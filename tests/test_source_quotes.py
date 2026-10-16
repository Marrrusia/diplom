"""Исправление цитат сохраняет точный источник, не меняя факты."""
import json
import pytest
from reqtest.services.source_quotes import restore_quote
from reqtest.services.extraction import extract_project
from reqtest.models.domain import Project, Requirement
from reqtest.llm.client import LLMError


@pytest.mark.parametrize('text,fragment,expected', [
    ('Поле  value\nравно 100', 'Поле value равно 100', 'Поле  value\nравно 100'),
    ('Вернуть «OK»', 'Вернуть "OK"', 'Вернуть «OK»'),
    ('value >= 10', 'value > 10', None),
    ('value = 100', 'value = 10', None),
    ('Вызвать Foo()', 'Вызвать foo()', None),
    ('от 0 до 100 включительно', '0..100', None),
    ('Поле value равно 100', 'Поле ... равно 100', None),
    ('Вернуть «OK»; Вернуть “OK”', 'Вернуть "OK"', None),
])
def test_safe_quote_restoration(text, fragment, expected):
    assert restore_quote(text, fragment) == expected


def test_screenshot_russian_sentence_case_restored():
    text = 'Если elapsed_ms меньше 10, PollSensor вызываться не должен.'
    assert restore_quote(text, 'если elapsed_ms меньше 10') == 'Если elapsed_ms меньше 10'
    assert restore_quote(text, 'если Elapsed_ms меньше 10') is None
    assert restore_quote(text, 'если elapsed_ms меньше 100') is None
