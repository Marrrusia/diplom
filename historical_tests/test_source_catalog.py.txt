"""Новый контракт: адресуемые источники вместо цитат, перепечатанных моделью."""
import json
import pytest
from reqtest.models.domain import Project, Requirement, Element, SourceReference
from reqtest.services.source_catalog import build_source_catalog
from reqtest.services.extraction import extract_project
from reqtest.storage.sqlite_project import save_project, load_project
from reqtest.services.review import edit_element
from reqtest.llm.client import LLMError

TEXT = ('Компонент должен сохранить value в currentLevel и вернуть STATUS_OK. '
        'Если value меньше нуля, компонент должен оставить currentLevel без изменения.')


@pytest.mark.parametrize('text', [TEXT, 'Первое.\nВторое.', 'ReadADC() возвращает 1.25. Далее crcHandle.Instance равно CRC.',
    '  Первая строка\r\n\r\nВторая строка  ', 'Текст «в кавычках»; Другое действие.', 'Один фрагмент без точки'])
def test_source_spans_match_exact_original(text):
    sources=build_source_catalog(text)
    assert sources
    assert len({s.source_id for s in sources})==len(sources)
    assert all(text[s.start:s.end]==s.text for s in sources)
    assert sources==build_source_catalog(text)


def test_names_and_decimals_not_split():
    sources=build_source_catalog('Проверить crcHandle.Instance = 1.25. Затем продолжить.')
    assert len(sources)==2
    assert 'crcHandle.Instance = 1.25.' in sources[0].text


def project():
    return Project(name='Новый источник',requirements=[Requirement(id='R',text=TEXT)])


def response(elements):
    return json.dumps({'elements':elements},ensure_ascii=False)


def test_separated_actions_share_source_without_retyping_quotes():
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            payload=json.loads(messages[-1]['content'])
            assert payload['sources'][0]['id']=='F001'
            assert 'source_fragment' not in schema['$defs']['ProposedElement']['properties']
            return response([
                {'type':'действие','description':'Сохранить value в currentLevel','source_ids':['F001']},
                {'type':'действие','description':'Компонент должен вернуть STATUS_OK','source_ids':['F001']},
                {'type':'ограничение','description':'Компонент должен оставить currentLevel без изменения','source_ids':['F002']}])
    client=Client()
    result=extract_project(project(),client)
    assert client.calls==1
    assert len(result.project.elements)==4
    assert result.project.elements[2].condition_ids == [result.project.elements[3].id]
    assert result.project.elements[0].source_fragment==result.project.elements[1].source_fragment
    assert all(e.source_fragment in TEXT for e in result.project.elements)
    assert result.project.elements[2].source_refs[0].source_id=='F002'


@pytest.mark.parametrize('ids',[['UNKNOWN'],['F001','F001'],[]])
def test_bad_source_references_never_applied(ids):
    class Client:
        def complete(self,messages,schema):
            return response([{'type':'действие','description':'Вернуть STATUS_OK','source_ids':ids}])
    p=project(); before=p.model_dump_json()
    with pytest.raises(LLMError):extract_project(p,Client())
    assert p.model_dump_json()==before


def test_wrong_source_cannot_support_technical_fact_from_other_sentence():
    class Client:
        def complete(self,messages,schema):
            return response([{'type':'действие','description':'Вернуть STATUS_OK','source_ids':['F002']}])
    with pytest.raises(LLMError,match='STATUS_OK'):
        extract_project(project(),Client())


def test_old_llm_quote_contract_rejected_with_repair_request():
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            if self.calls==1:
                return response([{'type':'действие','description':'Вернуть STATUS_OK','source_fragment':TEXT}])
            assert 'source_ids' in messages[-1]['content']
            return response([{'type':'действие','description':'Вернуть STATUS_OK','source_ids':['F001']}])
    client=Client()
    assert extract_project(project(),client).project.elements
    assert client.calls==2


