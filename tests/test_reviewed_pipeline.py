"""Регрессии частичного результата, полноты и повторного импорта."""
import json
import pytest
from reqtest.models.domain import Project,Requirement,ReviewStatus,TestCase as Case,TestSource as Source
from reqtest.services.extraction import extract_project
from reqtest.services.coverage import coverage_summary
from reqtest.services.review import review_element,confirm_completeness,edit_element
from reqtest.services.project_import import merge_import
from reqtest.storage.sqlite_project import save_project,load_project
from reqtest.exporters.xlsx_report import export_report
from openpyxl import load_workbook


class Client:
    def __init__(self,items): self.items=items
    def complete(self,messages,schema): return json.dumps({'elements':self.items})


def test_bad_item_does_not_erase_good_result_or_invent_coverage(tmp_path):
    original=Project(name='P',requirements=[Requirement(id='R',text='Вернуть RESULT_OK.')])
    result=extract_project(original,Client([
        dict(type='действие',description='Вернуть RESULT_OK',source_ids=['F001']),
        dict(type='действие',description='Вернуть RESULT_FAKE',source_ids=['F001'])])).project
    assert len(result.elements)==1
    assert not original.elements
    assert result.elements[0].review_status==ReviewStatus.PENDING
    assert any('RESULT_FAKE' in n for n in result.analysis_notes['R'])
    assert coverage_summary(result)['total']['percent'] is None
    save_project(result,tmp_path/'p.sqlite')
    assert load_project(tmp_path/'p.sqlite')==result
    export_report(result,tmp_path/'p.xlsx')
    book=load_workbook(tmp_path/'p.xlsx')
    assert book['Summary']['C2'].value=='не определено'
    book.close()


def test_gap_sentence_never_becomes_test_element():
    project=Project(name='P',requirements=[Requirement(id='R',text='Выдать RESULT_OK. Поведение при FAULT не определено.')])
    result=extract_project(project,Client([
        dict(type='действие',description='Выдать RESULT_OK',source_ids=['F001']),
        dict(type='условие',description='Установлен FAULT',source_ids=['F002'])])).project
    assert len(result.elements)==1
    assert any('не определено' in n for n in result.analysis_notes['R'])


def test_completeness_requires_accepted_elements_and_is_invalidated():
    result=extract_project(Project(name='P',requirements=[Requirement(id='R',text='Вернуть RESULT_OK.')]),Client([
        dict(type='действие',description='Вернуть RESULT_OK',source_ids=['F001'])])).project
    with pytest.raises(ValueError): confirm_completeness(result,'R','Проверено')
    result=review_element(result,result.elements[0].id,True)
    result=confirm_completeness(result,'R','Все результаты и условия сверены с исходником')
    assert not result.analysis_incomplete and coverage_summary(result)['total']['percent']==0
    changed=edit_element(result,result.elements[0].id,{'description':'Вернуть RESULT_OK после проверки'})
    assert changed.analysis_incomplete==['R']


def test_reimport_identical_is_noop_but_conflict_and_file_duplicates_fail():
    req=Requirement(id='R',text='Вернуть RESULT_OK.')
    project=Project(name='P',requirements=[req])
    assert merge_import(project,[req],'requirements')==project
    with pytest.raises(ValueError): merge_import(project,[req,req],'requirements')
    with pytest.raises(ValueError): merge_import(project,[Requirement(id='R',text='Другое.')],'requirements')


def test_rejected_generated_test_remains_rejected():
    req=Requirement(id='R',text='Вернуть RESULT_OK.')
    case=Case(id='T',requirement_id='R',title='T',preconditions=[],input_data={},steps=['Вызвать'],expected_result='RESULT_OK',source=Source.GENERATED,review_status=ReviewStatus.REJECTED)
    project=Project(name='P',requirements=[req],test_cases=[case])
    result=extract_project(project,Client([dict(type='действие',description='Вернуть RESULT_OK',source_ids=['F001'])])).project
    assert result.test_cases[0].review_status==ReviewStatus.REJECTED


def test_old_snapshot_needs_completeness_review_without_mutating_file(tmp_path):
    import sqlite3
    req=Requirement(id='R',text='Вернуть RESULT_OK.')
    path=tmp_path/'old.sqlite'
    save_project(Project(name='P',requirements=[req]),path)
    with sqlite3.connect(path) as db:
        value=json.loads(db.execute('SELECT payload FROM project_snapshot WHERE id=1').fetchone()[0])
        value.pop('analysis_incomplete')
        db.execute('UPDATE project_snapshot SET payload=? WHERE id=1',(json.dumps(value),))
    original=path.read_bytes()
    restored=load_project(path)
    assert restored.analysis_incomplete==['R'] and path.read_bytes()==original


def test_completeness_action_is_available_in_ui():
    from PySide6.QtWidgets import QApplication,QPushButton
    from reqtest.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow()
    assert any('Подтвердить полноту' in button.text() for button in window.findChildren(QPushButton))
    window.close()
