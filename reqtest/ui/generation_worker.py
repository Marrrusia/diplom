"""Фоновая генерация без доступа к виджетам."""
import logging
from reqtest.ui.analysis_worker import AnalysisWorker
from reqtest.llm.client import LLMClient, LLMError
from reqtest.services.generation import generate_tests, generation_targets, GenerationResult


class GenerationWorker(AnalysisWorker):
    """Рабочий поток с режимом генерации и атомарным результатом."""
    def __init__(self, project, settings, mode, parent=None) -> None:
        super().__init__(project, settings, parent)
        self.mode = mode

    def run(self) -> None:
        """При полном покрытии не создавать даже HTTP-клиент."""
        try:
            if not generation_targets(self.project, self.mode):
                self.result.emit(GenerationResult(project=self.project, generated_count=0,
                    message='Все элементы имеют подтверждённое покрытие. Генерация не требуется'))
                return
            self.result.emit(generate_tests(self.project, LLMClient(self.settings), self.mode,
                self.progress.emit, self.isInterruptionRequested))
        except LLMError as error:
            logging.warning('Ошибка генерации: %s', error)
            self.error.emit(str(error))
        except Exception:
            logging.error('Непредвиденная ошибка генерации')
            self.error.emit('Непредвиденная ошибка генерации. Проект не изменён')
