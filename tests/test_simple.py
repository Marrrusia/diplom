"""Проверки одного запроса и отсутствия скрытой обработки результатов."""
import json
import httpx
import pytest
from core import analyze,inspect_answer


TEXT='При вызове Check в режиме WAIT компонент должен вернуть RESULT_WAIT и не вызывать Start. В режиме RUN при READY=1 вызвать Read() и вернуть значение. Для READY=0 поведение не определено.'


def raw_answer():
    return json.dumps(dict(obligations=[
        dict(statement='Вернуть RESULT_WAIT',conditions=['При вызове Check','в режиме WAIT'],source_fragment='вернуть RESULT_WAIT'),
        dict(statement='Не вызывать Start',conditions=['При вызове Check','в режиме WAIT'],source_fragment='не вызывать Start')],specification_gaps=['Для READY=0 поведение не определено.']),ensure_ascii=False)


def test_single_request_keeps_raw_and_result_without_categories():
    calls=[]; received=[]
    def handler(request):
        calls.append(request); payload=json.loads(request.content)
        assert payload['model']=='qwen35-9b-q5:latest' and payload['think'] is False
        assert payload['messages'][1]['content']==TEXT
        assert 'source_ids' not in payload['format']['$defs']['Obligation']['properties']
        assert 'type' not in payload['format']['$defs']['Obligation']['properties']
        return httpx.Response(200,json={'message':{'content':raw_answer()}})
    result=analyze(TEXT,'http://test','qwen35-9b-q5:latest',httpx.MockTransport(handler),received.append)
    assert len(calls)==1 and received[0]['raw_response']==raw_answer()
    assert result['raw_response']==raw_answer() and not result['warnings']
    assert result['parsed']==json.loads(raw_answer())


def test_invalid_json_not_retried_and_raw_preserved():
    calls=[]
    def handler(request):
        calls.append(request); return httpx.Response(200,json={'message':{'content':'{broken'}})
    result=analyze(TEXT,'http://test','test',httpx.MockTransport(handler))
    assert len(calls)==1 and result['parsed'] is None
    assert result['raw_response']=='{broken' and result['status']=='invalid_structure'


def test_missing_quote_warns_without_dropping_or_correcting_element():
    value=json.loads(raw_answer()); value['obligations'][0]['source_fragment']='invented quote'
    raw=json.dumps(value)
    parsed,warnings=inspect_answer(TEXT,raw)
    assert parsed==value and len(warnings)==1


def test_unquoted_condition_is_visible_as_warning():
    value=json.loads(raw_answer());value['obligations'][0]['conditions']=['Вызвана другая функция']
    parsed,warnings=inspect_answer(TEXT,json.dumps(value))
    assert len(parsed['obligations'])==2 and any('условие 1' in w for w in warnings)


def test_compound_answer_is_not_split_by_program():
    value=dict(obligations=[dict(statement='Сохранить value и вернуть RESULT_OK',conditions=[],source_fragment='Сохранить value и вернуть RESULT_OK')],specification_gaps=[])
    parsed,warnings=inspect_answer('Сохранить value и вернуть RESULT_OK.',json.dumps(value))
    assert parsed==value and len(parsed['obligations'])==1


def test_schema_rejects_old_contract_but_empty_answer_remains_visible():
    assert inspect_answer(TEXT,'{"elements":[]}')[0] is None
    parsed,warnings=inspect_answer(TEXT,'{"obligations":[],"specification_gaps":[]}')
    assert parsed is not None and warnings


@pytest.mark.parametrize('status',[429,403,404,503])
def test_http_error_is_one_request(status):
    calls=[]
    def handler(request):
        calls.append(request); return httpx.Response(status,text='sensitive server body')
    result=analyze(TEXT,'http://test','test',httpx.MockTransport(handler))
    assert len(calls)==1 and result['status']=='failed'
    assert str(status) in result['warnings'][0]
    assert 'sensitive server body' not in json.dumps(result)


def test_screen_shows_problematic_result_and_exact_raw():
    from PySide6.QtWidgets import QApplication
    from ui import Window
    app=QApplication.instance() or QApplication([])
    window=Window()
    parsed=json.loads(raw_answer())
    data=dict(raw_response=raw_answer(),parsed=parsed,warnings=['Цитата не найдена'],status='review')
    window.show_result(data)
    assert window.table.rowCount()==2
    assert window.raw.toPlainText()==raw_answer()
    assert 'Цитата не найдена' in window.notes.toPlainText()
    assert window.save_button.isEnabled()
    window.close()


def test_window_request_runs_in_background(monkeypatch):
    import time
    import ui
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    def fake_analyze(*args,received=None):
        time.sleep(0.03)
        value=dict(status='review',raw_response=raw_answer(),parsed=json.loads(raw_answer()),warnings=[])
        if received: received(value)
        return value
    monkeypatch.setattr(ui,'analyze',fake_analyze)
    window=ui.Window();window.input.setPlainText(TEXT);window.start()
    assert window.worker is not None and not window.start_button.isEnabled()
    deadline=time.monotonic()+3
    while window.worker is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(0.005)
    assert window.worker is None and window.table.rowCount()==2
    assert window.start_button.isEnabled()
    window.close()


def test_export_contains_original_response(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from ui import Window
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'diagnostics.json'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),'JSON'))
    window=Window()
    data=dict(requirement=TEXT,raw_response=raw_answer(),parsed=json.loads(raw_answer()),warnings=[],status='review')
    window.show_result(data);window.save()
    assert json.loads(path.read_text(encoding='utf-8'))==data
    window.close()
