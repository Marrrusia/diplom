"""Диапазоны: параметры из ключей, конкретные значения, ветви и независимые действия."""
import json
import pytest
from reqtest.models.domain import Project, Requirement, Element, ElementType, TestCase as Case
from reqtest.services.coverage import analyze_coverage
from reqtest.services.semantic_extraction import unsupported_literals
from reqtest.services.extraction import ExtractedElement

TEXT = ('При вызове SetLevel с целочисленным аргументом value в диапазоне от 0 до 100 включительно '
        'компонент должен сохранить value в поле currentLevel и вернуть STATUS_OK. '
        'Если value меньше 0 или больше 100, компонент должен вернуть STATUS_RANGE_ERROR и оставить currentLevel без изменения.')


def setup(fragment, kind='действие', value='50', expected='currentLevel = 50; возвращён STATUS_OK'):
    test = Case(id='T',requirement_id='R',title='Тест',preconditions=['currentLevel = 25'],
        input_data={'value':value},steps=[f'Вызвать SetLevel({value})','Проверить currentLevel и возвращаемый статус'],expected_result=expected)
    element = Element(id='E',requirement_id='R',type=kind,description=fragment,source_fragment=fragment)
    project = Project(name='Диапазон',requirements=[Requirement(id='R',text=TEXT)],elements=[element],test_cases=[test])
    class Client:
        payload=None
        def complete(self,messages,schema):
            self.payload=json.loads(messages[-1]['content'])
            return json.dumps({'status':'покрыт','confidence':0.95,'rationale':'Проверено действие для конкретного входа',
                'step_evidence':test.steps,'precondition_evidence':test.preconditions,'result_evidence':[test.expected_result]})
    return project,Client()


def test_parameter_name_in_key_is_available_for_action():
    p,client=setup('компонент должен сохранить value в поле currentLevel')
    result=analyze_coverage(p,client)
    assert result.coverage[0].status.value=='покрыт'
    assert not result.coverage[0].confirmed
    assert 'value' in client.payload['deterministic_check']['matched']
    assert not client.payload['deterministic_check']['missing']


@pytest.mark.parametrize('value',['0','50','100'])
def test_valid_branch_point_does_not_need_both_boundary_literals(value):
    p,client=setup('При вызове SetLevel с целочисленным аргументом value в диапазоне от 0 до 100 включительно', 'условие',value, f'currentLevel = {value}; возвращён STATUS_OK')
    result=analyze_coverage(p,client)
    assert result.coverage[0].status.value=='покрыт'
    assert not client.payload['deterministic_check']['missing']
    assert client.payload['deterministic_check']['numeric_context']['parameters'][0]['inside']


@pytest.mark.parametrize('value',['-1','101'])
def test_negative_branch_matches_outside_point(value):
    p,client=setup('Если value меньше 0 или больше 100', 'условие',value,'Возвращён STATUS_RANGE_ERROR; currentLevel = 25')
    assert analyze_coverage(p,client).coverage[0].status.value=='покрыт'
    assert not client.payload['deterministic_check']['missing']


def test_invalid_input_cannot_cover_valid_branch_even_if_model_says_yes():
    p,client=setup('компонент должен сохранить value в поле currentLevel',value='101',expected='currentLevel = 101; возвращён STATUS_OK')
    result=analyze_coverage(p,client)
    assert result.coverage[0].status.value=='требует проверки'
    assert 'не соответствует ветви' in result.coverage[0].rationale


def test_single_point_never_proves_whole_range():
    p,client=setup('в диапазоне от 0 до 100 включительно','диапазон','50')
    result=analyze_coverage(p,client)
    assert result.coverage[0].status.value=='требует проверки'
    assert 'не доказывает' in result.coverage[0].rationale


def test_unrelated_numeric_constant_stays_required():
    p,client=setup('компонент должен сохранить value в поле currentLevel')
    data=p.model_dump()
    data['requirements'][0]['text']+=' Число повторов 7.'
    data['elements'][0].update(description='Число повторов 7',source_fragment='Число повторов 7')
    result=analyze_coverage(Project.model_validate(data),client)
    assert result.coverage[0].status.value=='требует проверки'
    assert '7' in client.payload['deterministic_check']['missing']


@pytest.mark.parametrize('description,kind',[
    ('компонент должен сохранить value в поле currentLevel и вернуть STATUS_OK','действие'),
    ('Если value меньше 0 или больше 100, компонент должен вернуть STATUS_RANGE_ERROR и оставить currentLevel без изменения','ограничение')])
def test_compound_description_is_not_rejected_by_literal_checker(description,kind):
    item=ExtractedElement(type=kind,description=description,source_fragment=description)
    assert not unsupported_literals(item.description, TEXT)


def test_catalog_source_does_not_require_all_tokens_of_broad_sentence():
    from reqtest.services.source_catalog import build_source_catalog
    p,client=setup('компонент должен сохранить value в поле currentLevel')
    data=p.model_dump()
    source=build_source_catalog(TEXT)[0]
    data['elements'][0].update(source_fragment=source.text,source_refs=[source.model_dump()])
    result=analyze_coverage(Project.model_validate(data),client)
    assert result.coverage[0].status.value=='покрыт'
    assert not client.payload['deterministic_check']['missing']
    assert 'STATUS_OK' not in client.payload['deterministic_check']['missing']


def test_catalog_positive_branch_still_rejects_outside_value():
    from reqtest.services.source_catalog import build_source_catalog
    p,client=setup('компонент должен сохранить value в поле currentLevel',value='101',expected='currentLevel = 101; возвращён STATUS_OK')
    data=p.model_dump();source=build_source_catalog(TEXT)[0]
    data['elements'][0].update(source_fragment=source.text,source_refs=[source.model_dump()])
    result=analyze_coverage(Project.model_validate(data),client)
    assert result.coverage[0].status.value=='требует проверки'
    assert 'не соответствует ветви' in result.coverage[0].rationale
