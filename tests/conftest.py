"""Тестовые окна закрываются без блокирующего запроса о несохранённых данных."""
import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def discard_test_windows(monkeypatch):
    original = QMessageBox.question
    def question(parent, title, *args, **kwargs):
        if title == 'Несохранённые изменения':
            return QMessageBox.StandardButton.Discard
        return original(parent, title, *args, **kwargs)
    monkeypatch.setattr(QMessageBox, 'question', question)
