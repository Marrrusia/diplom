"""Детерминированный каталог источников: текст модели не становится цитатой."""
import re
from reqtest.models.domain import SourceReference


def build_source_catalog(text: str) -> list[SourceReference]:
    """Разделить предложения/абзацы, сохранив точные смещения Unicode-символов.

    Точки внутри имён и дробных чисел не разделяют источник. ID локален
    требованию и действителен только для его текущего текста.
    """
    boundaries = [0, *[m.end() for m in re.finditer(r'(?<=[.!?;])\s+(?=[А-ЯЁA-Z])|\n+', text)], len(text)]
    result = []
    for left, right in zip(boundaries, boundaries[1:]):
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right-1].isspace():
            right -= 1
        if left < right:
            result.append(SourceReference(source_id=f'F{len(result)+1:03}', start=left, end=right, text=text[left:right]))
    return result
