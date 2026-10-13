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
    return Project.model_validate(data)
