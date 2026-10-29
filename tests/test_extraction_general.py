"""Каталог источников, частичные результаты, связи и совместимость хранения."""
import json
from pathlib import Path
import pytest
from reqtest.models.domain import Project, Requirement, ReviewStatus, TestCase as Case
from reqtest.services.extraction import extract_project, ExtractionResponse
from reqtest.services.source_catalog import build_source_catalog
from reqtest.services.branch_context import build_context_catalog
from reqtest.services.coverage import analyze_coverage
from reqtest.storage.sqlite_project import save_project, load_project
from reqtest.exporters.diagnostics import export_diagnostics
from reqtest.llm.client import LLMError

CORPUS=json.loads((Path(__file__).resolve().parents[1]/'examples/validation_corpus.json').read_text(encoding='utf-8'))

class Client:
    def __init__(self,responses):
        self.responses=iter(responses)
        self.calls=[]
    def complete(self,messages,schema):
        self.calls.append(json.loads(json.dumps(messages)))
        return next(self.responses)

def project(text='Если READY равно 1, выполнить SendWord().'):
    return Project(name='Источники',requirements=[Requirement(id='R',text=text)])

def item(**changes):
    return dict(type='действие',description='Выполнить SendWord()',source_ids=['F001'],**changes)

def answer(*items,**extra):
    return json.dumps(dict(elements=list(items),**extra))

@pytest.mark.parametrize('case',CORPUS,ids=[c['id'] for c in CORPUS])
def test_reference_corpus_protocol_uses_sources_not_copied_quotes(case):
    sources=build_source_catalog(case['text'])
    elements=[]
    for e in case['elements']:
        assert e['source_fragment'] in case['text']
        start=case['text'].index(e['source_fragment']);end=start+len(e['source_fragment'])
        elements.append(dict(type=e['type'],description=e['description'],source_ids=[s.source_id for s in sources if s.start<end and start<s.end]))
    client=Client([answer(*elements)])
    result=extract_project(project(case['text']),client).project
    assert len(client.calls)==1
    assert all(e.review_status==ReviewStatus.PENDING for e in result.elements)
    assert result.analysis_incomplete==['R']
    assert all(case['text'][ref.start:ref.end]==ref.text for e in result.elements for ref in e.source_refs)

def test_contract_has_no_model_quotes_or_element_ids():
    fields=ExtractionResponse.model_json_schema()['$defs']['ProposedElement']
    assert set(fields['properties'])=={'type','description','source_ids','context_ids','negated_context_ids'}
    assert set(fields['required'])==set(fields['properties'])

def test_source_id_repair_receives_previous_answer():
    first=answer({**item(),'source_ids':['UNKNOWN']})
    client=Client([first,answer(item())])
    result=extract_project(project(),client).project
    assert len(client.calls)==2
    assert client.calls[1][-2]==dict(role='assistant',content=first)
    assert 'UNKNOWN' in client.calls[1][-1]['content']
    assert len(result.extraction_log)==2

def test_partial_result_survives_bad_source_id():
    content=answer(item(),{**item(),'source_ids':['UNKNOWN']})
    result=extract_project(project(),Client([content]*3)).project
    assert len([e for e in result.elements if e.type.value=='действие'])==1
    assert any('UNKNOWN' in n for n in result.analysis_notes['R'])

@pytest.mark.parametrize('content',['not json','{"elements":[],"extra":true}',answer(dict(type='действие',description='X',source_fragment='X'))])
def test_invalid_contract_preserves_original(content):
    original=project();before=original.model_dump_json()
    with pytest.raises(LLMError):extract_project(original,Client([content]*3))
    assert original.model_dump_json()==before

def test_invented_literal_blocks_only_offending_effect():
    result=extract_project(project(),Client([answer(item(),{**item(),'description':'Выполнить UNKNOWN_FLAG'})])).project
    effects=[e for e in result.elements if e.type.value=='действие']
    assert not effects[0].analysis_blocked and effects[1].analysis_blocked

def test_duplicate_and_opposite_conditions():
    positive=item(context_ids=['C001'])
    negative=item(negated_context_ids=['C001'])
    result=extract_project(project(),Client([answer(positive,positive,negative)])).project
    effects=[e for e in result.elements if e.type.value=='действие']
    assert len(effects)==2
    assert effects[0].condition_ids==effects[1].negated_condition_ids

def test_gap_only_response():
    result=extract_project(project(),Client([answer(specification_gaps=['Недостаточно данных'])])).project
    assert not result.elements and 'Недостаточно данных' in result.analysis_notes['R']

def test_cancel_after_response_preserves_original():
    original=project();before=original.model_dump_json();client=Client([answer(item())])
    with pytest.raises(LLMError,match='отменён'):extract_project(original,client,cancelled=lambda:bool(client.calls))
    assert original.model_dump_json()==before

def test_context_and_raw_response_roundtrip(tmp_path):
    content=answer(item())
    result=extract_project(project(),Client([content])).project
    save_project(result,tmp_path/'p.sqlite')
    restored=load_project(tmp_path/'p.sqlite')
    assert restored==result and restored.elements[0].condition_ids
    export_diagnostics(restored,tmp_path/'diagnostics.json')
    data=json.loads((tmp_path/'diagnostics.json').read_text(encoding='utf-8'))
    assert data['attempts'][0]['response']==content
    assert data['elements'][0]['condition_ids']==result.elements[0].condition_ids
    assert data['catalogs']['R']['contexts'][0]['source_id']=='C001'
    assert 'api_key' not in data and 'base_url' not in data

def test_coverage_receives_structural_applicability():
    result=extract_project(project(),Client([answer(item())])).project
    data=result.model_dump();data['test_cases']=[Case(id='T',requirement_id='R',title='T',steps=['Вызвать SendWord()'],expected_result='Готово').model_dump()]
    client=Client([json.dumps(dict(status='не покрыт',confidence=1,rationale='Нет доказательств'))]*len(result.elements))
    analyze_coverage(Project.model_validate(data),client)
    payload=json.loads(client.calls[0][1]['content'])
    assert payload['applicability']['all_true']==['Если READY равно 1']
