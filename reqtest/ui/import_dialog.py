"""Сопоставление колонок с предварительным просмотром."""
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                              QTableWidget, QTableWidgetItem, QVBoxLayout)
from reqtest.importers.files import Table

FIELDS = {
    "requirements": {"id": "Идентификатор", "text": "Текст", "type": "Тип", "source": "Источник"},
    "test_cases": {"id": "Идентификатор", "requirement_id": "Требование", "title": "Название",
                   "preconditions": "Предусловия", "input_data": "Входные данные",
                   "steps": "Действия", "expected_result": "Ожидаемый результат"},
}


class MappingDialog(QDialog):
    """Выбор колонок; обязательность и ошибки проверяются импортёром."""
    def __init__(self, table: Table, kind: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сопоставление колонок")
        self.resize(800, 550)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.fields = {}
        for field, label in FIELDS[kind].items():
            combo = QComboBox()
            combo.addItem("— Не импортировать —")
            combo.addItems(table.headers)
            for header in table.headers:
                if header.casefold() in (field.casefold(), label.casefold()):
                    combo.setCurrentText(header)
            self.fields[field] = combo
            form.addRow(label, combo)
        layout.addLayout(form)
        preview = QTableWidget(min(10, len(table.rows)), len(table.headers))
        preview.setHorizontalHeaderLabels(table.headers)
        for i, row in enumerate(table.rows[:10]):
            for j, value in enumerate(row):
                preview.setItem(i, j, QTableWidgetItem(value))
        preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Импортировать")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mapping(self) -> dict[str, str]:
        """Вернуть только выбранные колонки."""
        return {field: combo.currentText() for field, combo in self.fields.items() if combo.currentIndex() > 0}
