"""Ограниченные факты из данных теста; неизвестное не считается ложным.

Только закрытая грамматика сравнений и явных присваиваний. Код и выражения
из документов никогда не исполняются. Факты не подтверждают покрытие сами.
"""
import re
from decimal import Decimal
from reqtest.models.domain import Element, ElementType, Project, TestCase

NUMBER = r'[+-]?\d+(?:[.,]\d+)?'
NAME = r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*'


def condition_truth(description: str, inputs: dict[str, str]) -> bool | None:
    """Вычислить простое числовое условие; сложная грамматика даёт None."""
    text = re.sub(r'^если\s+', '', description.strip(' .'), flags=re.I)
    # Сначала ИЛИ: И имеет более высокий приоритет. Скобки не угадываем.
    if '(' in text or ')' in text:
        return None
    for operator, combine in [(r'\s+или\s+(?!равно\b)', any), (r'\s+и\s+', all)]:
        parts = re.split(operator, text, flags=re.I)
        if len(parts) > 1:
            # Эллипсис «x меньше 0 или больше 100»: имя наследуется явно.
            first = re.match(rf'^({NAME})\s+', parts[0])
            values = [condition_truth((first[1]+' ' if first and re.match(r'^(?:меньше|больше|равно|не равно)\b', part, re.I) else '')+part, inputs) for part in parts]
            if all(v is not None for v in values):
                return combine(values)
            return None
    bounded = re.fullmatch(rf'({NAME})\s+в диапазоне от\s+({NUMBER})\s+до\s+({NUMBER})\s+включительно', text, re.I)
    comparison = re.fullmatch(rf'({NAME})\s*(меньше или равно|больше или равно|не равно|меньше|больше|равно|<=|>=|==|!=|<|>)\s*({NUMBER})', text, re.I)
    match = bounded or comparison
    if match is None or match[1] not in inputs or not re.fullmatch(NUMBER, inputs[match[1]].strip()):
        return None
    value = Decimal(inputs[match[1]].strip().replace(',', '.'))
    if bounded:
        low, high = (Decimal(bounded[i].replace(',', '.')) for i in (2, 3))
        return low <= value <= high if low <= high else None
    limit = Decimal(comparison[3].replace(',', '.'))
    return {'меньше': value < limit, '<': value < limit, 'больше': value > limit, '>': value > limit,
            'равно': value == limit, '==': value == limit, 'не равно': value != limit, '!=': value != limit,
            'меньше или равно': value <= limit, '<=': value <= limit,
            'больше или равно': value >= limit, '>=': value >= limit}[comparison[2].lower()]


def assignments(text: str) -> dict[str, str]:
    """Однозначные явные присваивания; повторное разное значение исключается."""
    found: dict[str, set[str]] = {}
    for m in re.finditer(rf'(?<![\w.])({NAME})\s*=(?!=)\s*({NUMBER}|{NAME})(?![\w.])', text):
        found.setdefault(m[1], set()).add(m[2])
    return {key: next(iter(values)) for key, values in found.items() if len(values) == 1}


def coverage_facts(project: Project, element: Element, test: TestCase) -> dict:
    """Подготовить объяснимые факты для модели и независимой сверки решения."""
    by_id = {e.id: e for e in project.elements}
    conditions = []
    for ids, required in [(element.condition_ids, True), (element.negated_condition_ids, False)]:
        for cid in ids:
            truth = condition_truth(by_id[cid].description, test.input_data)
            conditions.append({'id': cid, 'required': required, 'actual': truth})
    applicable = (all(c['actual'] == c['required'] for c in conditions)
                  if conditions and all(c['actual'] is not None for c in conditions) else None)
    if any(c['actual'] is not None and c['actual'] != c['required'] for c in conditions):
        applicable = False
    own = condition_truth(element.description, test.input_data) if element.type == ElementType.CONDITION else None
    trigger = re.fullmatch(rf'При вызове\s+({NAME})', element.description.strip(' .'), re.I) if element.type == ElementType.CONDITION else None
    trigger_matches = bool(trigger and any(re.search(rf'\b(?:вызвать|вызов)\s+{re.escape(trigger[1])}\s*(?:\(|$)', step, re.I) for step in test.steps))
    before = assignments('\n'.join(test.preconditions))
    after = assignments(test.expected_result)
    unchanged = re.fullmatch(rf'оставить\s+({NAME})\s+без изменения', element.description.strip(' .'), re.I)
    state = None
    if unchanged and unchanged[1] in before and unchanged[1] in after:
        a, b = before[unchanged[1]], after[unchanged[1]]
        state = Decimal(a.replace(',', '.')) == Decimal(b.replace(',', '.')) if re.fullmatch(NUMBER,a) and re.fullmatch(NUMBER,b) else a == b
    returned = re.fullmatch(rf'вернуть\s+({NAME})', element.description.strip(' .'), re.I)
    result_matches = bool(returned and re.search(rf'\b(?:возвращён|возвращен|вернуть)\s+{re.escape(returned[1])}\b', test.expected_result, re.I))
    return {'conditions': conditions, 'applicable': applicable, 'own_condition': own,
            'before': before, 'expected_after': after, 'state_unchanged': state,
            'explicit_return_matches': result_matches, 'explicit_trigger_matches': trigger_matches}


def decision_conflicts(status: str, facts: dict, test: TestCase) -> list[str]:
    """Противоречивые выводы переводятся в проверку, никогда в автоподтверждение."""
    if status == 'покрыт' and (facts['applicable'] is False or facts['own_condition'] is False or facts['state_unchanged'] is False):
        return ['Решение модели противоречит вычисленному условию или явному изменению состояния']
    evidence = facts['state_unchanged'] is True or facts['explicit_return_matches']
    if status == 'не покрыт' and test.steps and test.expected_result and (facts['own_condition'] is True or facts['explicit_trigger_matches'] or (facts['applicable'] is True and evidence)):
        return ['Отрицательное решение требует проверки: вход удовлетворяет условию, в тесте есть соответствующие ожидаемые результаты']
    return []
