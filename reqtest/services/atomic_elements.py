"""Разбиение явных перечислений предикатов; не разделяет союзы внутри аргументов."""
import re
from dataclasses import dataclass
from reqtest.models.domain import ElementType

# Ограниченный словарь предикатов, а не попытка угадать любую русскую грамматику.
VERBS = ('сохранить', 'вернуть', 'оставить', 'вызвать', 'установить', 'сбросить',
         'включить', 'выключить', 'записать', 'прочитать', 'передать', 'очистить',
         'запретить', 'разрешить', 'увеличить', 'уменьшить', 'вычислить')
PREDICATE = r'(?:' + '|'.join(VERBS) + r')\b'
MODAL = r'(?:(?:компонент|модуль|обработчик)\s+должен\s+)'


@dataclass(frozen=True)
class AtomicDescription:
    """Самостоятельный проверяемый предикат со ссылкой на общий источник."""
    type: ElementType
    description: str


def split_description(kind: ElementType, description: str) -> list[AtomicDescription]:
    """Делить только явные команды, соединённые «и», «а также» либо «;».

    Не расширяет исходные факты. Сложные конструкции, не соответствующие
    шаблону, сохраняются целиком и проверяются существующими правилами.
    """
    original = AtomicDescription(kind, description)
    if kind not in (ElementType.ACTION, ElementType.CONSTRAINT):
        return [original]
    body = description.strip()
    condition = None
    conditional = re.match(r'^если\s+([^,]+),\s*(.+)$', body, re.IGNORECASE | re.DOTALL)
    if conditional:
        condition = 'Если ' + conditional.group(1)
        body = conditional.group(2)
    body = re.sub(r'^' + MODAL, '', body, flags=re.IGNORECASE)
    if not re.match(r'^' + PREDICATE, body, re.IGNORECASE):
        return [original]
    # Не выделять действие из оборота с неучтённым отрицанием или вложенной ветвью.
    if re.search(r'\b(?:не|если|иначе)\b', body, re.IGNORECASE):
        return [original]
    parts = re.split(r'\s+(?:и|а также)\s+(?=' + PREDICATE + r')|;\s*(?=' + PREDICATE + r')', body, flags=re.IGNORECASE)
    if len(parts) < 2:
        return [original]
    if any(not re.match(r'^' + PREDICATE, part.strip(), re.IGNORECASE) for part in parts):
        return [original]
    result = [AtomicDescription(ElementType.CONDITION, condition)] if condition else []
    for part in parts:
        part = part.strip().rstrip(';,')
        category = ElementType.CONSTRAINT if re.search(r'^оставить\b.*без изменени', part, re.IGNORECASE) else ElementType.ACTION
        result.append(AtomicDescription(category, part))
    return result
