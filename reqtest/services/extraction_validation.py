"""Вспомогательная проверка кодовых имён и литералов; не доказательство смысла."""
import re


def semantic_risks(description: str, quote: str, category: str) -> list[str]:
    """Консервативные сигналы ручной проверки, а не доказательство ошибки.

    Не разрезаем текст по союзам: так можно потерять условия и порядок.
    Подозрительное предложение сохраняется с исходной цитатой.
    """
    warnings = []
    text = description + ' ' + quote
    if category in ('условие', 'режим') and re.search(r'\b(?:должен|должна|должно|должны|shall|must)\b', description, re.I):
        warnings.append('Описание условия содержит требуемое поведение; проверьте разделение предпосылки и результата')
    if category == 'действие' and re.fullmatch(r'\s*(?:before|after)\s+\w+ing\b[^,;]*', description, re.I):
        warnings.append('Описание начинается с отношения порядка; проверьте наличие самостоятельного требуемого эффекта')
    if re.search(r'не\s+(?:определен[оаы]?|задан[оаы]?|указан[оаы]?)|'
                 r'not\s+(?:specified|defined)|unspecified|undefined', text, re.I):
        warnings.append('Источник содержит недостаточность спецификации; проверьте, задано ли здесь проверяемое поведение')
    if re.search(r'\b(?:быстро|корректно|своевременно|надлежащим|quickly|correctly|promptly)\b', description, re.I):
        warnings.append('Качественная формулировка: необходим явный критерий проверки из требования')
    if category == 'диапазон' and not re.search(r'\d|от\s+\S+\s+до|между|из\s+множества|between|range|\{', quote, re.I):
        warnings.append('Для диапазона не обнаружены явные границы или множество; проверьте категорию и достаточность данных')
    # Только явные пары глаголов; перечисления аргументов и логические И не режем.
    verbs = r'(?:сохранить|записать|вернуть|вызвать|выполнить|оставить|прочитать|установить|вычислить|return|store|write|call|leave|read|set|compute)'
    if re.search(r'\b' + verbs + r'\b.+?\b(?:и|а\s+также|and)\s+' + verbs + r'\b', description, re.I):
        warnings.append('Возможны независимые эффекты: разделите их на элементы, сохранив условия и порядок')
    return warnings


def context_risks(quote: str, applicability: str, category: str) -> list[str]:
    """Сигналы потери области и смешения порядка с предусловием."""
    warnings = []
    if re.search(r'\b(?:должен|должна|должно|должны|shall|must)\b', applicability, re.I):
        warnings.append('Применимость содержит требуемое поведение; проверьте, не записан ли ожидаемый результат вместо предусловия')
    if category not in ('условие', 'режим'):
        labels = re.findall(r'\b([A-Z][A-Z0-9_]*)\s*:', quote)
        if any(not re.search(r'\b' + re.escape(label) + r'\b', applicability) for label in labels):
            warnings.append('Метка области/ветви из цитаты отсутствует в применимости; проверьте условия')
    if re.search(r'\bbefore\s+|\bперед\s+|до\s+(?:вызова|выполнения|подтверждения)', applicability, re.I):
        warnings.append('В применимости указан порядок операций; проверьте, не подменяет ли он предусловие')
    return warnings


def unsupported_literals(description: str, source: str) -> list[str]:
    """Подозрительные кодовые имена/литералы; английские слова не считаются кодом.

    Это сигнал проверки, а не семантическое доказательство: обозначения и
    представления чисел могут быть эквивалентны. Текст не переписывается.
    """
    pattern = (r'\b[A-Za-z_][A-Za-z_0-9]*(?=\s*\()|'
               r'\b[A-Za-z_][A-Za-z_0-9]*_[A-Za-z_0-9]+\b|'
               r'\b[A-Z][A-Z_0-9]+\b|\b[a-z]+[A-Z][A-Za-z_0-9]*\b|'
               r'(?<![\w.])(?:0[xX][0-9a-fA-F]+|0[bB][01]+|[+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)(?!\w)')
    # Кандидат определяется по форме в описании, а наличие — по границам имени
    # в источнике. F() и «F вызываться не должен» обозначают одно имя.
    candidates = set(re.findall(pattern, description))
    def present(token):
        if re.match(r'^[+\-]?\d', token):
            return re.search(r'(?<![\w+\-])(?<!\d[.,])' + re.escape(token) + r'(?!\w|[.,]\d)', source)
        return re.search(r'(?<!\w)' + re.escape(token) + r'(?!\w)', source)
    return sorted(token for token in candidates if not present(token))

