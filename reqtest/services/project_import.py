"""Атомарное добавление данных в проект вне обработчиков интерфейса."""
from reqtest.models.domain import Project, Requirement, TestCase


def merge_import(project: Project, items: list[Requirement] | list[TestCase], kind: str) -> Project:
    """Вернуть проверенный снимок; исходный проект при ошибке не изменяется."""
    if kind not in ("requirements", "test_cases"):
        raise ValueError("Неизвестный набор данных")
    data = project.model_dump()
    data[kind].extend(item.model_dump() for item in items)
    return Project.model_validate(data)


def update_requirement_text(project: Project, identifier: str, text: str) -> Project:
    """Изменить текст через валидацию полного снимка проекта."""
    data = project.model_dump()
    found = False
    for requirement in data['requirements']:
        if requirement['id'] == identifier:
            requirement['text'] = text
            found = True
    if not found:
        raise ValueError('Неизвестное требование')
    removed = {e['id'] for e in data['elements'] if e['requirement_id'] == identifier}
    data['elements'] = [e for e in data['elements'] if e['id'] not in removed]
    data['coverage'] = [link for link in data['coverage'] if link['element_id'] not in removed]
    for test in data['test_cases']:
        test['element_ids'] = [eid for eid in test['element_ids'] if eid not in removed]
    return Project.model_validate(data)
