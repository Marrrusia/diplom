"""Общий контракт на разных формулировках; ответы LLM здесь подменены явно."""
import json
from pathlib import Path
import pytest
from reqtest.models.domain import Project, Requirement, Element, ReviewStatus, LLMSettings
from reqtest.services.extraction import extract_project
from reqtest.services.coverage import active_elements, coverage_summary
from reqtest.services.generation import generation_targets, GenerationMode
from reqtest.services.review import review_element, edit_element, add_manual_element
from reqtest.services.semantic_extraction import unsupported_literals
from reqtest.storage.sqlite_project import save_project, load_project
from reqtest.llm.client import LLMError
from extraction_fakes import AuditedClient, clean_review

CORPUS = json.loads((Path(__file__).resolve().parents[1] / 'examples/validation_corpus.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CORPUS, ids=[c['id'] for c in CORPUS])
def test_reference_contract_across_languages_and_notations(case):
    project = Project(name='Корпус', requirements=[Requirement(id=case['id'], text=case['text'])])
    client = AuditedClient(case['elements'])
    result = extract_project(project, client).project
    assert client.calls == ['ExtractionResponse', 'ExtractionReview']
    assert len(result.elements) == len(case['elements'])
    assert not result.analysis_incomplete
    assert all(e.review_status == ReviewStatus.PENDING and not e.analysis_blocked for e in result.elements)
    assert [e.description for e in result.elements] == [e['description'] for e in case['elements']]
    assert all(case['text'][ref.start:ref.end] == ref.text for e in result.elements for ref in e.source_refs)
    assert not project.elements


def simple_project():
    return Project(name='Проверка', requirements=[Requirement(id='R', text='Выполнить TransferWord() при READY = 1.')])


def proposal(**changes):
    return dict(id='a', type='действие', description='Выполнить TransferWord()', source_ids=['F001'], **changes)


@pytest.mark.parametrize('kind', ['missing', 'unsupported', 'contradiction', 'ambiguous', 'compound', 'category', 'relationship'])
def test_expert_findings_are_saved_and_block_only_named_elements(kind):
    def review(payload):
        answer = clean_review(payload)
        answer['findings'] = [dict(kind=kind, element_ids=[payload['elements'][0]['id']], source_ids=['F001'],
                                   rationale='Спорный предикат', blocking=True)]
        return answer
    result = extract_project(simple_project(), AuditedClient([proposal()], review)).project
    assert len(result.elements) == 1 and result.elements[0].analysis_blocked
    assert 'Спорный предикат' in result.elements[0].review_notes
    assert not active_elements(result)
    assert coverage_summary(result)['total']['percent'] is None
    assert result.analysis_incomplete == ['R']


def test_missing_aspect_does_not_create_synthetic_elements():
    def review(payload):
        answer = clean_review(payload)
        answer.update(coverage_complete=False, findings=[dict(kind='missing', source_ids=['F001'],
                      element_ids=[], rationale='Не выделено условие READY = 1')])
        return answer
    result = extract_project(simple_project(), AuditedClient([proposal()], review)).project
    assert len(result.elements) == 1
    assert not result.elements[0].analysis_blocked
    assert result.analysis_incomplete == ['R']
    assert any('READY = 1' in note for note in result.analysis_notes['R'])


@pytest.mark.parametrize('extra', ['UNKNOWN_FLAG', '999'])
def test_unsupported_literals_remain_visible_but_are_not_actionable(extra):
    item = proposal()
    item['description'] += ' ' + extra
    result = extract_project(simple_project(), AuditedClient([item])).project
    assert extra in result.elements[0].description
    assert result.elements[0].analysis_blocked
    assert not active_elements(result)
    with pytest.raises(LLMError):
        generation_targets(result, GenerationMode.MISSING)
    accepted = review_element(result, result.elements[0].id, True)
    assert len(active_elements(accepted)) == 1
    assert accepted.analysis_incomplete == ['R']


def test_english_paraphrase_is_not_treated_as_invented_code():
    assert not unsupported_literals('Wait for the interrupt before returning the result',
                                    'The handler shall return after an interrupt occurs')


@pytest.mark.parametrize('role', ['specification_gap', 'ambiguous'])
def test_gap_and_ambiguity_are_reviewed_without_deleting_candidate(role):
    def review(payload):
        answer = clean_review(payload)
        answer['source_assessments'][0].update(role=role, rationale='Поведение не установлено однозначно')
        return answer
    result = extract_project(simple_project(), AuditedClient([proposal()], review)).project
    assert len(result.elements) == 1
    assert result.elements[0].analysis_blocked
    assert role in '\n'.join(result.analysis_notes['R'])


@pytest.mark.parametrize('defect', ['unknown_element', 'unknown_source', 'missing_source', 'unassessed_element', 'malformed'])
def test_invalid_expert_contract_cannot_release_candidates(defect):
    def review(payload):
        answer = clean_review(payload)
        if defect == 'unknown_element': answer['source_assessments'][0]['element_ids'] = ['FAKE']
        if defect == 'unknown_source': answer['source_assessments'][0]['source_id'] = 'FAKE'
        if defect == 'missing_source': answer['source_assessments'] = []
        if defect == 'unassessed_element': answer['source_assessments'][0]['element_ids'] = []
        if defect == 'malformed': return {}
        return answer
    client = AuditedClient([proposal()], review)
    result = extract_project(simple_project(), client).project
    assert client.calls.count('ExtractionReview') == 2
    assert result.elements[0].analysis_blocked
    assert result.analysis_incomplete == ['R']


def test_partial_invalid_sources_are_recorded_with_full_candidate():
    bad = dict(id='b', type='действие', description='Несохранённый кандидат', source_ids=['MISSING'])
    result = extract_project(simple_project(), AuditedClient([proposal(), bad])).project
    assert len(result.elements) == 1
    assert 'Несохранённый кандидат' in '\n'.join(result.analysis_notes['R'])
    assert 'MISSING' in '\n'.join(result.analysis_notes['R'])
    assert result.analysis_incomplete == ['R']


@pytest.mark.parametrize('problem', ['duplicate_id', 'bad_schema', 'unknown_sources'])
def test_total_contract_failure_preserves_original(problem):
    class Client:
        def complete(self, messages, schema):
            if problem == 'bad_schema': return '{"elements": [{"source_fragment":"invented"}]}'
            items = [proposal(), proposal()] if problem == 'duplicate_id' else [dict(
                id='a', type='действие', description='Проверка', source_ids=['FAKE'])]
            return json.dumps(dict(elements=items))
    original = simple_project()
    before = original.model_dump_json()
    with pytest.raises(LLMError): extract_project(original, Client())
    assert original.model_dump_json() == before


def test_relations_are_supplied_by_model_and_preserved_without_language_parser():
    project = Project(name='Ветви', requirements=[Requirement(id='R', text='A && B -> SendPacket(); !A -> KeepValue().')])
    items = [dict(id='c1', type='условие', description='A', source_ids=['F001']),
             dict(id='c2', type='условие', description='B', source_ids=['F001'], condition_ids=['c1']),
             dict(id='x', type='действие', description='SendPacket()', source_ids=['F001'], condition_ids=['c2']),
             dict(id='y', type='действие', description='KeepValue()', source_ids=['F001'], negated_condition_ids=['c1'])]
    result = extract_project(project, AuditedClient(items)).project
    assert result.elements[1].condition_ids == ['R::E001']
    assert result.elements[2].condition_ids == ['R::E002']
    assert result.elements[3].negated_condition_ids == ['R::E001']


@pytest.mark.parametrize('problem', ['unknown', 'non_condition', 'self', 'overlap', 'duplicate', 'cycle'])
def test_bad_dependency_graph_is_quarantined_with_original_links(problem):
    items = [dict(id='c', type='условие', description='READY = 1', source_ids=['F001']), proposal()]
    if problem == 'unknown': items[1]['condition_ids'] = ['missing']
    if problem == 'non_condition': items[0]['condition_ids'] = ['a']
    if problem == 'self': items[0]['condition_ids'] = ['c']
    if problem == 'overlap': items[1].update(condition_ids=['c'], negated_condition_ids=['c'])
    if problem == 'duplicate': items[1]['condition_ids'] = ['c', 'c']
    if problem == 'cycle':
        items[1].update(type='условие', condition_ids=['c'])
        items[0]['condition_ids'] = ['a']
    result = extract_project(simple_project(), AuditedClient(items)).project
    assert len(result.elements) == 2
    assert any(e.analysis_blocked and e.review_notes for e in result.elements)
    Project.model_validate_json(result.model_dump_json())


def test_blocked_context_propagates_transitively_and_requires_ordered_review():
    project = simple_project()
    data = project.model_dump()
    data['elements'] = [Element(id='c1', requirement_id='R', type='условие', description='READY', source_fragment='READY', analysis_blocked=True).model_dump(),
                        Element(id='c2', requirement_id='R', type='условие', description='READY', source_fragment='READY', condition_ids=['c1']).model_dump(),
                        Element(id='a', requirement_id='R', type='действие', description='TransferWord()', source_fragment='TransferWord()', condition_ids=['c2']).model_dump()]
    project = Project.model_validate(data)
    assert not active_elements(project)
    # c2 is excluded transitively even if its own analysis_blocked flag is false.
    with pytest.raises(ValueError): review_element(project, 'c2', True)
    assert len(active_elements(review_element(project, 'c1', True))) == 3


def test_cancel_between_stages_is_atomic():
    client = AuditedClient([proposal()])
    project = simple_project()
    before = project.model_dump_json()
    with pytest.raises(LLMError, match='отменён'):
        extract_project(project, client, cancelled=lambda: bool(client.calls))
    assert project.model_dump_json() == before


def test_no_rule_adds_modes_or_splits_compound_phrases():
    project = Project(name='Без эвристик', requirements=[Requirement(id='R', text='В режиме CUSTOM сохранить значение и вернуть результат.')])
    item = dict(id='a', type='действие', description='Сохранить значение и вернуть результат', source_ids=['F001'])
    def review(payload):
        answer = clean_review(payload)
        answer.update(coverage_complete=False, findings=[dict(kind='compound', element_ids=['R::E001'], source_ids=['F001'],
                      rationale='Разделить независимые действия')])
        return answer
    result = extract_project(project, AuditedClient([item], review)).project
    assert len(result.elements) == 1
    assert result.elements[0].description == item['description']
    assert result.elements[0].analysis_blocked


def test_manual_add_edit_accept_and_sqlite_roundtrip(tmp_path):
    project = simple_project()
    candidate, identifier = add_manual_element(project, 'R')
    assert not project.elements
    edited = edit_element(candidate, identifier, dict(description='Выполнить TransferWord()', source_fragment='TransferWord()'))
    assert not active_elements(edited)
    accepted = review_element(edited, identifier, True)
    assert len(active_elements(accepted)) == 1
    path = tmp_path / 'проверка.sqlite'
    save_project(accepted, path)
    assert load_project(path) == accepted


def test_context_only_source_does_not_validate_behavior():
    def review(payload):
        answer = clean_review(payload)
        answer['source_assessments'][0]['role'] = 'context'
        return answer
    result = extract_project(simple_project(), AuditedClient([proposal()], review)).project
    assert not active_elements(result)


@pytest.mark.parametrize('kind', ['unsupported', 'contradiction', 'relationship'])
def test_critical_finding_cannot_be_downgraded_by_model_flag(kind):
    def review(payload):
        answer = clean_review(payload)
        answer['findings'] = [dict(kind=kind, blocking=False, element_ids=['R::E001'],
                                   source_ids=['F001'], rationale='Обнаружена ошибка')]
        return answer
    result = extract_project(simple_project(), AuditedClient([proposal()], review)).project
    assert not active_elements(result)


def test_unknown_new_request_does_not_inherit_old_full_coverage():
    from reqtest.services.project_import import merge_import
    result = merge_import(simple_project(), [Requirement(id='NEW', text='Иное поведение')], 'requirements')
    assert result.analysis_incomplete == ['NEW']
