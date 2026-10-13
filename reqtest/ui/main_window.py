"""Каркас русскоязычного интерфейса первого этапа."""
import logging
from pathlib import Path
from PySide6.QtWidgets import (QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QDialog, QInputDialog)
from openpyxl import load_workbook
from reqtest.models.domain import Project
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
                if kind == "requirements":
                    edit = QPushButton("Исправить текст выбранного требования")
                    edit.clicked.connect(self.edit_requirement)
                    layout.addWidget(edit)
                table = QTableWidget(0, len(FIELDS[kind]))
                table.setHorizontalHeaderLabels(list(FIELDS[kind].values()))
                table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                self.tables[kind] = table
                layout.addWidget(table)
                tabs.addTab(page, title)
                continue
            label = QLabel(f"{title}: раздел будет реализован на следующих этапах.")
            label.setWordWrap(True)
            layout.addWidget(label)
            layout.addStretch()
            tabs.addTab(page, title)
        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Этап 2: импорт требований и тест-кейсов. Данные пока хранятся только в памяти")

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
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка изменения", str(error))
