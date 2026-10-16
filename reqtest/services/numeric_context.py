"""Ограниченная проверка явно заданного числового диапазона и конкретного входа."""
import re
from decimal import Decimal, InvalidOperation
from reqtest.models.domain import Element, ElementType, TestCase

NUMBER = r'[+-]?\d+(?:[.,]\d+)?'
DOMAIN = re.compile(rf'\b(?P<name>[A-Za-z_][A-Za-z_0-9]*)\s+в диапазоне от (?P<low>{NUMBER}) до (?P<high>{NUMBER}) включительно')


def numeric_context(requirement: str, element: Element, test: TestCase) -> dict:
    """Различать параметр и его значение, не исполнять произвольные выражения."""
    contexts = []
    dispensable = set()
    issues = []
    for match in DOMAIN.finditer(requirement):
        name = match['name']
        raw = test.input_data.get(name)
        if raw is None or not re.fullmatch(NUMBER, raw.strip()):
            continue
        try:
            low, high, value = [Decimal(v.replace(',', '.')) for v in (match['low'], match['high'], raw.strip())]
        except InvalidOperation:
            continue
        if low > high:
            continue
        inside = low <= value <= high
        position = 'нижняя граница' if value == low else 'верхняя граница' if value == high else 'внутри' if inside else 'вне'
        contexts.append({'parameter': name, 'value': raw, 'lower': match['low'], 'upper': match['high'],
                         'inside': inside, 'position': position, 'range_fully_tested': False})
        fragment = '\n'.join(ref.text for ref in element.source_refs) if element.source_refs else element.source_fragment
        outside_condition = re.search(rf'Если\s+{re.escape(name)}\s+меньше\s+{re.escape(match["low"])}\s+или\s+больше\s+{re.escape(match["high"])}\s*,[^.]+', requirement, re.IGNORECASE)
        outside_fragment = bool(outside_condition and fragment.rstrip('. ') in outside_condition.group(0))
        inside_fragment = bool(outside_condition and fragment.rstrip('. ') in requirement[:outside_condition.start()] and not outside_fragment)
        bounded_fragment = bool(name in fragment and re.search(r'в диапазоне|меньше|больше', fragment, re.IGNORECASE))
        branch_matches = (not inside) if outside_fragment else inside
        # Не требуем буквального присутствия границ в каждом конкретном тесте
        # условия ветви. Это не означает проверки всего диапазона.
        if element.type != ElementType.RANGE and bounded_fragment and branch_matches:
            dispensable.update((match['low'], match['high']))
        if (outside_fragment and inside) or ((bounded_fragment or inside_fragment) and not outside_fragment and not inside):
            issues.append(f'Вход {name}={raw} не соответствует ветви текущего элемента')
    return {'parameters': contexts, 'boundary_tokens_not_required': sorted(dispensable), 'issues': issues}
