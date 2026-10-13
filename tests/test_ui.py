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
