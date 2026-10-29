"""SQLite-файл проекта: проверенный снимок, атомарная замена, без настроек LLM."""
import os
import json
from contextlib import closing
import sqlite3
import tempfile
from pathlib import Path
from reqtest.models.domain import Project

APPLICATION_ID = 0x52515453
FILE_VERSION = 1


class ProjectFileError(ValueError):
    """Неподдерживаемый или повреждённый файл проекта."""


def load_project(path: Path) -> Project:
    """Открыть только для чтения и проверить формат/все ссылки до возврата."""
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            if connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
                raise ProjectFileError('Этот файл не является проектом ReqTest')
            if connection.execute('PRAGMA user_version').fetchone()[0] != FILE_VERSION:
                raise ProjectFileError('Версия файла проекта не поддерживается')
            rows = connection.execute('SELECT payload FROM project_snapshot WHERE id=1').fetchall()
            if len(rows) != 1:
                raise ProjectFileError('В файле отсутствует снимок проекта')
            payload = json.loads(rows[0][0])
            if 'analysis_incomplete' not in payload:
                payload['analysis_incomplete']=[r['id'] for r in payload.get('requirements',[])]
                for rid in payload['analysis_incomplete']:
                    payload.setdefault('analysis_notes',{}).setdefault(rid,[]).append('В старом проекте не записана проверка полноты; требуется ручная проверка')
            project = Project.model_validate(payload)
            if project.schema_version != 1:
                raise ProjectFileError('Версия данных проекта не поддерживается')
            return project
    except (sqlite3.Error, ValueError, OSError) as error:
        if isinstance(error, ProjectFileError):
            raise
        raise ProjectFileError('Не удалось открыть проект: файл повреждён, недоступен или содержит некорректные данные') from None


def save_project(project: Project, path: Path) -> None:
    """Сохранить в соседний временный SQLite-файл, затем атомарно заменить целевой."""
    validated = Project.model_validate_json(project.model_dump_json())
    if validated.schema_version != 1:
        raise ProjectFileError('Версия данных проекта не поддерживается')
    path = path.resolve()
    if path.exists():
        load_project(path)  # Не перезаписывать чужие базы или повреждённые проекты.
    descriptor, temporary = tempfile.mkstemp(prefix='.reqtest-', suffix='.sqlite', dir=path.parent)
    os.close(descriptor)
    temp_path = Path(temporary)
    try:
        with closing(sqlite3.connect(temp_path)) as connection:
            connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
            connection.execute(f'PRAGMA user_version={FILE_VERSION}')
            connection.execute('CREATE TABLE project_snapshot (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            connection.execute('INSERT INTO project_snapshot VALUES (1, ?)', (validated.model_dump_json(),))
            connection.commit()
        load_project(temp_path)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
