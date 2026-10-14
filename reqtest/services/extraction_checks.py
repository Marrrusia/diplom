"""Проверки отдельных явно записанных аспектов, без вывода нового поведения."""
import re
from dataclasses import dataclass
from reqtest.models.domain import ElementType


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
    return aspects


def missing_aspects(text: str, elements) -> list[RequiredAspect]:
    """Аспект должен присутствовать в своей категории, а не только в другом элементе."""
    return [aspect for aspect in required_aspects(text) if not any(
        item.type == aspect.type
        and re.sub(r"^(?:если|необходимо|должен)\s+", "", aspect.fragment, flags=re.IGNORECASE) in item.source_fragment
        and (aspect.description_token is None or aspect.description_token in item.description)
        for item in elements
    )]
