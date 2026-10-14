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
    if not changes.keys() <= {'type', 'description', 'source_fragment'}:
        raise ValueError('Нельзя изменять ID, статус или требование элемента')
    data = project.model_dump()
    for i, item in enumerate(data['elements']):
        if item['id'] == element_id:
            candidate = Element.model_validate({**item, **changes})
            if candidate.model_dump() == item:
                return project.model_copy(deep=True)
            candidate.review_status = ReviewStatus.PENDING
            data['elements'][i] = candidate.model_dump()
            invalidate_requirement(data, candidate.requirement_id)
            return Project.model_validate(data)
    raise ValueError('Элемент не найден')


def invalidate_requirement(data: dict, requirement_id: str) -> None:
    """Сбросить результаты, зависящие от контекста требования."""
    data['initial_coverage'] = None
    data['analysis_notes'].pop(requirement_id, None)
    element_ids = {e['id'] for e in data['elements'] if e['requirement_id'] == requirement_id}
    data['coverage'] = [link for link in data['coverage'] if link['element_id'] not in element_ids]
    for test in data['test_cases']:
        if test['requirement_id'] == requirement_id and test['source'] == TestSource.GENERATED:
            test['review_status'] = ReviewStatus.PENDING


def review_element(project: Project, element_id: str, accepted: bool) -> Project:
    """Отклонённые аспекты сохраняются для просмотра, исключаются из расчёта."""
    data = project.model_dump()
    for item in data['elements']:
        if item['id'] == element_id:
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
