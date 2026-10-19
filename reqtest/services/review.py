"""Атомарное редактирование и сброс устаревших подтверждений."""
from reqtest.models.domain import Project, TestCase, Element, ReviewStatus, TestSource


def edit_test(project: Project, test_id: str, changes: dict) -> Project:
    """Сохранить изменяемые поля; источник, ID и требование остаются неизменными."""
    allowed = {'title', 'preconditions', 'input_data', 'steps', 'expected_result', 'element_ids'}
    if not changes.keys() <= allowed:
        raise ValueError('Нельзя изменять ID, источник, статус или требование теста')
    data = project.model_dump()
    for i, item in enumerate(data['test_cases']):
        if item['id'] == test_id:
            candidate = TestCase.model_validate({**item, **changes})
            if len(candidate.element_ids) != len(set(candidate.element_ids)):
                raise ValueError('Повторяющиеся ссылки на элементы')
            if candidate.model_dump() == item:
                return project.model_copy(deep=True)
            candidate.review_status = ReviewStatus.PENDING
            if candidate.source == TestSource.EXISTING:
                data['initial_coverage'] = None
            data['test_cases'][i] = candidate.model_dump()
            for entry in data['generation_log']:
                if test_id in entry['test_case_ids']:
                    entry['notes'] += '\n' + test_id + ': тест отредактирован пользователем; прежняя проверка генератора относится к исходной версии'
            data['coverage'] = [link for link in data['coverage'] if link['test_case_id'] != test_id]
            return Project.model_validate(data)
    raise ValueError('Тест не найден')


def edit_element(project: Project, element_id: str, changes: dict) -> Project:
    """Изменение аспекта сбрасывает анализ всего его требования (общие условия)."""
    if not changes.keys() <= {'type', 'description', 'source_fragment', 'condition_ids', 'negated_condition_ids'}:
        raise ValueError('Нельзя изменять ID, статус или требование элемента')
    data = project.model_dump()
    for i, item in enumerate(data['elements']):
        if item['id'] == element_id:
            candidate = Element.model_validate({**item, **changes})
            if 'source_fragment' in changes and changes['source_fragment'] != item['source_fragment']:
                candidate.source_refs = []
            if candidate.model_dump() == item:
                return project.model_copy(deep=True)
            candidate.review_status = ReviewStatus.PENDING
            candidate.review_notes = []
            candidate.analysis_blocked = True
            data['elements'][i] = candidate.model_dump()
            invalidate_requirement(data, candidate.requirement_id)
            return Project.model_validate(data)
    raise ValueError('Элемент не найден')


def invalidate_requirement(data: dict, requirement_id: str) -> None:
    """Сбросить результаты, зависящие от контекста требования."""
    data['initial_coverage'] = None
    if requirement_id not in data['analysis_incomplete']:
        data['analysis_incomplete'].append(requirement_id)
    data['analysis_notes'].setdefault(requirement_id, []).append(
        'Контекст изменён пользователем; прежние замечания экспертизы сохранены для сверки. Требуется повторная проверка.')
    element_ids = {e['id'] for e in data['elements'] if e['requirement_id'] == requirement_id}
    data['coverage'] = [link for link in data['coverage'] if link['element_id'] not in element_ids]
    for test in data['test_cases']:
        if (test['requirement_id'] == requirement_id and test['source'] == TestSource.GENERATED
                and test['review_status'] != ReviewStatus.REJECTED):
            test['review_status'] = ReviewStatus.PENDING


def review_element(project: Project, element_id: str, accepted: bool) -> Project:
    """Отклонённые аспекты сохраняются для просмотра, исключаются из расчёта."""
    data = project.model_dump()
    for item in data['elements']:
        if item['id'] == element_id:
            status = ReviewStatus.ACCEPTED if accepted else ReviewStatus.REJECTED
            if accepted and any(e.analysis_blocked or e.review_status == ReviewStatus.REJECTED
                                for e in project.elements if e.id in item['condition_ids'] + item['negated_condition_ids']):
                raise ValueError('Сначала проверьте обязательные условия применимости элемента')
            if item['review_status'] != status or (accepted and item['analysis_blocked']):
                item['review_status'] = status
                if accepted:
                    item['analysis_blocked'] = False
                invalidate_requirement(data, item['requirement_id'])
            return Project.model_validate(data)
    raise ValueError('Элемент не найден')


def add_manual_element(project: Project, requirement_id: str) -> tuple[Project, str]:
    """Создать временный кандидат для формы; отмена формы не меняет проект."""
    from uuid import uuid4
    from reqtest.models.domain import ElementType
    requirement = next((r for r in project.requirements if r.id == requirement_id), None)
    if requirement is None:
        raise ValueError('Неизвестное требование')
    element = Element(id=requirement_id + '::MANUAL-' + uuid4().hex[:12], requirement_id=requirement_id,
                      type=ElementType.ACTION, description=requirement.text,
                      source_fragment=requirement.text, analysis_blocked=True,
                      review_notes=['Элемент добавлен вручную; уточните описание, категорию и применимость'])
    data = project.model_dump()
    data['elements'].append(element.model_dump())
    invalidate_requirement(data, requirement_id)
    return Project.model_validate(data), element.id


def confirm_extraction(project: Project, requirement_id: str, rationale: str) -> Project:
    """Зафиксировать явную ручную сверку полноты, сохранив замечания модели."""
    if not rationale.strip():
        raise ValueError('Укажите обоснование сверки с исходным требованием')
    if not any(r.id == requirement_id for r in project.requirements):
        raise ValueError('Неизвестное требование')
    elements = [e for e in project.elements if e.requirement_id == requirement_id
                and e.review_status != ReviewStatus.REJECTED]
    if any(e.analysis_blocked or e.review_status != ReviewStatus.ACCEPTED for e in elements):
        raise ValueError('Сначала проверьте и примите либо отклоните все элементы требования')
    data = project.model_dump()
    data['analysis_incomplete'] = [rid for rid in data['analysis_incomplete'] if rid != requirement_id]
    data['analysis_notes'].setdefault(requirement_id, []).append('Ручная сверка полноты: ' + rationale.strip())
    return Project.model_validate(data)


def review_test(project: Project, test_id: str, accepted: bool) -> Project:
    """Принятие теста не является подтверждением связей покрытия."""
    data = project.model_dump()
    for item in data['test_cases']:
        if item['id'] == test_id:
            status = ReviewStatus.ACCEPTED if accepted else ReviewStatus.REJECTED
            if item['review_status'] != status:
                item['review_status'] = status
                data['coverage'] = [link for link in data['coverage'] if link['test_case_id'] != test_id]
            return Project.model_validate(data)
    raise ValueError('Тест не найден')
