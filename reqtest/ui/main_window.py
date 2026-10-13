"""Каркас русскоязычного интерфейса первого этапа."""
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    """Главное окно с разделами будущего рабочего процесса."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Интеллектуальный анализ покрытия требований")
        self.resize(1100, 720)
        tabs = QTabWidget()
        for title in ("Требования", "Проверяемые элементы", "Тест-кейсы", "Матрица покрытия",
                      "Генерация тестов", "Отчёты", "Настройки LLM"):
            page = QWidget()
            layout = QVBoxLayout(page)
            label = QLabel(f"{title}: раздел будет реализован на следующих этапах.")
            label.setWordWrap(True)
            layout.addWidget(label)
            layout.addStretch()
            tabs.addTab(page, title)
        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Этап 1: структура проекта и модели данных готовы")
