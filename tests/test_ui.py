"""Проверка создания интерфейса без запуска бесконечного цикла событий."""
import os
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
