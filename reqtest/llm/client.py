"""HTTP-клиент Ollama и OpenAI-совместимых серверов."""
import json
import math
import re
import time
from urllib.parse import urlsplit
import httpx
from reqtest.models.domain import LLMSettings


class LLMError(ValueError):
    """Безопасное сообщение без ключей и содержимого HTTP-ответа."""


class LLMClient:
    """Синхронный клиент: вызывать только из фонового потока."""
    def __init__(self, settings: LLMSettings, transport: httpx.BaseTransport | None = None, *, cancelled=None, status=None) -> None:
        self.settings = settings
        self.transport = transport
        self.cancelled = cancelled
        self.status = status
        url = urlsplit(settings.base_url)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise LLMError('Укажите HTTP(S)-адрес без ключей, параметров и учётных данных')
        if settings.provider not in ('ollama', 'openai'):
            raise LLMError('Неизвестный тип сервера')
        if not settings.model.strip():
            raise LLMError('Укажите название модели')

    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        """Запросить JSON с ограниченным временем ожидания, сохраняя TLS-проверку."""
        headers = {}
        if self.settings.api_key:
            headers['Authorization'] = 'Bearer ' + self.settings.api_key.get_secret_value()
        base = self.settings.base_url.rstrip('/')
        if self.settings.provider == 'ollama':
            url = base + '/api/chat'
            payload = dict(model=self.settings.model, messages=messages, stream=False, format=schema,
                           options={'temperature': 0})
            if self.settings.model.split(':')[0].casefold() == 'qwen35-9b-q5':
                payload.pop('options')
                payload['think'] = False
        else:
            url = base + '/chat/completions'
            payload = dict(model=self.settings.model, messages=messages, temperature=0,
                           response_format={'type': 'json_object'})
        timeout_seconds = 600 if self.settings.provider == 'ollama' and self.settings.model.split(':')[0].casefold() == 'qwen35-9b-q5' else 180
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=15), transport=self.transport,
                              follow_redirects=False, headers=headers) as client:
                for retry in range(3):
                    if self.cancelled and self.cancelled():
                        raise LLMError('Операция отменена; проект не изменён')
                    response = client.post(url, json=payload)
                    if response.status_code != 429:
                        break
                    delay = self.rate_limit_delay(response, 3 * 2**retry)
                    if retry == 2 or delay > 60:
                        raise LLMError(f'Лимит LLM: HTTP 429. Повторите не раньше чем через {math.ceil(delay)} секунд')
                    self.wait_for_limit(delay)
                response.raise_for_status()
                data = response.json()
            content = data['message']['content'] if self.settings.provider == 'ollama' else data['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise TypeError()
            return content
        except httpx.TimeoutException:
            raise LLMError(f'Сервер не ответил за {timeout_seconds} секунд. Проверьте модель и повторите запрос') from None
        except httpx.HTTPStatusError as error:
            raise LLMError(f'Сервер вернул HTTP {error.response.status_code}. Проверьте адрес, модель и доступ') from None
        except httpx.RequestError:
            raise LLMError('Не удалось подключиться к серверу LLM. Проверьте адрес и запуск сервера') from None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise LLMError('Сервер вернул ответ в неподдерживаемом формате') from None


    @staticmethod
    def rate_limit_delay(response, fallback: float) -> float:
        """Числовой Retry-After или безопасное извлечение длительности из сообщения."""
        try:
            delay=float(response.headers.get('retry-after',''))
        except ValueError:
            try:
                message=response.json().get('error',{}).get('message','')
            except (ValueError,AttributeError):
                message=''
            match=re.search(r'try again in\s+(\d+(?:\.\d+)?)s',message if isinstance(message,str) else '',re.I)
            delay=float(match[1]) if match else fallback
        return delay if math.isfinite(delay) and delay>=0 else fallback

    def wait_for_limit(self, delay: float) -> None:
        """Ожидание в рабочем потоке с частой проверкой отмены."""
        remaining=delay+0.2
        shown=None
        while remaining>0:
            if self.cancelled and self.cancelled():
                raise LLMError('Операция отменена во время ожидания лимита; проект не изменён')
            seconds=math.ceil(remaining)
            if self.status and seconds!=shown:
                self.status(f'Лимит LLM: повтор через {seconds} с. Можно отменить операцию')
                shown=seconds
            step=min(remaining,0.2)
            time.sleep(step)
            remaining-=step
        if self.status:
            self.status('Повторный запрос после ожидания лимита LLM…')
