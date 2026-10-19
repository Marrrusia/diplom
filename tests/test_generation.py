"""Генерация: режимы, безопасность связей, дубликаты, проверка и фоновые операции."""
import json
import time
import pytest
from reqtest.models.demo import demo_project
from reqtest.models.domain import (LLMSettings, Project, TestCase as Case,
    ReviewStatus, CoverageLink, CoverageStatus, TestSource as Source)
from reqtest.services.generation import (generate_tests, GenerationMode,
    generation_targets, review_generated_test)
from reqtest.services.coverage import active_tests, coverage_summary
from reqtest.llm.client import LLMError


def candidate():
    project = demo_project()
    return dict(title='Тактирование CRC', preconditions=['crcHandle.Instance == CRC'],
        input_data={'crcHandle.Instance': 'CRC'}, steps=['Вызвать HAL_CRC_MspInit', 'Зафиксировать вызовы макросов'],
        expected_result='Вызван __HAL_RCC_CRC_CLK_ENABLE() без аргументов; тактирование CRC включено',
        element_ids=[e.id for e in project.elements])


class Client:
    def __init__(self, tests=None, validation=None):
        self.settings = LLMSettings(model='test-model')
        self.calls = 0
        self.tests = tests if tests is not None else [candidate()]
        self.validation = validation or dict(consistent=True, sufficient_specification=True,
            duplicate=False, rationale='Явные условия, действия и результат согласованы')
    def complete(self, messages, schema):
        self.calls += 1
        if 'tests' in schema['properties']:
            return json.dumps({'tests': self.tests, 'specification_gaps': []})
        return json.dumps(self.validation)


def covered_project():
    project = demo_project()
    test = Case(id='T1', requirement_id=project.requirements[0].id, **candidate())
    data = project.model_dump()
    data['test_cases'] = [test.model_dump()]
    data['coverage'] = [CoverageLink(element_id=e.id, test_case_id='T1', status=CoverageStatus.COVERED,
        rationale='Проверено', confidence=1, review_status=ReviewStatus.ACCEPTED).model_dump() for e in project.elements]
    return Project.model_validate(data)


def test_full_generation_requires_review_and_logs():
    original = demo_project()
    client = Client()
    result = generate_tests(original, client, GenerationMode.FULL)
    assert client.calls == 2
    assert result.generated_count == 1
    test = result.project.test_cases[0]
    assert test.source == Source.GENERATED
    assert test.review_status == ReviewStatus.PENDING
    assert not active_tests(result.project)
    assert result.project.generation_log[0].test_case_ids == [test.id]
    assert not original.test_cases
    accepted = review_generated_test(result.project, test.id, True)
    assert len(active_tests(accepted)) == 1
    assert coverage_summary(accepted)['total']['percent'] == 0
    assert not active_tests(review_generated_test(accepted, test.id, False))


def test_full_coverage_does_not_call_llm():
    client = Client()
    result = generate_tests(covered_project(), client, GenerationMode.MISSING)
    assert client.calls == 0
    assert result.generated_count == 0
    assert 'не требуется' in result.message
    assert coverage_summary(result.project)['total']['percent'] == 100


def test_full_mode_rejects_existing_tests():
    with pytest.raises(LLMError, match='отсутствии тестов'):
        generate_tests(covered_project(), Client(), GenerationMode.FULL)


def test_only_unconfirmed_targets_sent(monkeypatch):
    project = covered_project()
    project.coverage[-1].review_status = ReviewStatus.PENDING
    target = project.elements[-1].id
    assert [e.id for e in generation_targets(project, GenerationMode.MISSING)] == [target]
    client = Client(tests=[])
    original = client.complete
    def complete(messages, schema):
        payload = json.loads(messages[-1]['content'])
        assert [e['id'] for e in payload['target_elements']] == [target]
        assert len(payload['covered_element_ids']) == 3
        return original(messages, schema)
    monkeypatch.setattr(client, 'complete', complete)
    result = generate_tests(project, client, GenerationMode.MISSING)
    assert result.generated_count == 0
    assert target in result.project.generation_log[0].notes


@pytest.mark.parametrize('validation', [dict(consistent=False, sufficient_specification=True, duplicate=False, rationale='Противоречие'),
    dict(consistent=True, sufficient_specification=False, duplicate=False, rationale='Недостаточность'),
    dict(consistent=True, sufficient_specification=True, duplicate=True, rationale='Дубликат')])
def test_validator_rejections_logged(validation):
    result = generate_tests(demo_project(), Client(validation=validation), GenerationMode.FULL)
    assert not result.project.test_cases
    assert validation['rationale'] in result.project.generation_log[0].notes


def test_duplicate_with_different_title_skips_validation():
    first = candidate()
    second = candidate()
    second['title'] = 'Другое название'
    client = Client(tests=[first, second])
    result = generate_tests(demo_project(), client, GenerationMode.FULL)
    assert result.generated_count == 1
    assert client.calls == 2
    assert 'дубликат' in result.project.generation_log[0].notes


def test_explicit_negative_scenario_rejected():
    test = candidate()
    test['preconditions'] = ['crcHandle.Instance != CRC']
    client = Client(tests=[test], validation=dict(consistent=False, sufficient_specification=False,
                    duplicate=False, rationale='Отрицательная ветвь не определена'))
    result = generate_tests(demo_project(), client, GenerationMode.FULL)
    assert result.generated_count == 0
    assert client.calls == 2
    assert 'Противоречие' in result.project.generation_log[0].notes


@pytest.mark.parametrize('change', [{'element_ids': ['unknown']}, {'steps': []}, {'preconditions': [' ']}])
def test_invalid_candidate_atomic(change):
    test = candidate()
    test.update(change)
    project = demo_project()
    before = project.model_dump_json()
    with pytest.raises(LLMError):
        generate_tests(project, Client(tests=[test]), GenerationMode.FULL)
    assert project.model_dump_json() == before


def test_cancel_preserves_project():
    with pytest.raises(LLMError, match='отменена'):
        generate_tests(demo_project(), Client(), GenerationMode.FULL, cancelled=lambda: True)


def test_gui_generation_and_acceptance(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from reqtest.ui.main_window import MainWindow
    from reqtest.ui import generation_worker
    app = QApplication.instance() or QApplication([])
    def run(project, client, mode, progress, cancelled):
        return generate_tests(project, Client(), mode, progress, cancelled)
    monkeypatch.setattr(generation_worker, 'generate_tests', run)
    window = MainWindow()
    window.project = demo_project()
    window.start_generation()
    deadline = time.monotonic() + 3
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.worker is None
    assert window.generated_table.rowCount() == 1
    assert window.matrix.columnCount() == 0
    window.generated_table.setCurrentCell(0, 0)
    window.review_generated(True)
    assert window.matrix.columnCount() == 1
    assert '0.0%' in window.summary_label.text()
    window.close()
