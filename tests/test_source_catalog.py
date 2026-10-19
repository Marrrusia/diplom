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




@pytest.mark.parametrize('ids',[['UNKNOWN'],['F001','F001'],[]])
def test_bad_source_references_never_applied(ids):
    class Client:
        def complete(self,messages,schema):
            return response([{'type':'действие','description':'Вернуть STATUS_OK','source_ids':ids}])
    p=project(); before=p.model_dump_json()
    with pytest.raises(LLMError):extract_project(p,Client())
    assert p.model_dump_json()==before






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
