"""Применимость без привязки к именам из демонстрационного набора."""
import pytest
from reqtest.models.domain import Element, Project, Requirement
from reqtest.services.branch_context import attach_branch_context, parse_branch
from reqtest.services.source_catalog import build_source_catalog
from reqtest.storage.sqlite_project import save_project, load_project


def setup(text, descriptions):
    requirement = Requirement(id='OTHER', text=text)
    refs = build_source_catalog(text)
    elements = [Element(id=f'X{i}', requirement_id='OTHER', type=kind,
                       description=description, source_fragment=refs[index].text,
                       source_refs=[refs[index]])
                for i, (kind, description, index) in enumerate(descriptions)]
    return requirement, elements


@pytest.mark.parametrize('condition,action', [
    ('температура выше порога', 'выключить вентилятор'),
    ('режим равен READY', 'вернуть RESULT_READY'),
    ('флаг установлен', 'сохранить счётчик')])
def test_explicit_conditions_are_preserved_generically(condition, action):
    r, elements = setup(f'Если {condition}, компонент должен {action}.', [('действие', action, 0)])
    result = attach_branch_context(r, elements)
    assert len(result) == 2
    assert result[0].condition_ids == [result[1].id]
    assert result[1].description == f'Если {condition}'
    assert not elements[0].condition_ids
    Project(name='Проверка', requirements=[r], elements=result)


def test_existing_condition_reused():
    r, elements = setup('Если режим активен, модуль должен вернуть READY.',
        [('условие', 'Если режим активен', 0), ('действие', 'вернуть READY', 0)])
    result = attach_branch_context(r, elements)
    assert len(result) == 2
    assert result[1].condition_ids == ['X0']


def test_else_is_false_of_same_condition_and_persists(tmp_path):
    r, elements = setup('Если флаг установлен, вернуть YES, иначе вернуть NO.',
        [('действие', 'вернуть YES', 0), ('действие', 'вернуть NO', 0)])
    result = attach_branch_context(r, elements)
    assert result[0].condition_ids == result[1].negated_condition_ids == [result[2].id]
    assert not result[1].condition_ids
    project = Project(name='Ветви', requirements=[r], elements=result)
    path = tmp_path/'branches.sqlite'
    save_project(project, path)
    assert load_project(path) == project


def test_branches_not_attached_to_unrelated_actions():
    r, elements = setup('Если флаг A установлен, вернуть YES. Если флаг B установлен, вернуть NO.',
        [('действие', 'вернуть YES', 0), ('действие', 'вернуть NO', 1)])
    result = attach_branch_context(r, elements)
    assert result[0].condition_ids != result[1].condition_ids
    assert len(result) == 4


def test_nested_conditions_are_not_guessed():
    text = 'Если режим активен, то если флаг установлен, вернуть READY.'
    assert parse_branch(text) is None
    r, elements = setup(text, [('действие', 'вернуть READY', 0)])
    result = attach_branch_context(r, elements)
    assert len(result) == 1
    assert not result[0].condition_ids
    assert result[0].review_notes


def test_ambiguous_else_not_guessed():
    r, elements = setup('Если флаг установлен, вернуть YES, иначе вернуть YES.',
        [('действие', 'вернуть YES', 0)])
    result = attach_branch_context(r, elements)
    assert len(result) == 1
    assert result[0].review_notes


def test_non_condition_reference_rejected():
    r, elements = setup('Вернуть READY.', [('действие', 'вернуть READY', 0), ('действие', 'вернуть READY', 0)])
    elements[0].condition_ids = ['X1']
    with pytest.raises(ValueError, match='условие применимости'):
        Project(name='Ошибка', requirements=[r], elements=elements)


def test_cyclic_context_is_rejected():
    r, elements = setup('Если готов, то вернуть READY.',
        [('условие', 'Если готов', 0), ('условие', 'Готовность', 0)])
    elements[0].condition_ids = ['X1']
    elements[1].condition_ids = ['X0']
    with pytest.raises(ValueError, match='Циклические'):
        Project(name='Цикл', requirements=[r], elements=elements)


def test_review_can_correct_context_and_resets_coverage():
    from reqtest.services.review import edit_element
    r, elements = setup('Если готов, вернуть READY.',
        [('условие', 'Если готов', 0), ('действие', 'вернуть READY', 0)])
    project = Project(name='Правка', requirements=[r], elements=elements)
    changed = edit_element(project, 'X1', {'condition_ids': ['X0']})
    assert changed.elements[1].condition_ids == ['X0']
    assert project.elements[1].condition_ids == []
    with pytest.raises(ValueError, match='противоречивые'):
        edit_element(changed, 'X1', {'negated_condition_ids': ['X0']})


def test_coverage_receives_applicability_and_rejected_condition_blocks_positive():
    import json
    from reqtest.models.domain import TestCase as Case, ReviewStatus, CoverageStatus
    from reqtest.services.coverage import analyze_coverage
    r, elements = setup('Если готов, вернуть READY.',
        [('условие', 'Если готов', 0), ('действие', 'вернуть READY', 0)])
    elements[1].condition_ids = ['X0']
    elements[0].review_status = ReviewStatus.REJECTED
    project = Project(name='Контекст', requirements=[r], elements=elements,
        test_cases=[Case(id='T', requirement_id=r.id, title='Проверка',
                        preconditions=['Готов'], steps=['Выполнить вызов'], expected_result='Получен READY')])
    class Client:
        def complete(self, messages, schema):
            payload = json.loads(messages[-1]['content'])
            assert payload['applicability'] == {'all_true': ['Если готов'], 'all_false': []}
            return json.dumps(dict(status='покрыт', confidence=1, rationale='Результат проверен',
                precondition_evidence=['Готов'], step_evidence=['Выполнить вызов'], result_evidence=['Получен READY']))
    result = analyze_coverage(project, Client())
    assert result.coverage[0].status == CoverageStatus.REVIEW
    assert 'отклонено' in result.coverage[0].rationale
