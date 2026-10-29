"""Публичный одноэтапный процесс без повторной смысловой генерации."""
import json
import httpx
import pytest
from reqtest.models.domain import Project, Requirement, LLMSettings
from reqtest.services.extraction import extract_project, SYSTEM
from reqtest.llm.client import LLMClient, LLMError
from reqtest.storage.sqlite_project import save_project, load_project

TEXT='При вызове Fetch в режиме RUN, если READY равно 1, вернуть RESULT_OK.'
ITEM=dict(type='действие',description='Вернуть RESULT_OK',source_ids=['F001'],context_ids=['C001','C002','C003'])


class Client:
    def __init__(self, answers):
        self.answers=iter(answers)
        self.calls=[]
    def complete(self,messages,schema):
        self.calls.append(messages.copy())
        return json.dumps(next(self.answers))


def project():
    return Project(name='Короткий запрос',requirements=[Requirement(id='R',text=TEXT)])


def test_public_single_request_preserves_source_context_and_log(tmp_path):
    answer=dict(elements=[ITEM])
    client=Client([answer])
    result=extract_project(project(),client).project
    assert len(client.calls)==1
    assert 'READY равно 1' in result.elements[0].applicability
    assert len(result.elements[0].condition_ids)==3
    assert result.extraction_log[0].stage=='direct'
    assert json.loads(result.extraction_log[0].response)==answer
    assert result.analysis_incomplete==['R']
    save_project(result,tmp_path/'p.sqlite')
    assert load_project(tmp_path/'p.sqlite').extraction_log==result.extraction_log


def test_context_names_are_not_required_in_effect_quote():
    item={**ITEM,'description':'В режиме RUN при READY равно 1 вернуть RESULT_OK'}
    result=extract_project(project(),Client([dict(elements=[item])])).project
    assert not result.elements[0].analysis_blocked


def test_unknown_context_name_still_blocks_candidate():
    item={**ITEM,'description':'Вернуть UNKNOWN_FLAG'}
    result=extract_project(project(),Client([dict(elements=[item])])).project
    assert result.elements[0].analysis_blocked


def test_gap_only_answer_needs_one_request():
    client=Client([dict(elements=[],specification_gaps=['Не задан критерий'])])
    result=extract_project(project(),client)
    assert len(client.calls)==1 and not result.project.elements


def test_bad_quote_keeps_valid_neighbor_after_failed_repairs():
    bad={**ITEM,'source_ids':['invented']}
    client=Client([dict(elements=[ITEM,bad])]*3)
    result=extract_project(project(),client).project
    assert len([e for e in result.elements if e.type.value=='действие'])==1
    assert len(result.extraction_log)==3
    assert any('invented' in note for note in result.analysis_notes['R'])


def test_cancel_after_response_does_not_apply_project():
    original=project()
    before=original.model_dump_json()
    client=Client([dict(elements=[ITEM])])
    with pytest.raises(LLMError,match='отменён'):
        extract_project(original,client,cancelled=lambda:bool(client.calls))
    assert original.model_dump_json()==before


@pytest.mark.parametrize('provider',['ollama','openai'])
def test_public_workflow_uses_one_http_request(provider):
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        content=json.dumps(dict(elements=[ITEM]))
        return httpx.Response(200,json={'message':{'content':content}} if provider=='ollama'
            else {'choices':[{'message':{'content':content}}]})
    result=extract_project(project(),LLMClient(LLMSettings(provider=provider,model='same'),httpx.MockTransport(handler)))
    assert len(calls)==1 and len([e for e in result.project.elements if e.type.value=='действие'])==1
    assert calls[0]['messages'][0]['content'].startswith(SYSTEM)
