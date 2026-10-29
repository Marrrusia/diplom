"""Настройки новой модели не перекрываются прежними значениями приложения."""
import json
import httpx
import pytest
from reqtest.models.domain import LLMSettings
from reqtest.llm.client import LLMClient


@pytest.mark.parametrize('provider',['ollama','openai'])
@pytest.mark.parametrize('defaults',[False,True])
def test_sampling_defaults_can_be_inherited(provider,defaults):
    captured=[]
    def handler(request):
        captured.append(json.loads(request.content))
        assert request.extensions['timeout']['read'] == 600
        return httpx.Response(200,json={'message':{'content':'{}'}} if provider=='ollama'
            else {'choices':[{'message':{'content':'{}'}}]})
    settings=LLMSettings(provider=provider,model='local',use_model_defaults=defaults,thinking=False,timeout_seconds=600)
    LLMClient(settings,httpx.MockTransport(handler)).complete([],{'type':'object'})
    payload=captured[0]
    if provider=='ollama':
        assert ('options' not in payload) if defaults else payload['options']=={'temperature':0}
        assert payload['think'] is False
    else:
        assert ('temperature' not in payload) if defaults else payload['temperature']==0
        assert 'think' not in payload


def test_thinking_auto_does_not_force_unsupported_parameter():
    captured=[]
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':'{}'}})
    LLMClient(LLMSettings(model='old'),httpx.MockTransport(handler)).complete([],{})
    assert 'think' not in captured[0]
