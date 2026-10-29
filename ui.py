"""Небольшое окно: требование, исходный ответ и результаты без преобразования."""
import json
import os
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QFormLayout, QLineEdit, QPlainTextEdit, QPushButton, QLabel, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox)
from core import analyze


class Worker(QThread):
    """Сетевой запрос выполняется вне потока интерфейса."""
    result = Signal(object)
    raw = Signal(object)
    error = Signal(str)

    def __init__(self, text: str, server: str, model: str, parent=None):
        super().__init__(parent)
        self.values = text, server, model

    def run(self) -> None:
        """Получить ответ без повторных запросов."""
        try:
            self.result.emit(analyze(*self.values, received=self.raw.emit))
        except Exception:
            self.error.emit('Не удалось выполнить анализ. Проверьте введённые данные.')


class Window(QMainWindow):
    """Простой стенд для проверки выделения одного требования."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Простое выделение требований — 0.2')
        self.resize(1080, 850)
        self.worker = None
        self.run_data = None
        page=QWidget(); self.setCentralWidget(page); layout=QVBoxLayout(page)
        form=QFormLayout()
        self.server=QLineEdit('http://localhost:11434')
        self.model=QLineEdit('qwen35-9b-q5:latest')
        form.addRow('Адрес Ollama',self.server); form.addRow('Модель',self.model)
        layout.addLayout(form)
        layout.addWidget(QLabel('Вставьте одно требование:'))
        self.input=QPlainTextEdit(); self.input.setPlaceholderText('Исходный текст требования целиком…')
        self.input.setMaximumHeight(190); layout.addWidget(self.input)
        self.start_button=QPushButton('Выделить результаты — один запрос')
        self.start_button.clicked.connect(self.start); layout.addWidget(self.start_button)
        self.status=QLabel('Проверяются только структура JSON и дословность цитат. Смысл и полноту проверяет человек.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.tabs=QTabWidget(); layout.addWidget(self.tabs)
        self.table=QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(['Что требуется','При каких условиях','Дословная цитата'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.table,'Результаты модели')
        self.raw=QPlainTextEdit(); self.raw.setReadOnly(True); self.tabs.addTab(self.raw,'Исходный ответ')
        self.notes=QPlainTextEdit(); self.notes.setReadOnly(True); self.tabs.addTab(self.notes,'Замечания')
        self.save_button=QPushButton('Сохранить ответ и диагностику JSON…')
        self.save_button.setEnabled(False); self.save_button.clicked.connect(self.save); layout.addWidget(self.save_button)

    def start(self) -> None:
        """Начать новый анализ; предыдущий результат не показывается как новый."""
        if self.worker is not None:
            return
        if not self.input.toPlainText().strip() or not self.model.text().strip():
            self.status.setText('Введите требование и имя модели.'); return
        self.run_data=None; self.table.setRowCount(0); self.raw.clear(); self.notes.clear()
        self.save_button.setEnabled(False); self.start_button.setEnabled(False)
        for field in (self.input,self.server,self.model): field.setEnabled(False)
        self.status.setText('Один запрос к Ollama выполняется в фоне. Ожидание — до 600 секунд.')
        self.worker=Worker(self.input.toPlainText(),self.server.text(),self.model.text(),self)
        self.worker.raw.connect(self.show_raw); self.worker.result.connect(self.show_result)
        self.worker.error.connect(self.show_error); self.worker.finished.connect(self.finished)
        self.worker.start()

    def show_raw(self, data: dict) -> None:
        """Сделать исходный ответ доступным для экспорта ещё до отображения таблицы."""
        self.run_data=data; self.raw.setPlainText(data.get('raw_response') or '')
        self.save_button.setEnabled(True)

    def show_result(self, data: dict) -> None:
        """Показать все предложения, включая строки с несовпавшими цитатами."""
        self.run_data=data; self.save_button.setEnabled(True)
        self.raw.setPlainText(data.get('raw_response') or '')
        parsed=data.get('parsed')
        if parsed is not None:
            self.table.setRowCount(len(parsed['obligations']))
            for row,item in enumerate(parsed['obligations']):
                values=[item['statement'],'\n'.join(item['conditions']),item['source_fragment']]
                for column,value in enumerate(values): self.table.setItem(row,column,QTableWidgetItem(value))
            self.table.resizeRowsToContents()
        messages=list(data.get('warnings',[]))
        if parsed is not None and parsed['specification_gaps']:
            messages+=['', 'Замечания модели о спецификации (тоже требуют проверки):',*parsed['specification_gaps']]
        self.notes.setPlainText('\n'.join(messages) or 'Структура и дословность цитат прошли проверку. Смысл и полнота не проверялись.')
        if parsed is None:
            self.status.setText('Нет структурированного результата. Смотрите исходный ответ и замечания.')
            self.tabs.setCurrentWidget(self.notes)
        else:
            self.status.setText(f"Предложено результатов: {len(parsed['obligations'])}. Замечаний проверки: {len(data.get('warnings', []))}. Смысл и полноту проверьте вручную.")
            self.tabs.setCurrentWidget(self.table)

    def show_error(self, message: str) -> None:
        self.status.setText(message)

    def finished(self) -> None:
        """Вернуть управление после единственного запроса."""
        worker=self.worker; self.worker=None
        if worker: worker.deleteLater()
        self.start_button.setEnabled(True)
        for field in (self.input,self.server,self.model): field.setEnabled(True)

    def save(self) -> None:
        """Сохранить неизменённый ответ и проверку без настроек подключения."""
        if self.run_data is None: return
        target,_=QFileDialog.getSaveFileName(self,'Сохранить диагностику','simple-diagnostics.json','JSON (*.json)')
        if not target: return
        path=Path(target)
        if not path.suffix: path=path.with_suffix('.json')
        temporary=None
        try:
            fd,name=tempfile.mkstemp(prefix='.simple-',suffix='.json',dir=path.parent)
            os.close(fd); temporary=Path(name)
            temporary.write_text(json.dumps(self.run_data,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temporary,path)
            self.status.setText('Диагностика сохранена: '+str(path))
        except OSError:
            QMessageBox.warning(self,'Сохранение','Не удалось сохранить файл.')
        finally:
            if temporary: temporary.unlink(missing_ok=True)

    def closeEvent(self,event) -> None:
        if self.worker is not None:
            self.status.setText('Запрос ещё выполняется. Закройте окно после его завершения (до 600 секунд).')
            event.ignore()
        else:
            event.accept()


def main() -> int:
    """Запустить окно стенда."""
    app=QApplication.instance() or QApplication(sys.argv)
    window=Window(); window.show()
    return app.exec()
