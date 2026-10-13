"""Каркас русскоязычного интерфейса первого этапа."""
import logging
from pathlib import Path
from PySide6.QtWidgets import (QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget,
    QFormLayout, QComboBox, QLineEdit, QProgressBar, QTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QDialog, QInputDialog)
from openpyxl import load_workbook
from reqtest.models.domain import Project, LLMSettings
from reqtest.ui.analysis_worker import AnalysisWorker
from reqtest.importers.files import read_table, import_requirements_document, import_requirements_table, import_tests_table
from reqtest.services.project_import import merge_import, update_requirement_text
from reqtest.ui.import_dialog import MappingDialog, FIELDS


class MainWindow(QMainWindow):
    """Главное окно с разделами будущего рабочего процесса."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Интеллектуальный анализ покрытия требований")
        self.resize(1100, 720)
        self.project = Project(name="Новый проект")
        self.tables = {}
        self.worker = None
        self.import_buttons = []
        tabs = QTabWidget()
        for title in ("Требования", "Проверяемые элементы", "Тест-кейсы", "Матрица покрытия",
                      "Генерация тестов", "Отчёты", "Настройки LLM"):
            page = QWidget()
            layout = QVBoxLayout(page)
            if title in ("Требования", "Тест-кейсы"):
                kind = "requirements" if title == "Требования" else "test_cases"
                button = QPushButton("Импортировать файл")
                button.clicked.connect(lambda checked=False, k=kind: self.import_file(k))
                layout.addWidget(button)
                self.import_buttons.append(button)
                if kind == "requirements":
                    edit = QPushButton("Исправить текст выбранного требования")
                    edit.clicked.connect(self.edit_requirement)
                    layout.addWidget(edit)
                    self.import_buttons.append(edit)
                table = QTableWidget(0, len(FIELDS[kind]))
                table.setHorizontalHeaderLabels(list(FIELDS[kind].values()))
                table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                self.tables[kind] = table
                layout.addWidget(table)
                tabs.addTab(page, title)
                continue
            if title == "Настройки LLM":
                form = QFormLayout()
                self.provider = QComboBox()
                self.provider.addItems(["ollama", "openai"])
                self.server = QLineEdit("http://localhost:11434")
                self.model_name = QLineEdit("qwen2.5:7b")
                self.api_key = QLineEdit()
                self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
                for name, widget in (("Тип сервера", self.provider), ("Адрес сервера", self.server),
                                     ("Модель", self.model_name), ("API-ключ (необязательно)", self.api_key)):
                    form.addRow(name, widget)
                layout.addLayout(form)
                layout.addWidget(QLabel("Ollama: http://localhost:11434. OpenAI API: адрес с /v1.\n"
                                        "Ключ и настройки хранятся только в текущем сеансе."))
                layout.addStretch()
                tabs.addTab(page, title)
                continue
            if title == "Проверяемые элементы":
                self.analyze_button = QPushButton("Выделить элементы всех требований")
                self.analyze_button.clicked.connect(self.start_analysis)
                layout.addWidget(self.analyze_button)
                self.cancel_button = QPushButton("Отменить анализ")
                self.cancel_button.setEnabled(False)
                self.cancel_button.clicked.connect(self.cancel_analysis)
                layout.addWidget(self.cancel_button)
                self.analysis_progress = QProgressBar()
                layout.addWidget(self.analysis_progress)
                self.elements_table = QTableWidget(0, 6)
                self.elements_table.setHorizontalHeaderLabels(["ID", "Требование", "Категория", "Описание", "Цитата", "Проверка"])
                self.elements_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                layout.addWidget(self.elements_table)
                self.analysis_notes = QTextEdit()
                self.analysis_notes.setReadOnly(True)
                layout.addWidget(self.analysis_notes)
                tabs.addTab(page, title)
                continue
            label = QLabel(f"{title}: раздел будет реализован на следующих этапах.")
            label.setWordWrap(True)
            layout.addWidget(label)
            layout.addStretch()
            tabs.addTab(page, title)
        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Этап 3: импорт и выделение элементов через LLM. Данные пока хранятся только в памяти")

    def import_file(self, kind: str) -> None:
        """Выбрать файл и настройки; передать обработку импортёрам и сервису."""
        filters = "Требования (*.txt *.docx *.xlsx)" if kind == "requirements" else "Тест-кейсы (*.csv *.xlsx)"
        filename, _ = QFileDialog.getOpenFileName(self, "Импорт", "", filters)
        if not filename:
            return
        try:
            path = Path(filename)
            if path.suffix.lower() in (".txt", ".docx"):
                items = import_requirements_document(path)
            else:
                sheet = None
                encoding = "utf-8-sig"
                if path.suffix.lower() == ".xlsx":
                    workbook = load_workbook(path, read_only=True)
                    try:
                        names = workbook.sheetnames
                    finally:
                        workbook.close()
                    sheet, ok = QInputDialog.getItem(self, "Лист Excel", "Выберите лист", names, 0, False)
                    if not ok:
                        return
                else:
                    encoding, ok = QInputDialog.getItem(self, "Кодировка CSV", "Кодировка", ["utf-8-sig", "cp1251"], 0, False)
                    if not ok:
                        return
                table = read_table(path, sheet, encoding)
                dialog = MappingDialog(table, kind, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                items = (import_requirements_table(table, dialog.mapping(), filename)
                         if kind == "requirements" else import_tests_table(table, dialog.mapping()))
            self.project = merge_import(self.project, items, kind)
            self.refresh_tables()
            self.statusBar().showMessage(f"Добавлено записей: {len(items)}. Данные только в памяти")
        except Exception as error:
            logging.exception("Ошибка импорта")
            QMessageBox.warning(self, "Ошибка импорта", str(error))

    def refresh_tables(self) -> None:
        """Отобразить принятые записи проекта."""
        for kind, table in self.tables.items():
            items = getattr(self.project, kind)
            table.setRowCount(len(items))
            for i, item in enumerate(items):
                for j, field in enumerate(FIELDS[kind]):
                    value = getattr(item, field)
                    if isinstance(value, list):
                        value = "\n".join(value)
                    table.setItem(i, j, QTableWidgetItem(str(value or "")))
            table.resizeColumnsToContents()

    def edit_requirement(self) -> None:
        """Редактировать выбранное требование с проверкой снимка проекта."""
        row = self.tables["requirements"].currentRow()
        if row < 0:
            QMessageBox.information(self, "Выбор требования", "Выберите строку требования")
            return
        requirement = self.project.requirements[row]
        text, ok = QInputDialog.getMultiLineText(self, "Исправить текст", requirement.id, requirement.text)
        if not ok:
            return
        try:
            self.project = update_requirement_text(self.project, requirement.id, text)
            self.refresh_tables()
            self.render_elements()
            self.analysis_notes.clear()
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка изменения", str(error))

    def start_analysis(self) -> None:
        """Собрать настройки сеанса и запустить фоновый анализ."""
        if self.worker is not None:
            return
        if not self.project.requirements:
            QMessageBox.information(self, "Анализ", "Сначала импортируйте требования")
            return
        if self.project.elements:
            answer = QMessageBox.question(self, "Повторный анализ",
                "Существующие элементы, связи тестов с элементами и покрытие будут сброшены. Продолжить?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        settings = LLMSettings(provider=self.provider.currentText(), base_url=self.server.text(),
                               model=self.model_name.text(), api_key=self.api_key.text() or None)
        self.worker = AnalysisWorker(self.project, settings, self)
        self.worker.result.connect(self.accept_analysis)
        self.worker.error.connect(lambda message: QMessageBox.warning(self, "Ошибка LLM", message))
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.analysis_finished)
        self.analyze_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        for button in self.import_buttons:
            button.setEnabled(False)
        self.analysis_progress.setRange(0, len(self.project.requirements))
        self.analysis_progress.setValue(0)
        self.statusBar().showMessage("Анализ выполняется в фоне…")
        self.worker.start()

    def update_progress(self, value: int, total: int) -> None:
        """Обновить прогресс в GUI-потоке."""
        self.analysis_progress.setRange(0, total)
        self.analysis_progress.setValue(value)

    def accept_analysis(self, result) -> None:
        """Принять только завершённый проверенный снимок."""
        self.project = result.project
        self.render_elements()
        self.analysis_notes.setPlainText("Результат LLM требует ручной проверки. Цитаты проверены автоматически; "
            "соответствие описаний смыслу требования не гарантируется.\n\n" +
            "\n".join(f"{identifier}: {note}" for identifier, notes in result.notes.items() for note in notes))

    def cancel_analysis(self) -> None:
        """Отменить между запросами; текущий HTTP-запрос ограничен таймаутом."""
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Отмена после завершения текущего запроса (до 180 секунд)")

    def analysis_finished(self) -> None:
        """Освободить поток и разрешить следующую операцию."""
        self.worker.deleteLater()
        self.worker = None
        self.analyze_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        for button in self.import_buttons:
            button.setEnabled(True)
        self.statusBar().showMessage("Операция завершена. Данные только в памяти")

    def closeEvent(self, event) -> None:
        """Не уничтожать работающий поток при закрытии окна."""
        if self.worker is not None:
            self.cancel_analysis()
            event.ignore()
            return
        event.accept()

    def render_elements(self) -> None:
        """Показать текущие предложения модели."""
        self.elements_table.setRowCount(len(self.project.elements))
        for i, element in enumerate(self.project.elements):
            values = (element.id, element.requirement_id, element.type.value,
                      element.description, element.source_fragment, element.review_status.value)
            for j, value in enumerate(values):
                self.elements_table.setItem(i, j, QTableWidgetItem(value))
