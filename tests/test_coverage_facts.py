"""Числовые условия и сохранность состояния с произвольными именами."""
import pytest
from reqtest.services.coverage_facts import condition_truth, assignments, coverage_facts, decision_conflicts
from reqtest.models.domain import Element, Requirement, Project, TestCase as Case


@pytest.mark.parametrize('description,inputs,expected', [
    ('Если speed меньше -2 или больше 7', {'speed':'8'}, True),
    ('Если speed меньше -2 или больше 7', {'speed':'-3'}, True),
    ('Если speed меньше -2 или больше 7', {'speed':'7'}, False),
    ('Если temp больше или равно 1,5', {'temp':'1.50'}, True),
    ('Если temp <= -2.5', {'temp':'-2.6'}, True),
    ('Если a > 1 и b != 0', {'a':'2','b':'0'}, False),
    ('Если a > 1 или b != 0', {'a':'0','b':'2'}, True),
    ('x в диапазоне от -1 до 1 включительно', {'x':'1'}, True),
    ('Если x больше 0', {}, None),
    ('Если x больше 0', {'x':'неизвестно'}, None),
    ('Если x больше 0 после сброса', {'x':'1'}, None),
    ('Если (x больше 0)', {'x':'1'}, None),
    ('Если x больше 0 или y меньше 2', {'x':'1'}, None),
])
def test_three_valued_numeric_conditions(description, inputs, expected):
    assert condition_truth(description, inputs) is expected


def sample(value='13', changed=False):
    text = 'Если pressure меньше -4 или больше 12, оставить sensor.value без изменения.'
    r = Requirement(id='ANY', text=text)
    condition = Element(id='C', requirement_id=r.id, type='условие',
        description='Если pressure меньше -4 или больше 12', source_fragment=text)
    action = Element(id='A', requirement_id=r.id, type='ограничение',
        description='оставить sensor.value без изменения', source_fragment=text, condition_ids=['C'])
    p = Project(name='Факты', requirements=[r], elements=[condition, action])
    test = Case(id='T', requirement_id=r.id, title='Состояние', input_data={'pressure':value},
        preconditions=['sensor.value = 3.0'], steps=['Вызвать обработчик', 'Проверить sensor.value'],
        expected_result='sensor.value = '+('4' if changed else '3'))
    return p, action, test


def test_initial_and_expected_state_are_compared():
    p,e,t = sample()
    facts = coverage_facts(p,e,t)
    assert facts['applicable'] is True
    assert facts['state_unchanged'] is True
    assert decision_conflicts('не покрыт', facts, t)
    assert not decision_conflicts('покрыт', facts, t)


def test_changed_state_blocks_positive_proposal():
    p,e,t = sample(changed=True)
    facts = coverage_facts(p,e,t)
    assert facts['state_unchanged'] is False
    assert decision_conflicts('покрыт',facts,t)


def test_wrong_input_blocks_positive_proposal():
    p,e,t = sample(value='5')
    assert decision_conflicts('покрыт',coverage_facts(p,e,t),t)


def test_ambiguous_assignments_are_not_proof():
    assert assignments('counter = 3; counter = 4') == {}
    p,e,t = sample()
    t.preconditions=[]
    facts=coverage_facts(p,e,t)
    assert facts['state_unchanged'] is None
    assert not decision_conflicts('не покрыт',facts,t)


def test_negated_condition():
    p,e,t=sample(value='5')
    e.condition_ids=[]
    e.negated_condition_ids=['C']
    assert coverage_facts(p,e,t)['applicable'] is True


def test_condition_only_does_not_inherit_other_aspects():
    from reqtest.services.numeric_context import numeric_context
    text='При вызове Run с аргументом count в диапазоне от 1 до 8 включительно вернуть OK. Если count меньше 1 или больше 8, вернуть ERROR.'
    e=Element(id='E',requirement_id='R',type='условие',description='При вызове Run',source_fragment=text)
    t=Case(id='T',requirement_id='R',title='Вызов',input_data={'count':'9'},steps=['Вызвать Run(9)'],expected_result='Возвращён ERROR')
    assert numeric_context(text,e,t)['issues']==[]


def test_analysis_downgrades_false_negative_without_confirming_it():
    import json
    from reqtest.services.coverage import analyze_coverage, coverage_summary
    p,e,t=sample()
    p.test_cases=[t]
    class Client:
        def complete(self,messages,schema):
            data=json.loads(messages[-1]['content'])
            assert 'facts' in data['deterministic_check']
            return json.dumps({'status':'не покрыт','confidence':0.9,'rationale':'Модель не заметила результат'})
    result=analyze_coverage(p,Client())
    assert all(link.status.value=='требует проверки' for link in result.coverage)
    assert coverage_summary(result)['total']['covered']==0
    assert not p.coverage


def test_plain_invocation_not_replaced_with_range_condition():
    p,e,t=sample()
    data=p.model_dump()
    data['elements'][1].update(type='условие',description='При вызове Refresh',condition_ids=[])
    p=Project.model_validate(data)
    t.steps=['Вызвать Refresh(13)']
    facts=coverage_facts(p,p.elements[1],t)
    assert facts['explicit_trigger_matches']
    assert decision_conflicts('не покрыт',facts,t)


def test_return_result_used_only_when_applicability_known():
    p,e,t=sample()
    e.description='вернуть STATUS_LIMIT'
    t.expected_result='Возвращён STATUS_LIMIT'
    assert decision_conflicts('не покрыт',coverage_facts(p,e,t),t)
    t.input_data={}
    assert not decision_conflicts('не покрыт',coverage_facts(p,e,t),t)
