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
    if not changes.keys() <= {'type', 'description', 'source_fragment', 'condition_ids', 'negated_condition_ids', 'conditions'}:
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
            requirement=next(r for r in project.requirements if r.id==candidate.requirement_id)
            if 'source_fragment' in changes and candidate.source_fragment != item['source_fragment'] and candidate.source_fragment not in requirement.text:
                raise ValueError('Цитата отсутствует в исходном требовании')
            candidate.analysis_blocked = candidate.source_fragment not in requirement.text
            candidate.review_notes = ['Цитата не найдена дословно; исправьте цитату или отклоните элемент'] if candidate.analysis_blocked else []
            data['elements'][i] = candidate.model_dump()
            invalidate_requirement(data, candidate.requirement_id)
            return Project.model_validate(data)
    raise ValueError('Элемент не найден')


def invalidate_requirement(data: dict, requirement_id: str) -> None:
    """Сбросить результаты, зависящие от контекста требования."""
    data['initial_coverage'] = None
    if requirement_id not in data.get('analysis_incomplete', []):
        data.setdefault('analysis_incomplete', []).append(requirement_id)
    data['analysis_notes'].pop(requirement_id, None)
    element_ids = {e['id'] for e in data['elements'] if e['requirement_id'] == requirement_id}
    data['coverage'] = [link for link in data['coverage'] if link['element_id'] not in element_ids]
    for test in data['test_cases']:
        if test['requirement_id'] == requirement_id and test['source'] == TestSource.GENERATED:
            test['review_status'] = ReviewStatus.PENDING if test['review_status'] != ReviewStatus.REJECTED else ReviewStatus.REJECTED


def review_element(project: Project, element_id: str, accepted: bool) -> Project:
    """Отклонённые аспекты сохраняются для просмотра, исключаются из расчёта."""
    data = project.model_dump()
    for item in data['elements']:
        if item['id'] == element_id:
            if accepted and item.get('analysis_blocked',False):
                raise ValueError('Сначала исправьте дословную цитату элемента или отклоните его')
            status = ReviewStatus.ACCEPTED if accepted else ReviewStatus.REJECTED
            if item['review_status'] != status:
                item['review_status'] = status
                invalidate_requirement(data, item['requirement_id'])
            return Project.model_validate(data)
    raise ValueError('Элемент не найден')


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


def confirm_completeness(project: Project, requirement_id: str, rationale: str) -> Project:
    """Записать ручную проверку набора, отдельно от принятия отдельных элементов."""
    if requirement_id not in {r.id for r in project.requirements}:
        raise ValueError('Требование не найдено')
    if not rationale.strip():
        raise ValueError('Укажите обоснование проверки полноты')
    active = [e for e in project.elements if e.requirement_id==requirement_id and e.review_status!=ReviewStatus.REJECTED]
    if not active or any(e.review_status!=ReviewStatus.ACCEPTED or e.analysis_blocked for e in active):
        raise ValueError('Сначала проверьте и примите все активные элементы требования')
    data=project.model_dump()
    data['analysis_incomplete']=[rid for rid in data['analysis_incomplete'] if rid!=requirement_id]
    data['analysis_notes'].setdefault(requirement_id,[]).append('Полнота проверена пользователем: '+rationale.strip())
    data['initial_coverage']=None
    return Project.model_validate(data)
