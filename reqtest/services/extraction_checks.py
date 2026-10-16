"""Проверки отдельных явно записанных аспектов, без вывода нового поведения."""
import re
from dataclasses import dataclass
from reqtest.models.domain import ElementType
from reqtest.services.element_grounding import technical_facts


@dataclass(frozen=True)
class RequiredAspect:
    """Цитата и категория для проверки полноты предложений модели."""
    type: ElementType
    fragment: str
    label: str
    description_token: str | None = None


def required_aspects(text: str) -> list[RequiredAspect]:
    """Распознать поддерживаемые явные формулировки; это не общий NLP-анализ."""
    aspects = []
    for match in re.finditer(
        r'При\s+вызове\s+(?:(?:подкомпонента|функции|метода)\s+)?'
        r'([A-Za-z_][A-Za-z_0-9]*)(?:\(\))?', text, re.IGNORECASE
    ):
        aspects.append(RequiredAspect(ElementType.CONDITION, match.group(0),
                                      'условие вызова', match.group(1)))
    for match in re.finditer(r'если\s+значение\s+[^,;:.!?\n]+?\s+равно\s+[^,;:.!?\n]+', text, re.IGNORECASE):
        aspects.append(RequiredAspect(ElementType.CONDITION, match.group(0).strip(), 'условие равенства'))
    for match in re.finditer(
        r'(?:необходимо|должен)\s+[^;:.!?\n]+?вызовом\s+макроса\s+'
        r'[A-Za-z_][A-Za-z_0-9]*\(\)', text, re.IGNORECASE
    ):
        aspects.append(RequiredAspect(ElementType.ACTION, match.group(0), 'действие вызова макроса'))
    for match in re.finditer(r'без\s+аргументов', text, re.IGNORECASE):
        aspects.append(RequiredAspect(ElementType.CONSTRAINT, match.group(0), 'ограничение числа аргументов'))
    for match in re.finditer(r'в диапазоне от [+-]?\d+(?:[.,]\d+)? до [+-]?\d+(?:[.,]\d+)?(?: включительно)?', text, re.IGNORECASE):
        aspects.append(RequiredAspect(ElementType.RANGE, match.group(0), 'числовой диапазон'))
    for match in re.finditer(r'в режиме [A-Za-z_][A-Za-z_0-9]*', text, re.IGNORECASE):
        aspects.append(RequiredAspect(ElementType.MODE, match.group(0), 'режим функционирования'))
    for match in re.finditer(r'не более \d+ раз', text, re.IGNORECASE):
        aspects.append(RequiredAspect(ElementType.LOOP, match.group(0), 'предел повторений цикла'))
    return aspects


def missing_aspects(text: str, elements) -> list[RequiredAspect]:
    """Аспект должен присутствовать в своей категории, а не только в другом элементе."""
    return [aspect for aspect in required_aspects(text) if not any(
        item.type == aspect.type
        and re.sub(r"^(?:если|необходимо|должен)\s+", "", aspect.fragment, flags=re.IGNORECASE) in item.source_fragment
        and (aspect.description_token is None or aspect.description_token in item.description)
        and (aspect.type != ElementType.CONDITION or technical_facts(aspect.fragment) <= technical_facts(item.description))
        for item in elements
    )]
