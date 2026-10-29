"""Двухэтапный публичный процесс: условия, типы, ошибки, хранение и HTTP."""
import json
import httpx
import pytest
from reqtest.llm.client import LLMClient, LLMError
from reqtest.models.domain import Project, Requirement, LLMSettings
from reqtest.services.extraction import extract_project
from reqtest.storage.sqlite_project import save_project, load_project
from reqtest.exporters.diagnostics import export_diagnostics

TEXT = 'По событию IRQ, если ENABLE равно 1, записать sample и вернуть SUCCESS.'
PLAN = dict(obligations=[
    dict(statement='Записать sample', source_fragment='записать sample',
         conditions=['По событию IRQ', 'если ENABLE равно 1']),
    dict(statement='Вернуть SUCCESS', source_fragment='вернуть SUCCESS',
         conditions=['По событию IRQ', 'если ENABLE равно 1']),
], specification_gaps=[])
REVIEW = dict(elements=[
 dict(type='условие', description='По событию IRQ',source_fragment='По событию IRQ',conditions=[]),
 dict(type='условие', description='ENABLE равно 1',source_fragment='если ENABLE равно 1',conditions=['По событию IRQ']),
 *[dict(type='действие',description=o['statement'],source_fragment=o['source_fragment'],conditions=o['conditions']) for o in PLAN['obligations']]
],specification_gaps=[])



class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def complete(self, messages, schema):
        self.calls.append((messages.copy(), schema))
        return json.dumps(next(self.responses), ensure_ascii=False)


def project(text=TEXT):
    return Project(name='Два этапа', requirements=[Requirement(id='R', text=text)])


def test_two_stages_preserve_context_and_raw_logs(tmp_path):
    client = Client([PLAN, REVIEW])
    result = extract_project(project(), client).project
    assert len(client.calls) == 2
    assert len(result.elements) == 4
    assert result.elements[1].applicability == 'По событию IRQ'
    assert result.elements[2].applicability == 'По событию IRQ; если ENABLE равно 1'
    assert result.elements[3].applicability == result.elements[2].applicability
    assert result.elements[2].source_fragment == 'записать sample'
    assert 'type' in client.calls[1][1]['properties']['elements']['items']['properties']
    assert [a.stage for a in result.extraction_log] == ['obligations','review']
    assert json.loads(result.extraction_log[0].response) == PLAN
    assert result.analysis_incomplete == ['R']
    path = tmp_path/'p.sqlite'
    save_project(result, path)
    restored = load_project(path)
    assert restored.extraction_log == result.extraction_log
    export_diagnostics(restored, tmp_path/'diagnostics.json')
    assert json.loads((tmp_path/'diagnostics.json').read_text(encoding='utf-8'))['attempts'][1]['stage'] == 'review'


def test_empty_draft_is_reviewed_for_missing_effects():
    client=Client([dict(obligations=[],specification_gaps=[]),REVIEW])
    result=extract_project(project(),client)
    assert len(client.calls)==2 and len(result.project.elements)==4


def test_bad_draft_quote_can_be_repaired_by_review():
    bad=json.loads(json.dumps(PLAN))
    bad['obligations'][0]['conditions']=['invented quote']
    client=Client([bad,REVIEW])
    result=extract_project(project(),client)
    assert len(client.calls)==2
    assert result.project.extraction_log[0].error
    payload=json.loads(client.calls[1][0][1]['content'])
    assert payload['text']==TEXT and payload['draft_errors']
    assert len(result.project.elements)==4


def test_partial_review_retains_good_items_and_records_rejections():
    bad=json.loads(json.dumps(REVIEW))
    bad['elements'][0]['source_fragment']='not in requirement'
    bad['elements'].append({'type':'unknown'})
    result=extract_project(project(),Client([PLAN,bad]))
    assert len(result.project.elements)==3
    assert 'исключён' in result.project.extraction_log[-1].error
    assert result.project.analysis_incomplete==['R']


def test_all_bad_review_quotes_preserve_existing_project():
    original=project()
    before=original.model_dump_json()
    bad=dict(elements=[dict(type='действие',description='Other()',source_fragment='invented',conditions=[])])
    with pytest.raises(LLMError):
        extract_project(original,Client([PLAN,bad]))
    assert original.model_dump_json()==before


def test_gap_only_review_is_successful_without_invented_elements():
    empty=dict(obligations=[],specification_gaps=['Не задано время'])
    client=Client([empty,dict(elements=[],specification_gaps=['Не задано время'])])
    result=extract_project(project('Время не задано.'),client)
    assert len(client.calls)==2
    assert not result.project.elements
    assert result.project.analysis_incomplete==['R']


def test_classifier_failure_preserves_original():
    original = project()
    before = original.model_dump_json()
    client = Client([PLAN, {}, {}, {}])
    with pytest.raises(LLMError):
        extract_project(original,client)
    assert original.model_dump_json() == before
    assert len(client.calls) == 4


def test_review_can_correct_roles_and_branch_conditions():
    plan=dict(obligations=[dict(statement='disable clock',source_fragment='SLEEP: disable clock',conditions=['disable clock'])],specification_gaps=[])
    review=dict(elements=[dict(type='ограничение',description='disable clock',source_fragment='disable clock',conditions=['SLEEP'])])
    result=extract_project(project('SLEEP: disable clock; RUN: enable output.'),Client([plan,review])).project
    assert result.elements[0].applicability=='SLEEP'
    assert result.elements[0].type.value=='ограничение'


def test_cancel_between_stages_preserves_original():
    original = project()
    client = Client([PLAN])
    with pytest.raises(LLMError, match='отменён'):
        extract_project(original,client,cancelled=lambda: bool(client.calls))
    assert not original.elements
    assert len(client.calls) == 1


@pytest.mark.parametrize('provider', ['ollama','openai'])
def test_public_workflow_http(provider):
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        response = PLAN if len(calls)==1 else REVIEW
        content = json.dumps(response)
        return httpx.Response(200,json={'message':{'content':content}} if provider=='ollama'
            else {'choices':[{'message':{'content':content}}]})
    result = extract_project(project(), LLMClient(LLMSettings(provider=provider,
        model='unchanged',base_url='http://localhost:11434'), httpx.MockTransport(handler)))
    assert len(calls)==2
    assert len(result.project.elements)==4
