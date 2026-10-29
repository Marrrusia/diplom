"""Диагностика старого алгоритма сохраняется и при отказе."""
import json
import pytest
from reqtest.models.domain import Project, Requirement, LLMSettings
from reqtest.llm.client import LLMError
from reqtest.services.extraction import extract_project
from reqtest.services.extraction_diagnostics import DiagnosticClient


def test_rejected_answers_saved(tmp_path,monkeypatch):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path))
    class Client:
        def complete(self,messages,schema): return '{bad-json'
    project=Project(name='P',requirements=[Requirement(id='R',text='Вернуть READY.')])
    before=project.model_dump()
    with pytest.raises(LLMError,match='Диагностика:'):
        extract_project(project,Client())
    data=json.loads(next(tmp_path.glob('extraction-diagnostics-*.json')).read_text(encoding='utf-8'))
    assert data['status']=='failed' and len(data['attempts'])==1
    assert all(a['response']=='{bad-json' and a['errors'] for a in data['attempts'])
    assert project.model_dump()==before


def test_secret_redacted(tmp_path,monkeypatch):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path))
    class Client:
        settings=LLMSettings(provider='openai',base_url='https://example.com',model='test',api_key='secret-test-key')
        def complete(self,messages,schema): return 'secret-test-key'
    client=DiagnosticClient(Client(),Project(name='P'))
    assert client.complete([dict(role='user',content='secret-test-key')],{})=='secret-test-key'
    content=client.path.read_text(encoding='utf-8')
    assert 'secret-test-key' not in content and '[REDACTED]' in content
    assert 'base_url' not in content


def test_unwritable_log_does_not_change_response(tmp_path,monkeypatch):
    target=tmp_path/'file'; target.write_text('x')
    monkeypatch.setenv('REQTEST_LOG_DIR',str(target))
    class Client:
        def complete(self,messages,schema): return 'response'
    client=DiagnosticClient(Client(),Project(name='P'))
    assert client.complete([],{})=='response' and not client.saved
