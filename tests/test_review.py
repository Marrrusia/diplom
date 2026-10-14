"""Редактирование и ручная проверка с атомарным сбросом устаревшего покрытия."""
import pytest
from PySide6.QtWidgets import QApplication, QDialog
from reqtest.models.domain import (Project, TestCase as Case, TestSource as Source,
    ReviewStatus, CoverageLink, CoverageStatus, GenerationEntry)
from reqtest.models.demo import demo_project
from reqtest.services.review import edit_test, edit_element, review_test, review_element
from reqtest.services.coverage import active_elements, active_tests, review_link, coverage_summary, matrix_status
from reqtest.services.generation import generation_targets, GenerationMode
from reqtest.ui.edit_dialogs import TestEditorDialog as CaseEditor, ElementEditorDialog


def reviewed_project():
    project = demo_project()
    data = project.model_dump()
    test = Case(id='T1', requirement_id=project.requirements[0].id, title='CRC',
        preconditions=['crcHandle.Instance == CRC'], input_data={'crcHandle.Instance': 'CRC'},
        steps=['Вызвать HAL_CRC_MspInit', 'Зафиксировать вызов макроса компонентом'],
        expected_result='__HAL_RCC_CRC_CLK_ENABLE() вызван без аргументов',
        element_ids=[e.id for e in project.elements], source=Source.GENERATED, review_status=ReviewStatus.ACCEPTED)
    data['test_cases'] = [test.model_dump()]
    data['coverage'] = [CoverageLink(element_id=e.id, test_case_id='T1', status=CoverageStatus.COVERED,
        rationale='Предложение модели', confidence=1, review_status=ReviewStatus.ACCEPTED).model_dump() for e in project.elements]
    data['generation_log'] = [GenerationEntry(id='L1', requirement_id=test.requirement_id, model='test', mode='full', test_case_ids=['T1'], notes='Исходная проверка').model_dump()]
    return Project.model_validate(data)


def test_edit_generated_test_resets_approval_and_links():
    original = reviewed_project()
    changed = edit_test(original, 'T1', {'expected_result': 'Макрос вызван без аргументов; тактирование CRC включено'})
    assert not changed.coverage
    assert changed.test_cases[0].review_status == ReviewStatus.PENDING
    assert not active_tests(changed)
    assert changed.generation_log[0].test_case_ids == ['T1']
    assert 'отредактирован' in changed.generation_log[0].notes
    assert coverage_summary(original)['total']['percent'] == 100
    assert coverage_summary(changed)['total']['percent'] == 0


@pytest.mark.parametrize('changes', [{'steps': []}, {'element_ids': ['missing']}, {'title': ' '}, {'source': 'существующий'}, {'element_ids': ['E1', 'E1']}])
def test_bad_edits_preserve_original(changes):
    project = reviewed_project()
    before = project.model_dump_json()
    with pytest.raises(ValueError):
        edit_test(project, 'T1', changes)
    assert project.model_dump_json() == before


def test_unchanged_save_preserves_approval():
    project = reviewed_project()
    assert edit_test(project, 'T1', {'title': 'CRC'}) == project


def test_element_edit_checks_quote_and_resets_context():
    project = reviewed_project()
    with pytest.raises(ValueError, match='Цитата'):
        edit_element(project, project.elements[0].id, {'source_fragment': 'Выдуманная цитата'})
    changed = edit_element(project, project.elements[0].id, {'description': 'Условие вызова HAL_CRC_MspInit'})
    assert not changed.coverage
    assert changed.elements[0].review_status == ReviewStatus.PENDING
    assert changed.test_cases[0].review_status == ReviewStatus.PENDING


def test_rejected_elements_retained_and_excluded():
    project = reviewed_project()
    rejected = review_element(project, project.elements[0].id, False)
    assert len(rejected.elements) == 4
    assert len(active_elements(rejected)) == 3
    assert coverage_summary(rejected)['rejected_elements'] == 1
    assert len(generation_targets(rejected, GenerationMode.MISSING)) == 3
    restored = review_element(rejected, project.elements[0].id, True)
    assert len(active_elements(restored)) == 4
    assert not restored.coverage


def test_test_acceptance_does_not_create_coverage():
    project = review_test(reviewed_project(), 'T1', False)
    assert not active_tests(project)
    restored = review_test(project, 'T1', True)
    assert len(active_tests(restored)) == 1
    assert not restored.coverage


def test_manual_decision_preserves_model_rationale():
    project = reviewed_project()
    data = project.model_dump()
    data['coverage'][0].update(status='требует проверки', review_status='ожидает проверки')
    project = Project.model_validate(data)
    with pytest.raises(ValueError, match='обоснование'):
        review_link(project, project.elements[0].id, 'T1', True, CoverageStatus.COVERED)
    changed = review_link(project, project.elements[0].id, 'T1', True, CoverageStatus.COVERED,
                          'Вызов присутствует в действиях, результат проверяется')
    assert changed.coverage[0].status == CoverageStatus.REVIEW
    assert changed.coverage[0].rationale == 'Предложение модели'
    assert changed.coverage[0].confirmed
    assert matrix_status(changed, changed.elements[0].id, 'T1') == CoverageStatus.COVERED


def test_editor_invalid_inputs_keep_dialog_open():
    app = QApplication.instance() or QApplication([])
    project = reviewed_project()
    dialog = CaseEditor(project, project.test_cases[0])
    dialog.inputs.setPlainText('not json')
    dialog.save()
    assert dialog.result_project is None
    assert dialog.error_label.text()
    dialog.inputs.setPlainText('{"crcHandle.Instance": "CRC"}')
    dialog.expected.setPlainText('Макрос вызван без аргументов; тактирование CRC включено')
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert 'тактирование' in dialog.result_project.test_cases[0].expected_result
    assert not dialog.result_project.coverage
    dialog.close()


def test_window_edits_test_using_form(monkeypatch):
    from reqtest.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = reviewed_project()
    window.refresh_tables()
    window.tables['test_cases'].setCurrentCell(0, 0)
    def execute(dialog):
        dialog.expected.setPlainText('Вызван макрос без аргументов; тактирование CRC включено')
        dialog.save()
        return dialog.result()
    monkeypatch.setattr(CaseEditor, 'exec', execute)
    window.edit_selected_test()
    assert window.project.test_cases[0].review_status == ReviewStatus.PENDING
    assert not window.project.coverage
    assert window.matrix.columnCount() == 0
    window.close()


def test_edit_one_test_preserves_other_test_links():
    project = reviewed_project()
    data = project.model_dump()
    other = project.test_cases[0].model_dump()
    other['id'] = 'T2'
    data['test_cases'].append(other)
    for link in list(data['coverage']):
        data['coverage'].append({**link, 'test_case_id': 'T2'})
    project = Project.model_validate(data)
    changed = edit_test(project, 'T1', {'expected_result': 'Исправленный ожидаемый результат'})
    assert len(changed.coverage) == 4
    assert all(l.test_case_id == 'T2' and l.confirmed for l in changed.coverage)
    assert coverage_summary(changed)['total']['percent'] == 100


def test_element_dialog_rejects_invented_quote():
    app = QApplication.instance() or QApplication([])
    project = reviewed_project()
    dialog = ElementEditorDialog(project, project.elements[0])
    dialog.fragment.setPlainText('Выдуманный фрагмент')
    dialog.save()
    assert dialog.result_project is None
    assert 'Цитата' in dialog.error_label.text()
    dialog.fragment.setPlainText(project.elements[0].source_fragment)
    dialog.description.setPlainText('Условие вызова HAL_CRC_MspInit')
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not dialog.result_project.coverage
    dialog.close()
