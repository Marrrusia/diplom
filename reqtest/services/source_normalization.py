"""Консервативная нормализация ссылок без семантического угадывания."""
import re
from reqtest.models.domain import SourceReference
from reqtest.services.extraction_validation import unsupported_literals


def canonical_contexts(refs: list[SourceReference]) -> list[SourceReference]:
    """Объединить только дословно одинаковые условия; сохранить первый источник."""
    seen = set()
    result = []
    for ref in refs:
        key = ref.text.strip(' .,;').casefold()
        if key not in seen:
            seen.add(key)
            result.append(ref)
    return result


def definition_sources(description: str, selected: list[SourceReference],
                       sources: list[SourceReference]) -> list[SourceReference]:
    """Добавить единственное явное определение имени с общими операндами.

    Числа и просто встречающиеся в другом предложении имена не восстанавливаются.
    Добавленная ссылка остаётся видимой пользователю.
    """
    support = '\n'.join(r.text for r in selected)
    added = []
    for token in unsupported_literals(description, support):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', token):
            continue
        candidates = [r for r in sources if re.search(
            r'\b' + re.escape(token) + r'\s+(?:по\s+формуле|by\s+(?:the\s+)?formula)\b', r.text, re.I)]
        if len(candidates) != 1:
            continue
        candidate = candidates[0]
        names = set(re.findall(r'\b[A-Za-z_][A-Za-z_0-9]*\b', support))
        operands = set(re.findall(r'\b[A-Za-z_][A-Za-z_0-9]*\b', candidate.text)) - {token}
        if names & operands and candidate not in selected and candidate not in added:
            added.append(candidate)
    return added


def result_as_condition(description: str) -> bool:
    """Сигнал ожидаемого эффекта, ошибочно названного предпосылкой."""
    return bool(re.search(r'\b(?:сохраня[ею]т|возвраща[ею]т|вычисля[ею]т|принима[ею]т|'
                          r'должен|должны|must|shall|returns?|stores?)\b', description, re.I))
