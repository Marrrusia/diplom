"""Обработка ограничений сервера без настоящих запросов и ожидания."""
import json
import httpx
import pytest
from reqtest.llm.client import LLMClient,LLMError
from reqtest.models.domain import LLMSettings


def test_retry_after_then_success(monkeypatch):
    sleeps=[]; calls=[]; statuses=[]
    monkeypatch.setattr('reqtest.llm.client.time.sleep',sleeps.append)
    def handler(request):
        calls.append(request)
        if len(calls)==1: return httpx.Response(429,headers={'retry-after':'1.2'})
        return httpx.Response(200,json={'message':{'content':'{}'}})
    client=LLMClient(LLMSettings(model='test'),httpx.MockTransport(handler),status=statuses.append)
    assert client.complete([],{})=='{}'
    assert len(calls)==2 and sum(sleeps)>=1.2 and statuses


def test_groq_message_delay():
    response=httpx.Response(429,json={'error':{'message':'Rate limit. Please try again in 9.9s.'}})
    assert LLMClient.rate_limit_delay(response,3)==9.9


def test_cancel_during_wait(monkeypatch):
    state={'cancel':False}
    monkeypatch.setattr('reqtest.llm.client.time.sleep',lambda seconds:state.update(cancel=True))
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(429,headers={'retry-after':'10'})
    client=LLMClient(LLMSettings(model='test'),httpx.MockTransport(handler),cancelled=lambda:state['cancel'])
    with pytest.raises(LLMError,match='отменена'): client.complete([],{})
    assert len(calls)==1


def test_long_or_persistent_limit_is_bounded(monkeypatch):
    monkeypatch.setattr('reqtest.llm.client.time.sleep',lambda seconds:None)
    for delay,expected in [('120',1),('0',3)]:
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(429,headers={'retry-after':delay},text='secret body')
        client=LLMClient(LLMSettings(model='test'),httpx.MockTransport(handler))
        with pytest.raises(LLMError,match='429') as error: client.complete([],{})
        assert len(calls)==expected and 'secret body' not in str(error.value)
