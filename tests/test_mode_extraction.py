"""Регрессия сообщения DEMO_MODE_002 о пропущенном ACTIVE и пробеле спецификации."""
import json
from pathlib import Path

import pytest

from reqtest.importers.files import import_requirements_document
from reqtest.llm.client import LLMError
from reqtest.models.domain import Element, ElementType, Project, Requirement
from reqtest.services.extraction import extract_project
from reqtest.services.extraction_checks import missing_aspects, required_aspects
from reqtest.services.source_catalog import build_source_catalog


def test_mode_case_and_repetition_do_not_create_missing_aspects():
    text = 'В режиме ACTIVE вызвать StartADC(). В режиме ACTIVE вернуть STATUS_OK.'
    element = Element(id='E', requirement_id='R', type=ElementType.MODE,
                      description='Режим ACTIVE', source_fragment='В режиме ACTIVE вызвать StartADC().')
    assert len(required_aspects(text)) == 1
    assert not missing_aspects(text, [element])


def test_gap_does_not_require_an_undefined_mode():
    assert not required_aspects('Поведение в режиме UNKNOWN не определено.')


def test_mixed_source_does_not_hide_defined_mode():
    aspects = required_aspects('В режиме ACTIVE компонент должен вызвать StartADC(); остальное поведение не определено.')
    assert any(a.type == ElementType.MODE for a in aspects)


def test_technical_mode_case_is_preserved():
    text = 'В режиме ACTIVE вызвать StartADC().'
    element = Element(id='E', requirement_id='R', type=ElementType.MODE,
                      description='Режим active', source_fragment=text)
    assert missing_aspects(text, [element])


def test_demo_mode_defined_behavior_with_extra_gap_reference():
    root = Path(__file__).resolve().parents[1]
    requirement = import_requirements_document(root / 'examples/demo_suite/small_sets/DEMO_MODE_002/requirements.txt')[0]
    catalog = build_source_catalog(requirement.text)
    standby, active, gap = [ref.source_id for ref in catalog]
    items = [
        ('условие', 'Вызов ReadSample', [standby]),
        ('режим', 'Режим STANDBY', [standby]),
        ('режим', 'Режим ACTIVE', [active, gap]),
        ('действие', 'Вызвать StartADC()', [active, gap]),
        ('ограничение', 'StartADC() без аргументов', [active]),
        ('ограничение', 'ReadADC() без аргументов', [active]),
        ('действие', 'Вернуть 1', [gap]),
    ]

    class Client:
        calls = 0

        def complete(self, messages, schema):
            self.calls += 1
            return json.dumps({'elements': [dict(type=t, description=d, source_ids=s) for t, d, s in items]})

    client = Client()
    result = extract_project(Project(name='Режимы', requirements=[requirement]), client)
    assert client.calls == 1
    assert len([e for e in result.project.elements if e.type == ElementType.MODE]) == 2
    assert all(gap not in [ref.source_id for ref in e.source_refs] for e in result.project.elements)
    assert any('не определено' in note for note in result.notes[requirement.id])
    assert any('Исключён кандидат' in note and 'Вернуть 1' in note for note in result.notes[requirement.id])
    assert not any(e.description == 'Вернуть 1' for e in result.project.elements)


def test_gap_only_source_cannot_prove_defined_action():
    requirement = Requirement(id='R', text='Поведение в режиме ACTIVE при ADC_READY, отличном от 1, не определено.')

    class Client:
        def complete(self, messages, schema):
            return json.dumps({'elements': [dict(type='действие', description='Вернуть 1', source_ids=['F001'])]})

    project = Project(name='Пробел', requirements=[requirement])
    result = extract_project(project, Client())
    assert not result.project.elements
    assert any('Исключён кандидат' in note for note in result.notes['R'])
    assert any('Проверяемые элементы не выделены' in note for note in result.notes['R'])
    assert not project.elements


def test_discarded_candidate_does_not_hide_missing_required_mode():
    requirement = Requirement(id='R', text='В режиме ACTIVE компонент должен вызвать StartADC(). '
                              'Поведение в режиме ACTIVE при ошибке не определено.')

    class Client:
        def complete(self, messages, schema):
            return json.dumps({'elements': [dict(type='режим', description='Режим ACTIVE', source_ids=['F002'])]})

    with pytest.raises(LLMError, match='Пропущены отдельные аспекты'):
        extract_project(Project(name='Режим', requirements=[requirement]), Client())
