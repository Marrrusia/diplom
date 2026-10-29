"""Фоновое выполнение анализа без обращения к виджетам."""
import logging
from PySide6.QtCore import QThread, Signal
from reqtest.llm.client import LLMClient, LLMError
from reqtest.services.extraction import extract_project


class AnalysisWorker(QThread):
    """Один атомарный запуск анализа проекта."""
    result = Signal(object)
    error = Signal(str)
    status = Signal(str)
    progress = Signal(int, int)

    def __init__(self, project, settings, parent=None) -> None:
        super().__init__(parent)
        self.project = project.model_copy(deep=True)
        self.settings = settings

    def run(self) -> None:
        """Отправить проверенный результат в GUI-поток."""
        try:
            result = extract_project(self.project, LLMClient(self.settings, cancelled=self.isInterruptionRequested, status=self.status.emit), self.progress.emit,
                                     self.isInterruptionRequested)
            self.result.emit(result)
        except LLMError as error:
            logging.warning('Анализ LLM завершился ошибкой: %s', error)
            self.error.emit(str(error))
        except Exception:
            logging.error('Непредвиденная ошибка анализа LLM')
            self.error.emit('Непредвиденная ошибка анализа. Проект не изменён')
