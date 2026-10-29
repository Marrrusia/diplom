"""Регрессии из присланного отчёта: истинная цитата не оправдывает выдуманное описание."""
import json
import pytest
from reqtest.models.domain import Project, Requirement
from reqtest.services.extraction import ExtractedElement, extract_project
from reqtest.services.element_grounding import grounding_issues
from reqtest.services.extraction_checks import required_aspects
from reqtest.llm.client import LLMError
from reqtest.services import extraction, coverage, generation


@pytest.mark.parametrize('fragment', [
    'Если value меньше 0 или больше 100, компонент должен вернуть STATUS_RANGE_ERROR и оставить currentLevel без изменения.',
    'Вычислить new_flags по формуле (old_flags & ~0x0F) | (requested_flags & 0x0F).',
    'Список команд, критерии корректности, допустимое время и ожидаемые ответы в этой спецификации не указаны.'
])
def test_report_invented_no_arguments_rejected(fragment):
    item = ExtractedElement(type='ограничение', description='без аргументов', source_fragment=fragment)
    assert any('без аргументов' in issue for issue in grounding_issues(item))


def test_unknown_name_number_rejected_even_with_existing_quote():
    item = ExtractedElement(type='действие', description='PollSensor вызывается через 20 мс', source_fragment='PollSensor вызывается через 10 мс')
    assert any('20' in issue for issue in grounding_issues(item))


def test_general_prompts_have_no_foreign_example_identifiers():
    for prompt in (extraction.SYSTEM, coverage.SYSTEM, generation.SYSTEM):
        for identifier in ('CRC','HAL_CRC_MspInit','crcHandle','Instance'):
            assert identifier not in prompt


def test_undefined_behavior_becomes_note_not_element():
    text = 'Поведение при ADC_READY, отличном от 1, не определено.'
    project = Project(name='Режим', requirements=[Requirement(id='R', text=text)])
    class Client:
        def complete(self, messages, schema):
            return json.dumps({'elements':[{'type':'условие','description':text,'source_ids':['F001']}]})
    result = extract_project(project, Client())
    assert not result.project.elements
    assert text in result.project.analysis_notes['R']


def test_report_invented_constraint_retried_without_applying_bad_element():
    text = 'Сохранить value в currentLevel.'
    project = Project(name='Проверка', requirements=[Requirement(id='R', text=text)])
    class Client:
        calls = 0
        def complete(self, messages, schema):
            self.calls += 1
            if self.calls == 1:
                return json.dumps({'elements':[{'type':'ограничение', 'description':'без аргументов', 'source_ids':['F001']}]})
            assert 'без аргументов' in messages[-1]['content']
            return json.dumps({'elements':[{'type':'действие', 'description':'Сохранить value в currentLevel', 'source_ids':['F001']}]})
    client = Client()
    result = extract_project(project, client)
    assert client.calls == 2
    assert len(result.project.elements) == 1
    assert result.project.elements[0].type.value == 'действие'
    assert not project.elements


def test_persistent_unsupported_description_preserves_project():
    text = 'Сохранить value в currentLevel.'
    project = Project(name='Проверка', requirements=[Requirement(id='R', text=text)])
    class Client:
        def complete(self, messages, schema):
            return json.dumps({'elements':[{'type':'ограничение', 'description':'без аргументов', 'source_ids':['F001']}]})
    with pytest.raises(LLMError, match='без аргументов'):
        extract_project(project, Client())
    assert not project.elements


def test_range_mode_loop_required_in_their_categories():
    aspects = required_aspects('При вызове F в режиме ACTIVE обработать value в диапазоне от 0 до 100 включительно не более 3 раз')
    assert {'диапазон','режим','цикл'} <= {a.type.value for a in aspects}


def test_category_errors_from_report_detected():
    item = ExtractedElement(type='диапазон',description='биты вне маски 0x0F должны сохранить old_flags',
        source_fragment='биты вне маски 0x0F должны сохранить old_flags')
    assert grounding_issues(item)
