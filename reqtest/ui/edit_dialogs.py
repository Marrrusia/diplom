"""Редакторы с отдельными полями и проверкой перед закрытием окна."""
import json
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPlainTextEdit,
    QComboBox, QListWidget, QListWidgetItem, QDialogButtonBox, QLabel, QScrollArea, QWidget, QApplication)
from PySide6.QtCore import Qt
from reqtest.models.domain import Project, Element, ElementType, TestCase, ReviewStatus
from reqtest.services.review import edit_test, edit_element


class EditorDialog(QDialog):
    """Общий механизм сохранения с ошибкой в самом диалоге."""
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.result_project = None
        self.resize(850, 700)
        self.layout = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.fields_widget = QWidget()
        self.form = QFormLayout(self.fields_widget)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.scroll.setWidget(self.fields_widget)
        self.layout.addWidget(self.scroll)
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self.resize(min(900, geometry.width() - 60), min(760, geometry.height() - 60))
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #b00020')

    def finish_form(self) -> None:
        """Добавить объяснение сброса подтверждений и кнопки."""
        note = QLabel('После изменения потребуется повторная проверка. Устаревшие связи покрытия сбрасываются.')
        note.setWordWrap(True)
        self.layout.addWidget(note)
        for editor in self.fields_widget.findChildren(QPlainTextEdit):
            editor.setMinimumHeight(80)
            editor.setMaximumHeight(160)
        self.layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Сохранить')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Отмена')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def save(self) -> None:
        """Проверить полный снимок проекта, не потеряв ввод при ошибке."""
        try:
            self.result_project = self.apply()
        except (ValueError, TypeError) as error:
            self.error_label.setText(str(error))
            return
        self.accept()

    def apply(self) -> Project:
        raise NotImplementedError


class TestEditorDialog(EditorDialog):
    """Редактирование теста без необходимости знать полный JSON модели."""
    def __init__(self, project: Project, test: TestCase, parent=None) -> None:
        super().__init__(project, parent)
        self.test_id = test.id
        self.setWindowTitle('Редактировать тест-кейс')
        self.form.addRow('ID / требование', QLabel(test.id + ' / ' + test.requirement_id))
        self.title = QLineEdit(test.title)
        self.preconditions = QPlainTextEdit('\n'.join(test.preconditions))
        self.inputs = QPlainTextEdit(json.dumps(test.input_data, ensure_ascii=False, indent=2))
        self.steps = QPlainTextEdit('\n'.join(test.steps))
        self.expected = QPlainTextEdit(test.expected_result)
        for label, widget in [('Название', self.title), ('Предусловия (по строкам)', self.preconditions),
            ('Входные данные (JSON-объект)', self.inputs), ('Действия (по строкам)', self.steps), ('Ожидаемый результат', self.expected)]:
            self.form.addRow(label, widget)
        self.elements = QListWidget()
        for element in project.elements:
            if element.requirement_id == test.requirement_id and element.review_status != ReviewStatus.REJECTED:
                item = QListWidgetItem(element.id + ': ' + element.description)
                item.setToolTip(element.id + ": " + element.description)
                item.setData(Qt.ItemDataRole.UserRole, element.id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if element.id in test.element_ids else Qt.CheckState.Unchecked)
                self.elements.addItem(item)
        self.form.addRow('Связанные элементы', self.elements)
        self.finish_form()

    def apply(self) -> Project:
        """Собрать поля и передать атомарную проверку сервису."""
        inputs = json.loads(self.inputs.toPlainText())
        if not isinstance(inputs, dict) or any(not isinstance(v, str) for v in inputs.values()):
            raise ValueError('Входные данные должны быть JSON-объектом со строковыми значениями')
        lines = lambda widget: [line.strip() for line in widget.toPlainText().splitlines() if line.strip()]
        ids = [self.elements.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.elements.count())
               if self.elements.item(i).checkState() == Qt.CheckState.Checked]
        return edit_test(self.project, self.test_id, dict(title=self.title.text(),
            preconditions=lines(self.preconditions), input_data=inputs, steps=lines(self.steps),
            expected_result=self.expected.toPlainText(), element_ids=ids))


class ElementEditorDialog(EditorDialog):
    """Редактор категории, описания и точной исходной цитаты."""
    def __init__(self, project: Project, element: Element, parent=None) -> None:
        super().__init__(project, parent)
        self.element_id = element.id
        self.setWindowTitle('Редактировать проверяемый элемент')
        self.form.addRow('ID / требование', QLabel(element.id + ' / ' + element.requirement_id))
        requirement = next(r for r in project.requirements if r.id == element.requirement_id)
        source = QPlainTextEdit(requirement.text)
        source.setReadOnly(True)
        self.form.addRow('Исходное требование', source)
        self.category = QComboBox()
        self.category.addItems([t.value for t in ElementType])
        self.category.setCurrentText(element.type.value)
        self.description = QPlainTextEdit(element.description)
        self.fragment = QPlainTextEdit(element.source_fragment)
        self.conditions = QPlainTextEdit('\n'.join(element.conditions))
        self.form.addRow('Категория', self.category)
        self.form.addRow('Описание', self.description)
        self.form.addRow('Условия выполнения (по одному на строку)', self.conditions)
        self.form.addRow('Точная цитата', self.fragment)
        self.condition_lists = []
        for label, selected in [('При истинности условий', element.condition_ids),
                                ('При ложности условий (иначе)', element.negated_condition_ids)]:
            choices = QListWidget()
            for condition in project.elements:
                if condition.type == ElementType.CONDITION and condition.requirement_id == element.requirement_id and condition.id != element.id:
                    item = QListWidgetItem(condition.id + ': ' + condition.description)
                    item.setToolTip(condition.description)
                    item.setData(Qt.ItemDataRole.UserRole, condition.id)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if condition.id in selected else Qt.CheckState.Unchecked)
                    choices.addItem(item)
            self.condition_lists.append(choices)
            if choices.count():
                self.form.addRow(label, choices)
        self.finish_form()

    def apply(self) -> Project:
        return edit_element(self.project, self.element_id, dict(type=self.category.currentText(),
            description=self.description.toPlainText(), source_fragment=self.fragment.toPlainText(), conditions=[line.strip() for line in self.conditions.toPlainText().splitlines() if line.strip()],
            **{field: [choices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(choices.count())
                       if choices.item(i).checkState() == Qt.CheckState.Checked]
               for field, choices in zip(('condition_ids', 'negated_condition_ids'), self.condition_lists)}))
