"""Фоновое чтение, запись SQLite и экспорт отчёта."""
import logging
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from reqtest.models.domain import Project
from reqtest.storage.sqlite_project import load_project, save_project
from reqtest.exporters.xlsx_report import export_report


class FileWorker(QThread):
    """Операция с неизменяемым снимком; запись завершается атомарно."""
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, operation: str, path: Path, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.operation = operation
        self.path = path
        self.project = project.model_copy(deep=True)

    def run(self) -> None:
        """Отправить результат только после полного успеха операции."""
        try:
            if self.operation == 'open':
                value = load_project(self.path)
            elif self.operation == 'save':
                save_project(self.project, self.path)
                value = self.project
            elif self.operation == 'export':
                export_report(self.project, self.path)
                value = None
            else:
                raise ValueError('Неизвестная файловая операция')
            self.result.emit((self.operation, self.path, value))
        except (ValueError, OSError) as error:
            logging.warning('Файловая операция не выполнена: %s', type(error).__name__)
            self.error.emit(str(error))
        except Exception:
            logging.error('Непредвиденная ошибка файловой операции')
            self.error.emit('Не удалось выполнить файловую операцию. Проект в памяти не изменён')
