# Установка и запуск на Windows 11

## Требования

Windows 11 x64; Python 3.11+; PyCharm; интернет для установки пакетов и первой
загрузки модели. Для воспроизводимой проверки рекомендуются Python 3.11/3.12.
Основное приложение не требует GPU. Для Ollama объём RAM и скорость зависят
от модели; для компьютера с ограниченными ресурсами можно попробовать
`qwen2.5:3b`, вместо `qwen2.5:7b`. Качество выделения может измениться.

## Установка

1. Скачайте Python с https://www.python.org/downloads/windows/ . Выберите
   Windows installer (64-bit); отметьте Add python.exe to PATH.
2. Установите PyCharm: https://www.jetbrains.com/pycharm/download/?section=windows .
   Бесплатных возможностей достаточно.
3. Распакуйте архив в отдельную папку, например `C:\Projects\diplom`.
   При обновлении не удаляйте свои SQLite-проекты. `.venv` в архив не входит.
4. Откройте папку через File → Open.
5. Settings → Python Interpreter → Add Interpreter → Add Local Interpreter:
   создайте Virtualenv `.venv`, указав установленный Python как Base interpreter.
6. В терминале проекта выполните:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

Альтернатива без предварительного Virtualenv:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Можно использовать `scripts\setup_windows.ps1`. Скрипт выбирает Python через
`py -3` либо `python`; другой интерпретатор задаётся параметром
`-PythonExecutable "C:\путь\python.exe"`. Если выполнение PowerShell-скриптов
заблокировано политикой компьютера, используйте команды выше. Изменять
системную политику выполнения не требуется.

## Конфигурация PyCharm

Run → Edit Configurations → Python:

- Script path: `main.py` в папке проекта.
- Python interpreter: `.venv\Scripts\python.exe`.
- Working directory: папка `diplom`.
- Переменная QT_QPA_PLATFORM не должна иметь значение offscreen для рабочего GUI.

Нажмите Run. Для запуска в терминале:

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe main.py
```

## Ollama

Установщик: https://ollama.com/download/windows . Альтернатива:

```powershell
winget install --id Ollama.Ollama --exact
```

Перезапустите терминал, затем:

```powershell
ollama --version
ollama pull qwen2.5:7b
ollama list
```

Если сервер не запущен, выполните `ollama serve` и оставьте его работающим.
В приложении: тип `ollama`, адрес `http://localhost:11434`, модель точно как
в `ollama list`. Локальный сервер не требует API-ключа.

Для другого OpenAI-совместимого сервера выберите `openai`, адрес API с `/v1`,
например `http://localhost:1234/v1`, и имя модели. Сервер должен поддерживать
chat/completions и response_format json_object. Ключ вводится только при
необходимости; он действует в текущем сеансе и не сохраняется в SQLite.

## Проверка установки

```powershell
.\scripts\verify_windows.ps1
```

С установленным Ollama:

```powershell
.\scripts\verify_windows.ps1 -CheckOllama
```

Проверяются зависимости, pytest, точка входа Qt, при выборе — доступность
Ollama и наличие моделей. Проверка `/api/tags` не доказывает качество генерации.
Ручной сценарий Windows находится в [validation.md](validation.md).

## Типичные ошибки

| Ошибка | Действие |
| --- | --- |
| No such file: git.exe | Для архива Git не нужен. Для GitHub установите Git for Windows и задайте путь в Settings → Version Control → Git |
| Неизвестно, где Python | Выполните `py -c "import sys; print(sys.executable)"` или аналогичную команду через `python` |
| ModuleNotFoundError | Проверьте интерпретатор PyCharm и выполните pip install через `.venv\Scripts\python.exe` |
| Неизвестное требование при импорте теста | Сначала загрузите требования; проверьте точное совпадение requirement_id и сопоставление колонок |
| После запуска не видно окно | Удалите QT_QPA_PLATFORM=offscreen; этот режим только для тестов |
| Не удалось подключиться к LLM | Проверьте сервер, порт, имя модели; Ollama должен работать на том компьютере, чей адрес указан |
| HTTP 404 | Для Ollama используйте корень сервера; для OpenAI API — базовый адрес с /v1, без /chat/completions |
| HTTP 401/403 | Проверьте доступ и ключ в настройках; не публикуйте ключ в репозитории |
| Модель вернула некорректный JSON | Повторите запрос/выберите другую модель; результат не применяется при ошибке |
| DLL load failed для PySide6 | Проверьте x64 Python, переустановите пакеты в новом Virtualenv; при необходимости установите Microsoft Visual C++ Redistributable с официального сайта Microsoft |
| Excel блокирует замену отчёта | Закройте XLSX в Excel либо выберите новое имя |
| Процент 0%, модель пишет «покрыт» | Нужна ручная проверка и принятие связей; принятие одного теста не подтверждает покрытие |

Журнал: `%USERPROFILE%\.reqtest\logs\application.log`. Для другого каталога
задайте переменную `REQTEST_LOG_DIR`. Для диагностики сообщайте текст ошибки,
версию Python и модель, не API-ключ.
