"""Сохранение диагностики без настроек подключения."""
from reqtest import __version__
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


class DiagnosticClient:
    """Сохранить все ответы до проверки результата."""
    def __init__(self, client, project):
        self.client = client
        self.settings = getattr(client, 'settings', None)
        root = Path(os.environ.get('REQTEST_LOG_DIR', str(Path.home()/'.reqtest'/'logs')))
        self.path = root / ('extraction-diagnostics-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid4().hex[:8] + '.json')
        self.data = dict(version=__version__, format='simple-obligations-project-1', created_at=datetime.now(timezone.utc).isoformat(), model=getattr(self.settings,'model',''), provider=getattr(self.settings,'provider',''), requirements=[r.model_dump(mode='json') for r in project.requirements], attempts=[], status='running')
        self.saved = False

    def save(self):
        """Атомарная запись; сбой диагностики не прерывает анализ."""
        temporary = self.path.with_suffix('.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self.data, ensure_ascii=False, indent=2)
            secret = getattr(self.settings, 'api_key', None)
            if secret:
                content = content.replace(secret.get_secret_value(), '[REDACTED]')
            temporary.write_text(content, encoding='utf-8')
            os.replace(temporary, self.path)
            self.saved = True
        except OSError:
            self.saved = False
            logging.warning('Не удалось сохранить диагностику выделения')
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def complete(self, messages, schema):
        """Записать точный ответ без заголовков и адреса сервера."""
        entry = dict(messages=[dict(m) for m in messages], schema=schema, response='', errors=[])
        self.data['attempts'].append(entry)
        try:
            response = self.client.complete(messages, schema)
            entry['response'] = response
            return response
        except Exception as error:
            from reqtest.llm.client import LLMError
            entry['errors'] = [str(error) if isinstance(error, LLMError) else type(error).__name__]
            raise
        finally:
            self.save()

    def record_validation(self, requirement_id, attempt, problems):
        """Связать причины отказа с ответом."""
        self.data['attempts'][-1].update(requirement_id=requirement_id, attempt=attempt, errors=list(problems))
        self.save()
