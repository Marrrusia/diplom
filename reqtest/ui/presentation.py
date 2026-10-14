"""Общие правила отображения таблиц и полных текстов без бизнес-логики."""
from enum import Enum
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QTableWidget, QLineEdit,
                              QSplitter, QGridLayout, QPushButton, QTextEdit, QVBoxLayout)


def configure_table(table: QTableWidget, matrix: bool = False) -> None:
    """Ограничить ширины, разрешить перенос текста и выбор с клавиатуры."""
    table.setWordWrap(True)
    table.setAlternatingRowColors(True)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems if matrix else QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    table.setMinimumHeight(140)
    table.setAccessibleName('Матрица покрытия' if matrix else 'Таблица записей')


def fit_table(table: QTableWidget, matrix: bool = False) -> None:
    """Компактные столбцы; полный текст доступен в панели просмотра и подсказке."""
    for column in range(table.columnCount()):
        heading = table.horizontalHeaderItem(column)
        title = heading.text() if heading else ''
        width = 280 if title in ('Текст', 'Описание', 'Цитата', 'Действия', 'Ожидаемый результат', 'Название') else 190
        table.setColumnWidth(column, 180 if matrix else width)
    table.resizeRowsToContents()
    for row in range(table.rowCount()):
        table.setRowHeight(row, max(40, min(100, table.rowHeight(row))))
    if matrix:
        table.verticalHeader().setMaximumWidth(320)
    colors = {'покрыт': '#d4edda', 'не покрыт': '#f8d7da', 'требует проверки': '#fff3cd',
              'принят': '#d4edda', 'отклонён': '#f8d7da', 'ожидает проверки': '#fff3cd'}
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item:
                item.setToolTip(item.text())
                if item.text() in colors:
                    item.setBackground(QColor(colors[item.text()]))
                    item.setForeground(QColor('#202020'))


def filter_table(table: QTableWidget, query: str) -> None:
    """Скрыть строки без совпадений; индексы моделей при этом не меняются."""
    query = query.casefold().strip()
    for row in range(table.rowCount()):
        text = ' '.join(table.item(row, col).text() for col in range(table.columnCount()) if table.item(row, col))
        table.setRowHidden(row, query not in text.casefold())
    if table.currentRow() >= 0 and table.isRowHidden(table.currentRow()):
        table.clearSelection()
        table.setCurrentCell(-1, -1)


def readable_record(record, labels: dict[str, str]) -> str:
    """Показать модель по именованным полям вместо необработанного JSON."""
    parts = []
    for field, label in labels.items():
        value = getattr(record, field)
        if isinstance(value, Enum):
            value = value.value
        elif isinstance(value, list):
            value = '\n'.join(f'{i + 1}. {entry}' for i, entry in enumerate(value)) or 'Не указано'
        elif isinstance(value, dict):
            value = '\n'.join(f'{key}: {val}' for key, val in value.items()) or 'Не указано'
        parts.append(f'{label}:\n{value if value is not None else "Не указано"}')
    return '\n\n'.join(parts)


def enhance_page(layout: QVBoxLayout) -> None:
    """Сгруппировать кнопки и дать пользователю менять размер панелей."""
    buttons = [layout.itemAt(i).widget() for i in range(layout.count()) if isinstance(layout.itemAt(i).widget(), QPushButton)]
    if buttons:
        toolbar = QGridLayout()
        for i, button in enumerate(buttons):
            layout.removeWidget(button)
            toolbar.addWidget(button, i // 3, i % 3)
        layout.insertLayout(0, toolbar)
    panels = [(i, layout.itemAt(i).widget()) for i in range(layout.count())
              if isinstance(layout.itemAt(i).widget(), (QTableWidget, QTextEdit))]
    if len(panels) > 1:
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        for _, panel in panels:
            layout.removeWidget(panel)
            splitter.addWidget(panel)
        splitter.setSizes([320] + [180] * (len(panels) - 1))
        layout.insertWidget(panels[0][0], splitter, 1)
