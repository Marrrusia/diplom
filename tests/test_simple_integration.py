"""Интеграция простого ответа без классификации, разбиения и проверки перефразов."""
import json
import pytest
from openpyxl import load_workbook
from reqtest.models.domain import Project,Requirement,ElementType,ReviewStatus,LLMSettings,TestCase as Case
from reqtest.services.extraction import extract_project
from reqtest.services.review import edit_element,review_element,confirm_completeness
from reqtest.services.coverage import active_elements,coverage_summary,analyze_coverage
from reqtest.services.generation import generate_tests,GenerationMode
from reqtest.storage.sqlite_project import save_project,load_project
from reqtest.exporters.xlsx_report import export_report
from reqtest.llm.client import LLMError

TEXT='При вызове ReadSample в режиме STANDBY компонент должен вернуть STATUS_NOT_READY и не вызывать StartADC.'


class Client:
    def __init__(self,items,gaps=None): self.items=items; self.gaps=gaps or []; self.calls=0
    def complete(self,messages,schema):
        self.calls+=1
        assert messages[1]['content']==TEXT
        assert 'type' not in schema['$defs']['Obligation']['properties']
        return json.dumps(dict(obligations=self.items,specification_gaps=self.gaps),ensure_ascii=False)


def item(statement='Возвратить STATUS_NOT_READY',conditions=None,quote=TEXT):
    return dict(statement=statement,conditions=['Когда вызван ReadSample в режиме STANDBY'] if conditions is None else conditions,source_fragment=quote)


def run(items):
    client=Client(items)
    original=Project(name='P',requirements=[Requirement(id='R',text=TEXT)])
    result=extract_project(original,client).project
    assert client.calls==1 and not original.elements
    return result


def test_paraphrasing_is_not_an_error_and_no_condition_nodes_created():
    result=run([item(),item('Не вызывать StartADC')])
    assert len(result.elements)==2
    assert all(e.type==ElementType.OBLIGATION and not e.condition_ids and not e.analysis_blocked for e in result.elements)
    assert result.elements[0].conditions==['Когда вызван ReadSample в режиме STANDBY']
    assert result.elements[0].review_notes==[]
    assert coverage_summary(result)['total']['percent'] is None


def test_no_automatic_split_or_implied_conditions():
    result=run([item('Вернуть STATUS_NOT_READY и не вызывать StartADC',conditions=[])])
    assert len(result.elements)==1 and not result.elements[0].conditions


def test_wrong_citation_is_visible_but_cannot_be_used_or_accepted():
    result=run([item(quote='При вызове ... вернуть STATUS_NOT_READY')])
    element=result.elements[0]
    assert element.analysis_blocked and element.review_notes
    assert not active_elements(result)
    with pytest.raises(ValueError): review_element(result,element.id,True)
    corrected=edit_element(result,element.id,dict(source_fragment=TEXT))
    assert not corrected.elements[0].analysis_blocked and active_elements(corrected)
    accepted=review_element(corrected,element.id,True)
    assert accepted.elements[0].review_status==ReviewStatus.ACCEPTED


def test_storage_report_and_editor_preserve_conditions(tmp_path):
    result=run([item()])
    path=tmp_path/'p.sqlite';save_project(result,path)
    restored=load_project(path)
    assert restored==result
    xlsx=tmp_path/'p.xlsx';export_report(restored,xlsx)
    book=load_workbook(xlsx)
    rows=list(book['Elements'].values);index=rows[0].index('conditions')
    assert json.loads(rows[1][index])==result.elements[0].conditions
    book.close()
    from PySide6.QtWidgets import QApplication
    from reqtest.ui.edit_dialogs import ElementEditorDialog
    app=QApplication.instance() or QApplication([])
    dialog=ElementEditorDialog(result,result.elements[0])
    dialog.conditions.setPlainText('ReadSample вызван\nРежим STANDBY')
    updated=dialog.apply()
    assert updated.elements[0].conditions==['ReadSample вызван','Режим STANDBY']
    assert updated.analysis_incomplete==['R']
    dialog.close()


