"""Отличить пропуск поля моделью от потери цитаты при обработке."""
import json
import pytest
from reqtest.models.demo import demo_project
from reqtest.models.domain import Project,TestCase as Case,LLMSettings
from reqtest.services.coverage import analyze_coverage
from reqtest.llm.client import LLMError


def project():
    p=demo_project();data=p.model_dump();data['elements']=data['elements'][:1]
    data['test_cases']=[Case(id='T',requirement_id=p.requirements[0].id,title='T',steps=['Вызвать HAL_CRC_MspInit'],expected_result='Тактирование CRC включено').model_dump()]
    return Project.model_validate(data)


def base():
    return dict(status='покрыт',rationale='Проверен вызов',confidence=0.95,precondition_evidence=[],step_evidence=['Вызвать HAL_CRC_MspInit'],result_evidence=[])


def read_file(path):
    return json.loads(next(path.glob('coverage-diagnostics-*.json')).read_text(encoding='utf-8'))


@pytest.mark.parametrize('provided',[False,True])
def test_distinguish_missing_result_field_from_empty_array(tmp_path,monkeypatch,provided):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path));value=base()
    if not provided:value.pop('result_evidence')
    raw=json.dumps(value,ensure_ascii=False)
    class Client:
        def complete(self,messages,schema):return raw
    if not provided:
        with pytest.raises(LLMError,match='result_evidence'):analyze_coverage(project(),Client())
        data=read_file(tmp_path)
        assert data['status']=='failed' and data['attempts'][0]['response']==raw
        assert 'parsed_before_validation' not in data['attempts'][0]
        return
    result=analyze_coverage(project(),Client());data=read_file(tmp_path);entry=data['attempts'][0]
    assert entry['response']==raw and data['status']=='completed'
    assert ('result_evidence' in entry['provided_fields'])==provided
    assert entry['parsed_before_validation']['result_evidence']==[]
    assert entry['final_decision']['status']=='требует проверки'
    assert entry['final_decision']==result.coverage[0].model_dump(mode='json')
    assert entry['element_id']==result.elements[0].id and entry['test_case_id']=='T'
    assert entry['messages'][1]['content']


def test_nonempty_result_survives_normalization_and_decision(tmp_path,monkeypatch):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path));value=base();value['result_evidence']=['Тактирование CRC включено']
    class Client:
        def complete(self,messages,schema):return json.dumps(value)
    analyze_coverage(project(),Client());entry=read_file(tmp_path)['attempts'][0]
    assert entry['parsed_before_validation']['result_evidence']==value['result_evidence']
    assert entry['parsed_after_quote_validation']['result_evidence']==value['result_evidence']
    assert not entry['invalid_quotes']
    assert 'Нет цитат действий или ожидаемого результата' not in entry['validation_issues']


def test_failed_attempts_saved_with_exact_pair(tmp_path,monkeypatch):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path));value=base();value['step_evidence']=['Выдуманное действие']
    class Client:
        def complete(self,messages,schema):return json.dumps(value)
    with pytest.raises(LLMError,match='Диагностика покрытия:'):analyze_coverage(project(),Client())
    data=read_file(tmp_path)
    assert data['status']=='failed' and len(data['attempts'])==3
    assert [a['attempt'] for a in data['attempts']]==[1,2,3]
    assert all(a['test_case_id']=='T' and a['invalid_quotes'] for a in data['attempts'])


def test_secret_is_not_exported_and_write_failure_is_nonfatal(tmp_path,monkeypatch):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path))
    class Client:
        settings=LLMSettings(model='test',api_key='secret-test-key')
        def complete(self,messages,schema):
            value=base();value['rationale']='secret-test-key';return json.dumps(value)
    result=analyze_coverage(project(),Client())
    data=read_file(tmp_path)
    assert 'secret-test-key' not in json.dumps(data)
    assert 'secret-test-key' in result.coverage[0].rationale
    file=tmp_path/'not_a_directory';file.write_text('x');monkeypatch.setenv('REQTEST_LOG_DIR',str(file))
    assert analyze_coverage(project(),Client()).coverage==result.coverage
