"""HTTP-клиент Ollama и OpenAI-совместимых серверов."""
import json
from urllib.parse import urlsplit
import httpx
from reqtest.models.domain import LLMSettings


class LLMError(ValueError):
    """Безопасное сообщение без ключей и содержимого HTTP-ответа."""


class LLMClient:
    """Синхронный клиент: вызывать только из фонового потока."""
    def __init__(self, settings: LLMSettings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport
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
        else:
            url = base + '/chat/completions'
            payload = dict(model=self.settings.model, messages=messages, temperature=0,
                           response_format={'type': 'json_object'})
        try:
            with httpx.Client(timeout=httpx.Timeout(180, connect=15), transport=self.transport,
                              follow_redirects=False, headers=headers) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
            content = data['message']['content'] if self.settings.provider == 'ollama' else data['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise TypeError()
            return content
        except httpx.TimeoutException:
            raise LLMError('Сервер не ответил за 180 секунд. Проверьте модель и повторите запрос') from None
        except httpx.HTTPStatusError as error:
            raise LLMError(f'Сервер вернул HTTP {error.response.status_code}. Проверьте адрес, модель и доступ') from None
        except httpx.RequestError:
            raise LLMError('Не удалось подключиться к серверу LLM. Проверьте адрес и запуск сервера') from None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise LLMError('Сервер вернул ответ в неподдерживаемом формате') from None
