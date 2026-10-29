"""Атомарное добавление данных в проект вне обработчиков интерфейса."""
from reqtest.models.domain import Project, Requirement, TestCase
from reqtest.services.review import invalidate_requirement


def merge_import(project: Project, items: list[Requirement] | list[TestCase], kind: str) -> Project:
    """Вернуть проверенный снимок; исходный проект при ошибке не изменяется."""
    if kind not in ("requirements", "test_cases"):
        raise ValueError("Неизвестный набор данных")
    data = project.model_dump()
    identifiers = [item.id for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Повторные идентификаторы внутри импортируемого файла')
    existing = {item['id']: item for item in data[kind]}
    new_items = []
    for item in items:
        value = item.model_dump()
        if item.id in existing:
            if value != existing[item.id]:
                raise ValueError('Конфликт импортируемого идентификатора: '+item.id)
        else:
            new_items.append(value)
    if not new_items:
        return project.model_copy(deep=True)
    data['initial_coverage'] = None
    data[kind].extend(new_items)
    if kind == 'requirements':
        data['analysis_incomplete'] = list(dict.fromkeys(data.get('analysis_incomplete', []) + [item['id'] for item in new_items]))
    return Project.model_validate(data)


def update_requirement_text(project: Project, identifier: str, text: str) -> Project:
    """Изменить текст через валидацию полного снимка проекта."""
    data = project.model_dump()
    found = False
    for requirement in data['requirements']:
        if requirement['id'] == identifier:
            if requirement['text'] == text.strip():
                return project.model_copy(deep=True)
            requirement['text'] = text
            found = True
    if not found:
        raise ValueError('Неизвестное требование')
    invalidate_requirement(data, identifier)
    removed = {e['id'] for e in data['elements'] if e['requirement_id'] == identifier}
    data['elements'] = [e for e in data['elements'] if e['id'] not in removed]
    data['coverage'] = [link for link in data['coverage'] if link['element_id'] not in removed]
    for test in data['test_cases']:
        test['element_ids'] = [eid for eid in test['element_ids'] if eid not in removed]
    return Project.model_validate(data)
