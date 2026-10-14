"""Покрытие: доказательства, ручное подтверждение, противоречия и статистика."""
import json
import pytest
from reqtest.models.demo import demo_project
from reqtest.models.domain import (TestCase as Case, ReviewStatus, TestSource as Source,
    CoverageStatus, Project, Requirement, Element, ElementType)
from reqtest.services.coverage import (analyze_coverage, coverage_summary,
    review_link, matrix_status, active_tests, explicit_conflicts)
from reqtest.llm.client import LLMError


def project_with_test():
    project = demo_project()
    data = project.model_dump()
    data['test_cases'] = [Case(id='T1', requirement_id=project.requirements[0].id,
        title='CRC', preconditions=['crcHandle.Instance == CRC'],
        steps=['Вызвать HAL_CRC_MspInit'],
        expected_result='Тактирование CRC включено вызовом __HAL_RCC_CRC_CLK_ENABLE() без аргументов').model_dump()]
    return Project.model_validate(data)


class Client:
    def __init__(self, **changes):
        self.calls = 0
        self.changes = changes
    def complete(self, messages, schema):
        self.calls += 1
        data = dict(status='покрыт', rationale='Условие и действия проверены', confidence=0.95,
                    precondition_evidence=['crcHandle.Instance == CRC'], step_evidence=['Вызвать HAL_CRC_MspInit'],
                    result_evidence=['Тактирование CRC включено вызовом __HAL_RCC_CRC_CLK_ENABLE() без аргументов'])
        data.update(self.changes)
        return json.dumps(data)


def test_coverage_counts_only_confirmed_elements():
    client = Client()
    project = analyze_coverage(project_with_test(), client)
    assert client.calls == 4
    assert coverage_summary(project)['total']['percent'] == 0
    assert all(matrix_status(project, e.id, 'T1') == CoverageStatus.REVIEW for e in project.elements)
    for element in project.elements:
        project = review_link(project, element.id, 'T1', True)
    assert coverage_summary(project)['total']['percent'] == 100
    assert all(matrix_status(project, e.id, 'T1') == CoverageStatus.COVERED for e in project.elements)
    project = review_link(project, project.elements[0].id, 'T1', False)
    assert coverage_summary(project)['total']['percent'] == 75


@pytest.mark.parametrize('changes', [{'step_evidence': []}, {'result_evidence': []}, {'confidence': 0.5}])
def test_missing_evidence_or_low_confidence_requires_review(changes):
    project = analyze_coverage(project_with_test(), Client(**changes))
    assert all(l.status == CoverageStatus.REVIEW for l in project.coverage)
    with pytest.raises(ValueError, match='требует проверки'):
        review_link(project, project.elements[0].id, 'T1', True)


def test_invented_evidence_is_rejected_atomically():
    project = project_with_test()
    before = project.model_dump_json()
    with pytest.raises(LLMError, match='выдумала цитату'):
        analyze_coverage(project, Client(step_evidence=['Нажать выдуманную кнопку']))
    assert project.model_dump_json() == before


def test_title_match_is_not_evidence():
    data = project_with_test().model_dump()
    data['test_cases'][0].update(title='HAL_CRC_MspInit CRC', preconditions=[], steps=['Запустить стенд'], expected_result='Стенд готов')
    project = Project.model_validate(data)
    client = Client(precondition_evidence=[], step_evidence=['Запустить стенд'], result_evidence=['Стенд готов'])
    result = analyze_coverage(project, client)
    assert result.coverage[0].status == CoverageStatus.REVIEW
    assert 'HAL_CRC_MspInit' in result.coverage[0].rationale


def test_excluded_tests_and_empty_stats():
    project = project_with_test()
    project.test_cases[0].review_status = ReviewStatus.REJECTED
    assert not active_tests(project)
    client = Client()
    analyzed = analyze_coverage(project, client)
    assert client.calls == 0
    assert coverage_summary(analyzed)['total']['percent'] == 0
    assert coverage_summary(Project(name='Пустой'))['total']['percent'] is None
    project.test_cases[0].review_status = ReviewStatus.PENDING
    project.test_cases[0].source = Source.GENERATED
    assert not active_tests(project)


def test_conflicting_instance_detected():
    project = project_with_test()
    data = project.model_dump()
    data['test_cases'][0]['preconditions'] = ['crcHandle.Instance != CRC']
    project = Project.model_validate(data)
    result = analyze_coverage(project, Client(precondition_evidence=['crcHandle.Instance != CRC']))
    assert all(l.status == CoverageStatus.REVIEW for l in result.coverage)
    assert 'Противоречие' in result.coverage[0].rationale


def test_macro_arguments_conflict():
    assert explicit_conflicts(demo_project().requirements[0].text, '__HAL_RCC_CRC_CLK_ENABLE(1)')


def test_no_tests_do_not_imply_coverage():
    analyzed = analyze_coverage(demo_project(), Client())
    assert not analyzed.coverage
    assert coverage_summary(analyzed)['total']['uncovered'] == 4


def test_cancel_and_invalid_schema_preserve_project():
    with pytest.raises(LLMError, match='отменён'):
        analyze_coverage(project_with_test(), Client(), cancelled=lambda: True)
    with pytest.raises(LLMError, match='JSON'):
        analyze_coverage(project_with_test(), Client(confidence=2))


def test_window_background_coverage_and_review(monkeypatch):
    import time
    from PySide6.QtWidgets import QApplication
    from reqtest.ui.main_window import MainWindow
    from reqtest.ui import coverage_worker
    app = QApplication.instance() or QApplication([])
    def run(project, client, progress, cancelled):
        return analyze_coverage(project, Client(), progress, cancelled)
    monkeypatch.setattr(coverage_worker, 'analyze_coverage', run)
    window = MainWindow()
    window.project = project_with_test()
    window.start_coverage()
    assert not window.analyze_button.isEnabled()
    deadline = time.monotonic() + 3
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.worker is None
    assert window.matrix.rowCount() == 4
    assert window.matrix.columnCount() == 1
    assert window.matrix.item(0, 0).text() == 'требует проверки'
    window.matrix.setCurrentCell(0, 0)
    window.show_link(0, 0)
    assert 'Уверенность' in window.coverage_details.toPlainText()
    window.review_selected_link(True)
    assert window.matrix.item(0, 0).text() == 'покрыт'
    assert '25.0%' in window.summary_label.text()
    window.close()
