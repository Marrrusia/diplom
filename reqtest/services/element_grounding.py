"""Проверки привязки описания к цитате; не заменяют ручную семантическую проверку."""
import re
from reqtest.models.domain import ElementType


def technical_facts(text: str) -> set[str]:
    """Имена и числовые литералы не должны возникать только в описании."""
    return set(re.findall(r'\b[A-Za-z_][A-Za-z_0-9]*\b|(?<!\w)(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)\b', text))


def grounding_issues(element, requirement_text: str | None = None) -> list[str]:
    """Найти известные несоответствия реального демонстрационного отчёта."""
    description = element.description
    fragment = element.source_fragment
    problems = []
    # Имя переменной может уточняться общим контекстом требования; числовой
    # литерал должен подтверждаться непосредственно цитатой.
    unsupported = technical_facts(description) - technical_facts(requirement_text or fragment)
    unsupported |= {fact for fact in technical_facts(description) - technical_facts(fragment)
                    if fact[0].isdigit()}
    if unsupported:
        problems.append('Описание содержит имена/числа вне цитаты: ' + ', '.join(sorted(unsupported)))
    if re.search(r'без\s+аргументов', description, re.IGNORECASE) and not re.search(r'без\s+аргументов', fragment, re.IGNORECASE):
        problems.append('Ограничение «без аргументов» отсутствует в цитате')
    if re.search(r'\bдиапазон\w*\b', description, re.IGNORECASE) and element.type == ElementType.CONSTRAINT:
        problems.append('Числовой диапазон нужно выделить в категории «диапазон», сохранив условия отдельно')
    if re.search(r'не\s+более\s+\d+\s+раз', description, re.IGNORECASE) and element.type == ElementType.ACTION:
        problems.append('Предел повторений выделите отдельно как цикл/ограничение, не объединяйте с действием')
    if element.type == ElementType.RANGE and re.search(r'биты\s+(?:вне|внутри)\s+маски', description, re.IGNORECASE):
        problems.append('Сохранение/замена битов маски — действие или ограничение, а не диапазон значений')
    if is_specification_gap(fragment) and not is_specification_gap(description):
        problems.append('Цитата сообщает об отсутствии спецификации, а описание задаёт проверяемое поведение')
    if (element.type == ElementType.CONDITION and re.search(r'^если.*\bкорректн', description, re.IGNORECASE)
            and not re.search(r'\bкорректн', fragment, re.IGNORECASE)):
        problems.append('Ветка корректных входных данных отсутствует в цитате')
    independent_actions = set(re.findall(r'\b(?:сохранить|вернуть|оставить)\b', description, re.IGNORECASE))
    if len(independent_actions) > 1:
        problems.append('Разделите независимые результаты: сохранение/возврат/неизменность должны быть отдельными элементами')
    if (element.type == ElementType.CONSTRAINT and re.match(r'\s*если\b', description, re.IGNORECASE)
            and re.search(r'\b(?:вернуть|сохранить|оставить)\b', description, re.IGNORECASE)):
        problems.append('Условие ветви отделите от действия и ограничения сохранности значения')
    return problems


def is_specification_gap(description: str) -> bool:
    """Явное отсутствие спецификации — замечание, а не проверяемое поведение."""
    return bool(re.search(r'(?:не\s+определен[оыа]?|не\s+определён[оыа]?|не\s+задаются|не\s+указаны)', description, re.IGNORECASE))


def split_grounding_issues(issues: list[str]) -> tuple[list[str], list[str]]:
    """Фактическая ошибка блокирует ответ; качество разбиения требует человека."""
    structural = ('Разделите независимые результаты', 'Условие ветви отделите')
    warnings = [issue for issue in issues if issue.startswith(structural)]
    return [issue for issue in issues if not issue.startswith(structural)], warnings
