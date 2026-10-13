"""Точка входа настольного приложения."""
import logging
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from reqtest.ui.main_window import MainWindow


def main() -> int:
    """Настроить журналирование и запустить цикл событий Qt."""
    log_dir = Path(os.environ.get("REQTEST_LOG_DIR", str(Path.home() / ".reqtest" / "logs")))
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "application.log", encoding="utf-8",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Анализ покрытия требований")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
