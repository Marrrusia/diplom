"""Восстановление точной цитаты только при различиях пробелов, кавычек и регистра русских букв."""


def _normalized(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Нормализовать оформление с сохранением координат исходных символов."""
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    quotes = {'«': '"', '»': '"', '“': '"', '”': '"', '„': '"', '‘': "'", '’': "'"}
    for index, char in enumerate(text):
        value = ' ' if char.isspace() else quotes.get(char, char)
        if 'А' <= value <= 'Я' or value == 'Ё':
            value = value.lower()
        if value == ' ' and chars and chars[-1] == ' ':
            spans[-1] = (spans[-1][0], index + 1)
        else:
            chars.append(value)
            spans.append((index, index + 1))
    return ''.join(chars), spans


def _whole_tokens(text: str, start: int, end: int) -> bool:
    """Цитата не должна обрезать число или идентификатор по краям."""
    token = lambda char: char.isalnum() or char == '_'
    return not ((start > 0 and token(text[start]) and token(text[start - 1]))
                or (end < len(text) and token(text[end - 1]) and token(text[end])))


def restore_quote(text: str, fragment: str) -> str | None:
    """Не исправлять числа, латинские имена, операторы или перефразирование."""
    if fragment:
        start = 0
        while (index := text.find(fragment, start)) != -1:
            if _whole_tokens(text, index, index + len(fragment)):
                return fragment
            start = index + 1
    normalized, spans = _normalized(text)
    target = _normalized(fragment)[0].strip()
    if not target:
        return None
    matches = set()
    start = 0
    while (index := normalized.find(target, start)) != -1:
        end = index + len(target) - 1
        if _whole_tokens(text, spans[index][0], spans[end][1]):
            matches.add(text[spans[index][0]:spans[end][1]])
        start = index + 1
    return next(iter(matches)) if len(matches) == 1 else None
