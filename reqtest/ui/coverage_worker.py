"""Фоновый анализ покрытия."""
from reqtest.ui.analysis_worker import AnalysisWorker
from reqtest.services.coverage import analyze_coverage
from reqtest.llm.client import LLMClient, LLMError
import logging


class CoverageWorker(AnalysisWorker):
    """Использует сигналы и снимок проекта рабочего потока анализа."""
    def run(self) -> None:
        try:
            self.result.emit(analyze_coverage(self.project, LLMClient(self.settings, cancelled=self.isInterruptionRequested, status=self.status.emit),
                self.progress.emit, self.isInterruptionRequested))
        except LLMError as error:
            logging.warning('Ошибка покрытия: %s', error)
            self.error.emit(str(error))
        except Exception:
            logging.error('Непредвиденная ошибка покрытия')
            self.error.emit('Непредвиденная ошибка покрытия. Проект не изменён')
