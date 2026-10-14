"""Проверка настоящей точки входа с управляемым завершением цикла событий."""
import os
import tempfile
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from reqtest.main import main


def smoke() -> int:
    """Создать окно и завершить приложение без записи постоянного проекта."""
    with tempfile.TemporaryDirectory(prefix='reqtest-smoke-') as log_dir:
        os.environ['REQTEST_LOG_DIR'] = log_dir
        app = QApplication.instance() or QApplication([])
        QTimer.singleShot(250, app.quit)
        result = main()
        # Закрыть файловый обработчик до удаления временного каталога на Windows.
        import logging
        logging.shutdown()
        return result


if __name__ == '__main__':
    raise SystemExit(smoke())