def test_conditions_reach_coverage_and_generation():
    result=run([item()])
    data=result.model_dump();data['test_cases']=[Case(id='T',requirement_id='R',title='T',steps=['Вызвать ReadSample'],preconditions=['STANDBY'],expected_result='STATUS_NOT_READY').model_dump()]
    project=Project.model_validate(data)
    class CoverageClient:
        def complete(self,messages,schema):
            payload=json.loads(messages[-1]['content'])
            assert payload['applicability']['all_true']==result.elements[0].conditions
            assert payload['element']['conditions']==result.elements[0].conditions
            return json.dumps(dict(status='не покрыт',rationale='Нужна проверка',confidence=0.9,precondition_evidence=[],step_evidence=[],result_evidence=[]))
    analyze_coverage(project,CoverageClient())
    class Generator:
        settings=LLMSettings(model='test')
        def complete(self,messages,schema):
            payload=json.loads(messages[-1]['content'])
            assert payload['target_elements'][0]['conditions']==result.elements[0].conditions
            assert payload['covered_element_ids']==[]
            return json.dumps(dict(tests=[],specification_gaps=[]))
    generate_tests(project,Generator(),GenerationMode.MISSING)


def test_invalid_json_has_no_correction_request(tmp_path,monkeypatch):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path))
    class Broken:
        calls=0
        def complete(self,messages,schema): self.calls+=1; return '{bad'
    client=Broken(); project=Project(name='P',requirements=[Requirement(id='R',text=TEXT)])
    with pytest.raises(LLMError): extract_project(project,client)
    assert client.calls==1 and not project.elements
    diagnostic=json.loads(next(tmp_path.glob('extraction-diagnostics-*.json')).read_text(encoding='utf-8'))
    assert diagnostic['attempts'][0]['response']=='{bad'


def test_fullness_can_only_be_confirmed_after_review():
    result=run([item()]);element=result.elements[0]
    with pytest.raises(ValueError): confirm_completeness(result,'R','Проверено')
    reviewed=review_element(result,element.id,True)
    confirmed=confirm_completeness(reviewed,'R','Все обязательства и условия сверены с исходным текстом')
    assert coverage_summary(confirmed)['total']['percent']==0
    changed=edit_element(confirmed,element.id,dict(conditions=['ReadSample вызван в STANDBY']))
    assert coverage_summary(changed)['total']['percent'] is None


def test_blocked_element_is_not_a_generation_target_or_covered_fact():
    result=run([item(),item('Не вызывать StartADC',quote='Нет такой цитаты')])
    class Generator:
        settings=LLMSettings(model='test')
        def complete(self,messages,schema):
            payload=json.loads(messages[-1]['content'])
            assert len(payload['target_elements'])==1
            assert result.elements[1].id not in payload['covered_element_ids']
            return '{"tests":[],"specification_gaps":[]}'
    generate_tests(result,Generator(),GenerationMode.FULL)


@pytest.mark.parametrize('case',json.loads((__import__('pathlib').Path(__file__).parent/'fixtures/simple_user_answers.json').read_text(encoding='utf-8')),ids=lambda case:case['name'])
def test_user_examples_are_not_rewritten(case):
    class Saved:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            return json.dumps(case['answer'],ensure_ascii=False)
    client=Saved()
    project=Project(name='Replay',requirements=[Requirement(id='R',text=case['text'])])
    result=extract_project(project,client).project
    assert client.calls==1
    assert len(result.elements)==len(case['answer']['obligations'])
    assert sum(e.analysis_blocked for e in result.elements)==case['blocked']
    for element,original in zip(result.elements,case['answer']['obligations']):
        assert element.description==original['statement']
        assert element.conditions==original['conditions']
        assert element.source_fragment==original['source_fragment']
    assert coverage_summary(result)['total']['percent'] is None


def test_main_table_displays_text_conditions():
    from PySide6.QtWidgets import QApplication
    from reqtest.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow();window.project=run([item()]);window.refresh_tables()
    assert window.elements_table.columnCount()==7
    assert window.elements_table.item(0,4).text()==window.project.elements[0].conditions[0]
    window.show_element(0)
    assert window.project.elements[0].conditions[0] in window.element_details.toPlainText()
    window.close()
