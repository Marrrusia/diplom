"""Смысловые сигналы не должны превращаться в молчаливые исправления."""
import json

import pytest

from reqtest.models.domain import Project, Requirement
from reqtest.services.coverage import active_elements
from reqtest.services.extraction import extract_project
from reqtest.services.extraction_validation import semantic_risks, context_risks, unsupported_literals


@pytest.mark.parametrize('description,source', [
    ('Не вызывать PollSensor()', 'PollSensor вызываться не должен'),
    ('call flush()', 'flush must be called once'),
    ('ResetTimer()', 'device.ResetTimer must not be called'),
])
def test_function_name_presence_independent_of_call_notation(description, source):
    assert unsupported_literals(description,source)==[]


@pytest.mark.parametrize('description,source,missing', [
    ('PollSensor()', 'PollSensorExtra', 'PollSensor'),
    ('pollSensor()', 'PollSensor', 'pollSensor'),
    ('Return 1', 'Return 1.5', '1'),
    ('Return 1', 'Return -1', '1'),
    ('Use 10', 'Use 100', '10'),
    ('Use 0x0F', 'Use 0xFF', '0x0F'),
])
def test_literal_fix_does_not_hide_changed_names_and_values(description,source,missing):
    assert missing in unsupported_literals(description,source)


def test_scope_and_order_risks_are_review_signals():
    assert context_risks('LOW_POWER: disable output', '', 'действие')
    assert not context_risks('LOW_POWER: disable output', 'LOW_POWER', 'действие')
    assert context_risks('capture register before clearing interrupt', 'before clearing interrupt', 'действие')
    assert not context_risks('if flag is set, clear interrupt', 'if flag is set', 'действие')


def test_expected_behavior_in_context_or_condition_is_flagged():
    assert context_risks('fields shall retain their values','fields shall retain their values','ограничение')
    assert semantic_risks('Компонент должен вернуть код','Компонент должен вернуть код','условие')
    assert not context_risks('Если READY равно 1, вернуть код','Если READY равно 1','действие')
from reqtest.services.review import review_element


@pytest.mark.parametrize('description,category', [
    ('Поведение при перегрузке не определено', 'ограничение'),
    ('Output is not specified', 'действие'),
    ('Быстро обработать пакет', 'ограничение'),
    ('допустимое время', 'диапазон'),
    ('Записать buffer и вернуть RESULT_OK', 'действие'),
    ('Store payload and return ACK', 'действие'),
    ('before acknowledging the interrupt', 'действие'),
])
def test_unverifiable_or_compound_candidates_flagged(description, category):
    assert semantic_risks(description, description, category)


@pytest.mark.parametrize('description,category', [
    ('Если A и B равны 1', 'условие'),
    ('Передать аргументы left и right', 'действие'),
    ('Биты вне маски должны сохранить значения', 'ограничение'),
    ('от MIN_VALUE до MAX_VALUE', 'диапазон'),
    ('от -5 до 5 включительно', 'диапазон'),
    ('Не вызывать Reset()', 'ограничение'),
])
def test_valid_conditions_negation_and_arguments_not_split(description, category):
    assert not semantic_risks(description, description, category)


def test_suspicious_candidate_preserved_but_excluded_until_review():
    text = 'Записать buffer и вернуть RESULT_OK после Commit(). Вызвать Flush().'
    response = json.dumps({'elements': [
        dict(type='действие', description='Записать buffer и вернуть RESULT_OK после Commit()', source_ids=['F001']),
        dict(type='действие', description='Вызвать Flush()',
             source_ids=['F002']),
    ]})

    class Client:
        def complete(self, messages, schema):
            return response

    project = extract_project(Project(name='Проверка', requirements=[Requirement(id='R', text=text)]), Client()).project
    assert len(project.extraction_log) == 1  # Не повторяем тот же смысловой спор трижды.
    assert len(project.elements) == 2
    suspect, valid = project.elements
    assert suspect.analysis_blocked and suspect.review_notes
    assert not valid.analysis_blocked
    assert suspect not in active_elements(project)
    assert valid in active_elements(project)
    reviewed = review_element(project, suspect.id, accepted=True)
    assert not reviewed.elements[0].analysis_blocked
