"""Полный просмотр, фильтрация, общая отмена и прокручиваемые редакторы."""
import time
from PySide6.QtWidgets import QApplication, QSplitter, QDialogButtonBox
from reqtest.ui.main_window import MainWindow
from reqtest.ui.edit_dialogs import TestEditorDialog as CaseEditor
from reqtest.models.demo import demo_project
from reqtest.models.domain import TestCase as Case, Project, TestSource as Source
from reqtest.ui.presentation import readable_record


def project_with_test():
    project = demo_project()
    data = project.model_dump()
    data['test_cases'] = [Case(id='T1', requirement_id=project.requirements[0].id,
        title='Проверка тактирования CRC', steps=['Вызвать HAL_CRC_MspInit'],
        input_data={'crcHandle.Instance': 'CRC'}, preconditions=['crcHandle.Instance == CRC'],
        expected_result='Тактирование CRC включено', source=Source.GENERATED).model_dump()]
    return Project.model_validate(data)


def test_full_record_and_filter_preserve_model_indices():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = project_with_test()
    window.refresh_tables()
    table = window.tables['test_cases']
    table.setCurrentCell(0, 0)
    text = window.record_details['test_cases'].toPlainText()
    assert 'Ожидаемый результат:\nТактирование CRC включено' in text
    assert 'crcHandle.Instance: CRC' in text
    before = window.project.model_dump_json()
    window.search_fields['test_cases'].setText('не существующий текст')
    assert table.isRowHidden(0)
    assert not window.record_details['test_cases'].toPlainText()
    window.search_fields['test_cases'].clear()
    assert not table.isRowHidden(0)
    assert window.project.model_dump_json() == before
    assert window.findChildren(QSplitter)
    window.close()


def test_elements_show_full_requirement_and_selected_description():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = demo_project()
    window.refresh_tables()
    window.elements_table.setCurrentCell(2, 0)
    text = window.element_details.toPlainText()
    assert window.project.requirements[0].text in text
    assert window.project.elements[2].description in text
    window.close()


def test_generation_details_are_readable_not_raw_model_json():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = project_with_test()
    window.refresh_tables()
    window.generated_table.setCurrentCell(0, 0)
    text = window.generation_details.toPlainText()
    assert 'Ожидаемый результат:' in text
    assert 'Тактирование CRC включено' in text
    assert '"expected_result"' not in text
    window.close()


def test_global_progress_and_cancellation_visible_from_another_tab(monkeypatch):
    from reqtest.ui import analysis_worker
    from reqtest.services.extraction import AnalysisResult
    app = QApplication.instance() or QApplication([])
    def run(project, client, progress, cancelled):
        progress(1, 2)
        deadline = time.monotonic() + 2
        while not cancelled() and time.monotonic() < deadline:
            time.sleep(0.005)
        return AnalysisResult(project=project)
    monkeypatch.setattr(analysis_worker, 'extract_project', run)
    window = MainWindow()
    window.project = demo_project()
    window.project.elements = []
    window.show()
    window.centralWidget().setCurrentIndex(2)
    window.start_analysis()
    app.processEvents()
    assert window.analysis_progress.isVisible()
    assert window.global_cancel.isVisible() and window.global_cancel.isEnabled()
    assert not window.server.isEnabled()
    window.global_cancel.click()
    deadline = time.monotonic() + 3
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.worker is None
    assert not window.global_cancel.isEnabled()
    assert window.server.isEnabled()
    window.close()


def test_scrollable_editor_keeps_buttons_outside_scroll_area():
    app = QApplication.instance() or QApplication([])
    project = project_with_test()
    dialog = CaseEditor(project, project.test_cases[0])
    dialog.resize(700, 480)
    dialog.show()
    app.processEvents()
    assert dialog.scroll.widgetResizable()
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons.isVisible()
    assert not dialog.scroll.isAncestorOf(buttons)
    dialog.reject()


def test_switching_provider_preserves_custom_server():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.provider.setCurrentText('openai')
    assert window.server.text() == 'http://localhost:1234/v1'
    window.server.setText('http://custom-server:1234/v1')
    window.provider.setCurrentText('ollama')
    assert window.server.text() == 'http://custom-server:1234/v1'
    window.close()
