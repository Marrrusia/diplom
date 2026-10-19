"""Проверки отдельных явно записанных аспектов, без вывода нового поведения."""
import re
from dataclasses import dataclass
from reqtest.models.domain import ElementType, Element, Requirement, ReviewStatus
from reqtest.services.element_grounding import technical_facts, is_gap_only_source
from reqtest.services.source_catalog import build_source_catalog


def _normalize(text: str) -> str:
    """Сравнивать русское оформление, сохраняя регистр технических имён."""
    return re.sub(r'\s+', ' ', re.sub(r'[А-ЯЁ]', lambda m: m.group().lower(), text)).strip()


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
    text = '\n'.join(ref.text for ref in build_source_catalog(text)
                     if not is_gap_only_source(ref.text))
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
    modes = set()
    for match in re.finditer(r'в режиме ([A-Za-z_][A-Za-z_0-9]*)', text, re.IGNORECASE):
        if match.group(1) not in modes:
            aspects.append(RequiredAspect(ElementType.MODE, match.group(0), 'режим функционирования', match.group(1)))
            modes.add(match.group(1))
    for match in re.finditer(r'не более \d+ раз', text, re.IGNORECASE):
        aspects.append(RequiredAspect(ElementType.LOOP, match.group(0), 'предел повторений цикла'))
    return aspects


def missing_aspects(text: str, elements) -> list[RequiredAspect]:
    """Аспект должен присутствовать в своей категории, а не только в другом элементе."""
    return [aspect for aspect in required_aspects(text) if not any(
        item.type == aspect.type
        and _normalize(re.sub(r"^(?:если|необходимо|должен)\s+", "", aspect.fragment, flags=re.IGNORECASE)) in _normalize(item.source_fragment)
        and (aspect.description_token is None or aspect.description_token in item.description)
        and (aspect.type != ElementType.CONDITION or technical_facts(aspect.fragment) <= technical_facts(item.description))
        for item in elements
    )]


def restore_explicit_modes(requirement: Requirement, elements: list[Element]) -> list[Element]:
    """Дополнить явно названные режимы исходными цитатами без вывода поведения."""
    result = list(elements)
    catalog = build_source_catalog(requirement.text)
    used_ids = {element.id for element in result}
    for aspect in missing_aspects(requirement.text, elements):
        if aspect.type != ElementType.MODE:
            continue
        source = next((ref for ref in catalog if aspect.fragment in ref.text
                       and not is_gap_only_source(ref.text)), None)
        if source is None:
            continue
        number = 1
        while f'{requirement.id}::E{number:03}' in used_ids:
            number += 1
        identifier = f'{requirement.id}::E{number:03}'
        used_ids.add(identifier)
        result.append(Element(id=identifier, requirement_id=requirement.id,
                              type=ElementType.MODE, description=aspect.fragment,
                              source_fragment=source.text, source_refs=[source],
                              review_status=ReviewStatus.PENDING,
                              review_notes=['Режим добавлен правилом из явного текста требования: '
                                            'модель не выделила его отдельно. Требуется ручная проверка.']))
    return result
