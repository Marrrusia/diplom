"""Проверка создания интерфейса без запуска бесконечного цикла событий."""
import os
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QTabWidget
from reqtest.ui.main_window import MainWindow


def test_window_has_russian_sections():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert tabs.count() == 7
    assert tabs.tabText(0) == "Требования"
    assert tabs.tabText(6) == "Настройки LLM"
    window.show()
    app.processEvents()
    window.close()


def test_window_import_txt(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'requirements.txt'
    path.write_text('R1: Требование', encoding='utf-8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    window = MainWindow()
    window.import_file('requirements')
    assert window.project.requirements[0].id == 'R1'
    assert window.tables['requirements'].item(0, 1).text() == 'Требование'
    window.close()


def test_requirements_button_imports_actual_demo_txt(monkeypatch):
    from pathlib import Path
    from PySide6.QtWidgets import QFileDialog, QPushButton
    app = QApplication.instance() or QApplication([])
    path = Path(__file__).resolve().parents[1] / 'examples/demo_suite/small_sets/DEMO_RANGE_001/requirements.txt'
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    window = MainWindow()
    page = window.centralWidget().widget(0)
    button = next(b for b in page.findChildren(QPushButton) if b.text() == 'Импортировать файл')
    button.click()
    assert len(window.project.requirements) == 1
    assert window.project.requirements[0].id == 'DEMO_RANGE_001'
    window.close()


def test_bad_suffix_reports_actual_filename_without_csv_prompt(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'requirements.txt.lnk'
    path.write_text('R1: Текст', encoding='utf-8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[2]))
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args: pytest.fail('Не должен предлагать кодировку CSV'))
    window = MainWindow()
    window.import_file('requirements')
    assert not window.project.requirements
    assert 'requirements.txt.lnk' in messages[0]
    assert 'Импорт требований' in messages[0]
    window.close()
