"""Условия, отрицательные ветви и преобразования с точными источниками."""
import json
import pytest
from reqtest.models.domain import Requirement, Project, ElementType
from reqtest.services.branch_context import build_context_catalog, simple_branch
from reqtest.services.atomic_elements import split_description
from reqtest.services.extraction import extract_project
from reqtest.storage.sqlite_project import save_project, load_project


def run(text,items):
    class Client:
        def complete(self,messages,schema):
            return json.dumps(dict(elements=items))
    return extract_project(Project(name='Источники ветвей',requirements=[Requirement(id='R',text=text)]),Client()).project


@pytest.mark.parametrize('text',[
    'Если value меньше 0 или больше 100, вернуть ERROR.',
    'В режиме ACTIVE, если READY равно 1, вызвать Read().',
    'SLEEP: disable clock; RUN: enable output.',
    'When VALID equals 1, copy sample into output.',
    'При поступлении события WAKE в состоянии IDLE включить питание.',
])
def test_context_catalog_is_deterministic_and_exact(text):
    req=Requirement(id='R',text=text)
    refs=build_context_catalog(req)
    assert refs and refs==build_context_catalog(req)
    assert all(text[r.start:r.end]==r.text for r in refs)
    assert len({r.source_id for r in refs})==len(refs)


def test_range_effects_split_and_link_to_opposite_branches():
    text='При вызове SetLevel компонент должен сохранить value и вернуть OK. Если value меньше 0, вернуть ERROR и оставить value без изменения.'
    result=run(text,[dict(type='действие',description='сохранить value и вернуть OK',source_ids=['F001']),
                     dict(type='действие',description='вернуть ERROR и оставить value без изменения',source_ids=['F002'])])
    effects=[e for e in result.elements if e.type!=ElementType.CONDITION]
    assert len(effects)==4
    assert effects[0].condition_ids==effects[1].condition_ids
    assert effects[2].condition_ids==effects[3].condition_ids
    assert effects[0].condition_ids!=effects[2].condition_ids
    assert effects[3].type==ElementType.CONSTRAINT
    assert all(e.review_status.value=='ожидает проверки' for e in result.elements)
    assert result.analysis_incomplete==['R']


def test_else_links_false_condition_without_new_behavior(tmp_path):
    result=run('Если флаг установлен, вернуть YES, иначе вернуть NO.',[
        dict(type='действие',description='вернуть YES',source_ids=['F001']),
        dict(type='действие',description='вернуть NO',source_ids=['F001'])])
    assert result.elements[0].condition_ids==result.elements[1].negated_condition_ids
    assert not result.elements[1].condition_ids
    save_project(result,tmp_path/'else.sqlite')
    assert load_project(tmp_path/'else.sqlite')==result


def test_nested_branch_is_not_inferred():
    text='Если режим активен, то если флаг установлен, вернуть READY.'
    assert simple_branch(text) is None
    result=run(text,[dict(type='действие',description='вернуть READY',source_ids=['F001'])])
    assert not result.elements[0].condition_ids
    assert result.elements[0].analysis_blocked


def test_explicit_source_ids_can_represent_nested_scope():
    text='При вызове Tick в режиме RUN, если READY равно 1, вызвать Poll().'
    req=Requirement(id='R',text=text)
    contexts=build_context_catalog(req)
    result=run(text,[dict(type='действие',description='Вызвать Poll()',source_ids=['F001'],context_ids=[r.source_id for r in contexts])])
    assert len(result.elements[0].condition_ids)==3
    assert not result.elements[0].analysis_blocked


def test_condition_left_only_in_description_is_flagged():
    result=run('В режиме RUN, если READY равно 1, вызвать Poll().',[
        dict(type='действие',description='Если READY равно 1, вызвать Poll()',source_ids=['F001'],context_ids=['C001'])])
    assert result.elements[0].analysis_blocked
    assert any('не привязаны' in n for n in result.elements[0].review_notes)


def test_wrong_context_source_kind_is_rejected_locally():
    result=run('Вызвать Poll().',[dict(type='действие',description='Вызвать Poll()',source_ids=['F001']),
        dict(type='действие',description='Вызвать Poll()',source_ids=['F001'],context_ids=['F001'])])
    assert len(result.elements)==1
    assert result.analysis_notes['R']


def test_unselected_sentence_is_not_evidence_even_inside_envelope():
    result=run('Начало. Константа SECRET_FLAG определена. Вернуть OK.',[
        dict(type='действие',description='Вернуть SECRET_FLAG',source_ids=['F001','F003'])])
    assert 'SECRET_FLAG' in result.elements[0].source_fragment
    assert result.elements[0].analysis_blocked


def test_related_selected_sentence_can_supply_definition():
    result=run('Результат называется STATUS_DONE. Вернуть результат.',[
        dict(type='действие',description='Вернуть STATUS_DONE',source_ids=['F001','F002'])])
    assert not result.elements[0].analysis_blocked


@pytest.mark.parametrize('description',[
    'Вызвать Compute(a и записать b)',
    'Записать «a и вернуть b»',
    'Если READY, записать A и вернуть B',
    'Не вызывать A и вернуть B',
    'Записать A и вернуть B после Commit()',
])
def test_unsafe_split_is_left_to_manual_review(description):
    assert split_description(ElementType.ACTION,description)==[(ElementType.ACTION,description)]


def test_present_tense_and_argument_list_split_safely():
    assert [d for _,d in split_description(ElementType.ACTION,'Компонент сохраняет value и возвращает OK')]==['сохраняет value','возвращает OK']
    assert [d for _,d in split_description(ElementType.ACTION,'вызвать Compute(a и записать b) и вернуть OK')]==['вызвать Compute(a и записать b)','вернуть OK']


def test_old_sqlite_retains_links_but_does_not_invent_completeness(tmp_path):
    import sqlite3
    from reqtest.storage.sqlite_project import APPLICATION_ID, FILE_VERSION
    original=run('Если флаг установлен, вернуть YES.',[dict(type='действие',description='вернуть YES',source_ids=['F001'])])
    data=original.model_dump(mode='json')
    data.pop('analysis_incomplete')
    path=tmp_path/'old.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
        connection.execute(f'PRAGMA user_version={FILE_VERSION}')
        connection.execute('CREATE TABLE project_snapshot (id INTEGER PRIMARY KEY, payload TEXT)')
        connection.execute('INSERT INTO project_snapshot VALUES(1,?)',(json.dumps(data),))
    before=path.read_bytes()
    loaded=load_project(path)
    assert loaded.elements==original.elements
    assert loaded.analysis_incomplete==['R']
    assert path.read_bytes()==before
