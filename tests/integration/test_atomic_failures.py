"""Ошибки и отмена посередине многошагового сценария не меняют проект."""
import json
import httpx
import pytest
from reqtest.models.domain import Project, Requirement, LLMSettings, TestCase as Case
from reqtest.models.demo import demo_project
from reqtest.llm.client import LLMClient, LLMError
from reqtest.services.extraction import extract_project
from reqtest.services.coverage import analyze_coverage
from reqtest.services.generation import generate_tests, GenerationMode


@pytest.mark.integration
def test_http_failure_on_second_requirement_rolls_back():
    project = demo_project()
    data = project.model_dump()
    data['requirements'].append(Requirement(id='R2', text=project.requirements[0].text).model_dump())
    project = Project.model_validate(data)
    before = project.model_dump_json()
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(503, text='Server unavailable')
        content = json.dumps({'elements': [dict(type=e.type.value, description=e.description,
                        source_fragment=e.source_fragment) for e in demo_project().elements]})
        return httpx.Response(200, json={'message': {'content': content}})
    client = LLMClient(LLMSettings(model='test'), httpx.MockTransport(handler))
    with pytest.raises(LLMError, match='HTTP 503'):
        extract_project(project, client)
    assert len(calls) == 2
    assert project.model_dump_json() == before


@pytest.mark.integration
def test_cancel_after_first_pair_rolls_back_all_links():
    project = demo_project()
    data = project.model_dump()
    data['test_cases'] = [Case(id='T1', requirement_id=project.requirements[0].id, title='Тест',
         steps=['Вызвать HAL_CRC_MspInit'], expected_result='Результат').model_dump()]
    project = Project.model_validate(data)
    before = project.model_dump_json()
    class Client:
        calls = 0
        def complete(self, messages, schema):
            self.calls += 1
            return json.dumps({'status': 'не покрыт', 'rationale': 'Недостаточно доказательств', 'confidence': 0.9})
    client = Client()
    with pytest.raises(LLMError, match='отменён'):
        analyze_coverage(project, client, cancelled=lambda: client.calls > 0)
    assert client.calls == 1
    assert project.model_dump_json() == before


def proposal():
    return dict(title='Тест', preconditions=['crcHandle.Instance == CRC'], input_data={'crcHandle.Instance':'CRC'},
        steps=['Вызвать HAL_CRC_MspInit', 'Зафиксировать вызов __HAL_RCC_CRC_CLK_ENABLE() компонентом'],
        expected_result='Тактирование CRC включено; __HAL_RCC_CRC_CLK_ENABLE() вызван без аргументов',
        element_ids=[e.id for e in demo_project().elements])


@pytest.mark.integration
def test_invalid_second_validation_rolls_back_first_candidate():
    project = demo_project()
    before = project.model_dump_json()
    first = proposal()
    second = {**proposal(), 'steps': ['Вызвать HAL_CRC_MspInit на другом тестовом стенде']}
    class Client:
        settings = LLMSettings(model='test')
        calls = 0
        def complete(self, messages, schema):
            self.calls += 1
            if self.calls == 1:
                return json.dumps({'tests': [first, second]})
            if self.calls == 2:
                return json.dumps({'consistent': True, 'sufficient_specification': True, 'duplicate': False, 'rationale':'Согласован'})
            return 'broken JSON'
    client = Client()
    with pytest.raises(LLMError, match='JSON'):
        generate_tests(project, client, GenerationMode.FULL)
    assert client.calls == 3
    assert project.model_dump_json() == before


@pytest.mark.parametrize('change', [
    {'steps':['Вызов макроса __HAL_RCC_CRC_CLK_ENABLE()']},
    {'expected_result':'Макрос __HAL_RCC_CRC_CLK_ENABLE() вызван без аргументов'}])
def test_screenshot_generation_defects_rejected_before_model_validation(change):
    test = {**proposal(), **change}
    class Client:
        settings = LLMSettings(model='test')
        calls = 0
        def complete(self, messages, schema):
            self.calls += 1
            return json.dumps({'tests': [test]})
    client = Client()
    result = generate_tests(demo_project(), client, GenerationMode.FULL)
    assert result.generated_count == 0
    assert client.calls == 1
    assert 'Отклонено предложение' in result.project.generation_log[0].notes
