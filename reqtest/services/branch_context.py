"""Привязка элементов к явно выраженным условиям исходных фрагментов."""
import re
from dataclasses import dataclass
from reqtest.models.domain import Element, ElementType, Requirement
from reqtest.services.source_catalog import build_source_catalog


@dataclass(frozen=True)
class Branch:
    """Условие и две части явно записанной ветви; без догадок о поведении."""
    condition: str
    positive: str
    negative: str | None = None


def parse_branch(text: str) -> Branch | None:
    """Разобрать простую конструкцию; вложенные/неоднозначные оставить человеку."""
    if len(re.findall(r'\bесли\b', text, re.IGNORECASE)) > 1:
        return None
    explicit = re.match(r'^\s*(Если\s+.+?),\s*то\s+(.+)$', text, re.IGNORECASE | re.DOTALL)
    plain = re.match(r'^\s*(Если\s+[^,]+),\s*(.+)$', text, re.IGNORECASE | re.DOTALL)
    invocation = re.match(r'^\s*(При\s+.+?)\s+(?:(?:компонент|модуль|обработчик|подсистема)\s+)?должен\s+(.+)$', text, re.IGNORECASE | re.DOTALL)
    match = explicit or plain or invocation
    if not match:
        return None
    condition, body = match.group(1).strip(), match.group(2).strip()
    if re.search(r'\bесли\b', body, re.IGNORECASE):
        return None
    # Слишком сложное условие со списком/пунктуацией не разбираем по первой запятой.
    if not explicit and not invocation and ',' in re.split(r'\bиначе\b', body, flags=re.IGNORECASE)[0].rstrip(' ,;'):
        return None
    arms = re.split(r'\s*[,;]?\s*\bиначе\b\s*', body, maxsplit=1, flags=re.IGNORECASE)
    return Branch(condition, arms[0].strip(), arms[1].strip() if len(arms)>1 else None)


def _canonical(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip(' .,;').casefold()


def attach_branch_context(requirement: Requirement, elements: list[Element]) -> list[Element]:
    """Добавить пропущенные явные условия и связи применимости к действиям.

    Автоматическое связывание выполняется только по выбранным источникам и
    простому однозначному синтаксису. Оно не подтверждает покрытие.
    """
    result = [e.model_copy(deep=True) for e in elements]
    catalog = build_source_catalog(requirement.text)
    branches = {ref.source_id: (ref, parse_branch(ref.text)) for ref in catalog}
    for element in list(result):
        if element.type not in (ElementType.ACTION, ElementType.CONSTRAINT):
            continue
        contexts = [(ref, branch) for sid,(ref,branch) in branches.items()
                    if branch is not None and any(r.source_id==sid for r in element.source_refs)]
        if len(contexts) != 1:
            if any(re.search(r'\b(?:если|иначе)\b', r.text, re.IGNORECASE) for r in element.source_refs):
                element.review_notes.append('Неоднозначный условный контекст: применимость нужно уточнить вручную')
            continue
        ref, branch = contexts[0]
        # Для «иначе» определять сторону можно только по точному предикату.
        description = re.sub(r'^(?:компонент|модуль|обработчик)\s+должен\s+', '', element.description, flags=re.IGNORECASE)
        positive = _canonical(description) in _canonical(branch.positive)
        negative = bool(branch.negative and _canonical(description) in _canonical(branch.negative))
        if branch.negative is not None and positive == negative:
            element.review_notes.append('Сторона ветви с «иначе» не установлена однозначно; проверьте применимость')
            continue
        condition = next((e for e in result if e.type==ElementType.CONDITION and _canonical(e.description)==_canonical(branch.condition)),None)
        if condition is None:
            used = {e.id for e in result}
            number = 1
            while f'{requirement.id}::E{number:03}' in used:
                number += 1
            condition = Element(id=f'{requirement.id}::E{number:03}', requirement_id=requirement.id,
                type=ElementType.CONDITION, description=branch.condition, source_fragment=ref.text,
                source_refs=[ref], review_notes=['Условие выделено из явной конструкции источника; проверьте смысл'])
            result.append(condition)
        target = element.negated_condition_ids if negative else element.condition_ids
        if condition.id not in target:
            target.append(condition.id)
    return result
