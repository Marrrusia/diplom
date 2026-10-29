"""Регрессии полноты и настроек локальной модели."""
import json
import httpx
from reqtest.models.domain import Element, ElementType, LLMSettings
from reqtest.services.extraction_checks import required_aspects, missing_aspects
from reqtest.llm.client import LLMClient


def test_gap_mode_not_required_again():
    text='В режиме RUN компонент должен вернуть READY. Поведение в режиме RUN при FAULT не определено.'
    modes=[a for a in required_aspects(text) if a.type==ElementType.MODE]
    assert len(modes)==1
    element=Element(id='E',requirement_id='R',type=ElementType.MODE,description='В режиме RUN',source_fragment='В режиме RUN компонент должен вернуть READY.')
    assert not missing_aspects(text,[element])


def test_repeated_modes_and_case():
    text='В режиме RUN вернуть FIRST_OK. В режиме RUN вернуть SECOND_OK.'
    modes=[a for a in required_aspects(text) if a.type==ElementType.MODE]
    assert len(modes)==1
    element=Element(id='E',requirement_id='R',type=ElementType.MODE,description='в режиме RUN',source_fragment='в режиме RUN вернуть SECOND_OK.')
    assert not missing_aspects(text,[element])


def test_mixed_gap_does_not_hide_explicit_behavior():
    text='В режиме RUN компонент должен вернуть READY, остальное поведение не определено.'
    assert any(a.type==ElementType.MODE for a in required_aspects(text))


def test_selected_local_model_protocol():
    def handler(request):
        data=json.loads(request.content)
        assert data['model']=='qwen35-9b-q5:latest'
        assert data['think'] is False and 'options' not in data
        assert request.extensions['timeout']['read']==600
        return httpx.Response(200,json={'message':{'content':'{}'}})
    client=LLMClient(LLMSettings(model='qwen35-9b-q5:latest'),httpx.MockTransport(handler))
    assert client.complete([],{})=='{}'
