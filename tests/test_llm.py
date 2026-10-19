"""Проверки протоколов, валидации LLM и фонового потока без внешней модели."""
import json
import time
import httpx
import pytest
from reqtest.llm.client import LLMClient, LLMError
from reqtest.models.domain import LLMSettings
from reqtest.models.demo import demo_project
from reqtest.services.extraction import extract_project
from extraction_fakes import clean_review


def response(fragment='без аргументов'):
    items = [{'type': e.type.value, 'description': e.description, 'source_ids': ['F001']}
             for e in demo_project().elements]
    items[-1]['source_ids'] = ['F001'] if fragment == 'без аргументов' else ['UNKNOWN']
    return json.dumps({'elements': items, 'specification_gaps': []}, ensure_ascii=False)



@pytest.mark.parametrize('provider,path', [('ollama','/api/chat'), ('openai','/v1/chat/completions')])
def test_http_protocol(provider, path):
    def handler(request):
        assert request.url.path == path
        assert request.headers['Authorization'] == 'Bearer test-secret'
        body = json.loads(request.content)
        assert body['model'] == 'test'
        messages = body['messages']
        content = (json.dumps(clean_review(json.loads(messages[1]['content'])))
                   if messages[0]['content'].startswith('Проверь выделение') else response())
        if provider == 'ollama':
            assert body['stream'] is False
            return httpx.Response(200, json={'message': {'content': content}})
        return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
    settings = LLMSettings(provider=provider, model='test', api_key='test-secret',
                           base_url='http://localhost:1234' + ('/v1' if provider == 'openai' else ''))
    result = extract_project(demo_project(), LLMClient(settings, httpx.MockTransport(handler)))
    assert len(result.project.elements) == 4
    assert result.project.elements[0].review_status.value == 'ожидает проверки'
    assert not result.project.coverage
    assert not any(e.analysis_blocked for e in result.project.elements)


class FakeClient:
    def __init__(self, content):
        self.content = content
    def complete(self, messages, schema):
        return self.content


@pytest.mark.parametrize('content', ['not json', '{"elements":[],"unknown":true}'])
def test_invalid_answers_preserve_project(content):
    project = demo_project()
    before = project.model_dump_json()
    with pytest.raises(LLMError):
        extract_project(project, FakeClient(content))
    assert project.model_dump_json() == before


def test_cancellation():
    with pytest.raises(LLMError, match='отменён'):
        extract_project(demo_project(), FakeClient(response()), cancelled=lambda: True)


def test_empty_answer_warns():
    from reqtest.models.domain import Project, Requirement
    project = Project(name='Без триггера', requirements=[Requirement(id='R1', text='Модуль должен работать')])
    result = extract_project(project, FakeClient('{"elements":[]}'))
    assert not result.project.elements
    assert result.notes['R1']


def test_http_errors_hide_secrets():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text='test-secret'))
    client = LLMClient(LLMSettings(model='test', api_key='test-secret'), transport)
    with pytest.raises(LLMError, match='HTTP 401') as error:
        client.complete([], {})
    assert 'test-secret' not in str(error.value)


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout('secret response', request=request)
    with pytest.raises(LLMError, match='180 секунд'):
        LLMClient(LLMSettings(model='test'), httpx.MockTransport(handler)).complete([], {})


def test_background_window_analysis(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from reqtest.ui.main_window import MainWindow
    from reqtest.ui import analysis_worker
    from reqtest.services.extraction import AnalysisResult
    app = QApplication.instance() or QApplication([])
    def fake_extract(project, client, progress, cancelled):
        time.sleep(0.05)
        progress(1, 1)
        return AnalysisResult(project=demo_project())
    monkeypatch.setattr(analysis_worker, 'extract_project', fake_extract)
    window = MainWindow()
    window.project = demo_project()
    window.project.elements = []
    window.start_analysis()
    assert window.worker is not None
    assert not window.analyze_button.isEnabled()
    deadline = time.monotonic() + 3
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.worker is None
    assert window.elements_table.rowCount() == 4
    assert window.analyze_button.isEnabled()
    window.close()


def test_requirement_edit_invalidates_elements():
    from reqtest.services.project_import import update_requirement_text
    original = demo_project()
    updated = update_requirement_text(original, original.requirements[0].id, 'Изменённое требование')
    assert not updated.elements
    assert len(original.elements) == 4
