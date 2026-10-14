"""Проверки известных ошибок сценария, обнаруженных при ручном тестировании."""
import re
from reqtest.models.domain import Requirement, TestCase, Element, ElementType


def generation_quality_issues(requirement: Requirement, test: TestCase, elements: list[Element]) -> list[str]:
    """Не разрешать тесту подменять действие компонента ручным вызовом макроса."""
    issues = []
    macros = re.findall(r'макроса\s+([A-Za-z_][A-Za-z_0-9]*)\(', requirement.text)
    for macro in macros:
        pattern = r'^\s*(?:вызвать|вызов)\s+(?:макроса?\s+)?' + re.escape(macro) + r'\s*\('
        if any(re.search(pattern, step, re.IGNORECASE) for step in test.steps):
            issues.append('Тест вручную вызывает ' + macro + ' вместо наблюдения действия компонента')
    actions = [e for e in elements if e.id in test.element_ids and e.type == ElementType.ACTION]
    for action in actions:
        match = re.search(r'включить\s+тактирование\s+модуля\s+([A-Za-z_][A-Za-z_0-9]*)', action.source_fragment, re.IGNORECASE)
        if match and ('тактирован' not in test.expected_result.casefold() or match.group(1) not in test.expected_result):
            issues.append('В ожидаемом результате не указано включение тактирования ' + match.group(1))
    return issues
