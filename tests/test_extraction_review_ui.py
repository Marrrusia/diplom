"""Спорные элементы: пользователь видит, исправляет и явно принимает решение."""
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox
from reqtest.models.domain import Project, Requirement, Element, ReviewStatus
from reqtest.services.review import review_element, confirm_extraction
from reqtest.services.coverage import active_elements
from reqtest.ui.main_window import MainWindow
from reqtest.ui.edit_dialogs import ElementEditorDialog
from reqtest.exporters.xlsx_report import export_report
from openpyxl import load_workbook


def uncertain_project():
    return Project(name='Экспертиза', requirements=[Requirement(id='R', text='После события выполнить SendWord().')],
                   elements=[Element(id='E', requirement_id='R', type='действие', description='SendWord()',
                                     source_fragment='SendWord()', analysis_blocked=True, review_notes=['Проверьте условие'])],
                   analysis_incomplete=['R'])


def test_window_displays_blocked_candidates_without_matrix_rows():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = uncertain_project()
    window.refresh_tables()
    assert window.elements_table.rowCount() == 1
    assert window.elements_table.item(0, 6).text() == 'Требуется решение пользователя'
    assert window.matrix.rowCount() == 0
    assert 'Спорных элементов' in window.summary_label.text()
    assert 'Полнота выделения не подтверждена' in window.summary_label.text()
    window.close()


def test_add_dialog_cancel_is_atomic(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = uncertain_project()
    before = window.project.model_dump_json()
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args: ('R', True))
    monkeypatch.setattr(ElementEditorDialog, 'exec', lambda self: QDialog.DialogCode.Rejected)
    window.add_element()
    assert window.project.model_dump_json() == before
    window.close()


def test_add_dialog_save_preserves_pending_state(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = uncertain_project()
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args: ('R', True))
    def execute(dialog):
        dialog.category.setCurrentText('условие')
        dialog.description.setPlainText('После события')
        dialog.fragment.setPlainText('После события')
        dialog.save()
        return dialog.result()
    monkeypatch.setattr(ElementEditorDialog, 'exec', execute)
    window.add_element()
    assert len(window.project.elements) == 2
    assert window.project.elements[-1].analysis_blocked
    assert window.project.elements[-1].review_status == ReviewStatus.PENDING
    window.close()


def test_completeness_requires_explicit_decision_and_reason():
    project = uncertain_project()
    with pytest.raises(ValueError): confirm_extraction(project, 'R', ' ')
    with pytest.raises(ValueError): confirm_extraction(project, 'R', 'Сверено')
    accepted = review_element(project, 'E', True)
    assert len(active_elements(accepted)) == 1
    assert accepted.analysis_incomplete == ['R']
    confirmed = confirm_extraction(accepted, 'R', 'Сверены событие, действие и применимость')
    assert not confirmed.analysis_incomplete
    assert 'Ручная сверка полноты' in '\n'.join(confirmed.analysis_notes['R'])


def test_report_contains_block_state_and_completeness(tmp_path):
    path = tmp_path / 'report.xlsx'
    export_report(uncertain_project(), path)
    book = load_workbook(path)
    rows = list(book['Elements'].values)
    assert rows[1][rows[0].index('analysis_blocked')] is True
    summary = list(book['Summary'].values)
    assert any(row[0] == 'Спорных элементов (исключены до проверки)' and row[1] == 1 for row in summary)
    assert all(value is None for value in list(book['CoverageMatrix'].values)[0][3:])
    book.close()


def test_blocked_context_message_does_not_crash_window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    data = uncertain_project().model_dump()
    data['elements'][0]['type'] = 'условие'
    data['elements'].append(Element(id='A', requirement_id='R', type='действие', description='SendWord()',
                                   source_fragment='SendWord()', condition_ids=['E']).model_dump())
    window.project = Project.model_validate(data)
    window.refresh_tables()
    window.elements_table.setCurrentCell(1, 0)
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[2]))
    window.review_selected_element(True)
    assert messages and 'условия' in messages[0]
    assert window.project.elements[1].review_status == ReviewStatus.PENDING
    window.close()