def test_multiple_sources_have_exact_span_and_individual_references():
    p=Project(name='Несколько источников',requirements=[Requirement(id='R',text='Режим задан. Прочие сведения. Операция завершена.')])
    class Client:
        def complete(self,messages,schema):
            return response([{'type':'условие','description':'Условие операции','source_ids':['F003','F001']}])
    result=extract_project(p,Client()).project
    assert [r.source_id for r in result.elements[0].source_refs]==['F001','F003']
    assert result.elements[0].source_fragment==p.requirements[0].text


def test_sqlite_supports_old_and_new_elements(tmp_path):
    p=project()
    old=Element(id='E',requirement_id='R',type='действие',description='Вернуть STATUS_OK',source_fragment='вернуть STATUS_OK')
    data=p.model_dump();data['elements']=[old.model_dump(exclude={'source_refs'})]
    loaded=Project.model_validate(data)
    assert loaded.elements[0].source_refs==[]
    path=tmp_path/'old.sqlite';save_project(loaded,path);assert load_project(path)==loaded
    ref=build_source_catalog(TEXT)[0]
    data['elements']=[Element(id='E',requirement_id='R',type='действие',description='Вернуть STATUS_OK',source_fragment=ref.text,source_refs=[ref]).model_dump()]
    new=Project.model_validate(data)
    path=tmp_path/'new.sqlite';save_project(new,path);assert load_project(path)==new
    changed=edit_element(new,'E',{'source_fragment':'вернуть STATUS_OK'})
    assert changed.elements[0].source_refs==[]


def test_corrupted_saved_offsets_rejected():
    p=project();data=p.model_dump();ref=build_source_catalog(TEXT)[0].model_dump();ref['start']=1
    data['elements']=[{'id':'E','requirement_id':'R','type':'действие','description':'Вернуть STATUS_OK','source_fragment':TEXT[:ref['end']],'source_refs':[ref]}]
    with pytest.raises(ValueError,match='смещения'):Project.model_validate(data)


def test_source_references_exported_as_structured_json(tmp_path):
    from openpyxl import load_workbook
    from reqtest.exporters.xlsx_report import export_report
    p=project();ref=build_source_catalog(TEXT)[0]
    data=p.model_dump()
    data['elements']=[Element(id='E',requirement_id='R',type='действие',description='Вернуть STATUS_OK',
        source_fragment=ref.text,source_refs=[ref]).model_dump()]
    path=tmp_path/'sources.xlsx'
    export_report(Project.model_validate(data),path)
    book=load_workbook(path)
    rows=list(book['Elements'].values)
    index=rows[0].index('source_refs')
    saved=json.loads(rows[1][index])
    assert saved==[ref.model_dump()]
    book.close()


def test_condition_with_result_is_saved_with_review_note_not_aborted():
    text='Если value меньше нуля, компонент должен вернуть STATUS_RANGE_ERROR.'
    p=Project(name='Мягкая проверка',requirements=[Requirement(id='R',text=text)])
    class Client:
        calls=0
        def complete(self,messages,schema):
            self.calls+=1
            return response([{'type':'ограничение','description':text,'source_ids':['F001']}])
    client=Client()
    result=extract_project(p,client)
    assert client.calls==1
    element=result.project.elements[0]
    assert element.review_status.value=='ожидает проверки'
    assert any('Условие ветви' in note for note in element.review_notes)
    assert result.project.analysis_notes['R']
    assert not result.project.coverage


def test_structural_warning_does_not_hide_fabricated_fact():
    text='Если value меньше нуля, компонент должен вернуть STATUS_RANGE_ERROR.'
    p=Project(name='Ошибка фактов',requirements=[Requirement(id='R',text=text)])
    class Client:
        def complete(self,messages,schema):
            return response([{'type':'ограничение','description':'Если value меньше нуля, вернуть STATUS_FAKE','source_ids':['F001']}])
    with pytest.raises(LLMError,match='STATUS_FAKE'):
        extract_project(p,Client())
    assert not p.elements
