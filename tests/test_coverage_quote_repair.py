"""Цитаты покрытия: оформление, повторное исправление, атомарность и разделение полей."""
import json
import pytest
from reqtest.models.demo import demo_project
from reqtest.models.domain import TestCase as Case, Project
from reqtest.services.coverage import analyze_coverage
from reqtest.llm.client import LLMError


def project():
    p = demo_project()
    data = p.model_dump()
    data['elements'] = [data['elements'][0]]
    data['test_cases'] = [Case(id='T1', requirement_id=p.requirements[0].id, title='Тест',
        preconditions=['Instance равно CRC'], steps=['Вызвать HAL_CRC_MspInit'],
        expected_result='Тактирование  CRC включено').model_dump()]
    return Project.model_validate(data)


def response(**changes):
    result = {'status':'покрыт','confidence':0.95,'rationale':'Проверен вызов',
        'precondition_evidence':['Instance равно CRC'], 'step_evidence':['Вызвать HAL_CRC_MspInit'],
        'result_evidence':['Тактирование CRC включено']}
    result.update(changes)
    return json.dumps(result,ensure_ascii=False)


def test_formatting_restored_without_retry():
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            return response(step_evidence=['вызвать HAL_CRC_MspInit'])
    client=Client()
    result=analyze_coverage(project(),client)
    assert client.calls==1
    assert 'Тактирование  CRC включено' in result.coverage[0].rationale
    assert 'Вызвать HAL_CRC_MspInit' in result.coverage[0].rationale
    assert not result.coverage[0].confirmed


def test_paraphrased_test_quote_repaired():
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            if self.calls==1:
                return response(step_evidence=['Выполнить инициализацию CRC'])
            assert 'Выполнить инициализацию CRC' in messages[-1]['content']
            return response()
    client=Client()
    result=analyze_coverage(project(),client)
    assert client.calls==2
    assert len(result.coverage)==1


def test_persistent_wrong_field_quote_fails_without_partial_result():
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            return response(step_evidence=['Instance равно CRC'])
    p=project()
    before=p.model_dump_json()
    client=Client()
    with pytest.raises(LLMError,match='3 попыток') as error:
        analyze_coverage(p,client)
    assert client.calls==3
    assert 'step_evidence' in str(error.value)
    assert p.model_dump_json()==before


def test_missing_proof_can_be_reported_without_fabrication():
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            if self.calls==1:
                return response(result_evidence=['Вернулся несуществующий STATUS_OK'])
            return response(status='не покрыт',result_evidence=[])
    result=analyze_coverage(project(),Client())
    assert result.coverage[0].status.value=='не покрыт'
    assert not result.coverage[0].confirmed


@pytest.mark.parametrize('field',['step_evidence','result_evidence'])
def test_blank_evidence_is_absence_not_invented_quote(field):
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            return response(**{field:['','  ','\n\t']})
    client=Client();original=project();before=original.model_dump_json()
    result=analyze_coverage(original,client)
    assert client.calls==1
    assert len(result.coverage)==1
    assert result.coverage[0].status.value=='требует проверки'
    assert 'Нет цитат действий или ожидаемого результата' in result.coverage[0].rationale
    assert not result.coverage[0].confirmed
    assert original.model_dump_json()==before


def test_blank_entries_do_not_discard_valid_evidence():
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            return response(step_evidence=['','Вызвать HAL_CRC_MspInit','  '])
    client=Client();result=analyze_coverage(project(),client)
    assert client.calls==1
    evidence=json.loads(result.coverage[0].rationale.split('Цитаты теста: ')[1].split('\n')[0])
    assert evidence['steps']==['Вызвать HAL_CRC_MspInit']


def test_blank_evidence_does_not_stop_later_pairs():
    original=project();data=original.model_dump()
    second=dict(data['test_cases'][0]);second['id']='T2';data['test_cases'].append(second)
    original=Project.model_validate(data)
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            return response(step_evidence=['']) if self.calls==1 else response()
    client=Client();result=analyze_coverage(original,client)
    assert client.calls==2
    assert [link.test_case_id for link in result.coverage]==['T1','T2']
    assert result.coverage[0].status.value=='требует проверки'
