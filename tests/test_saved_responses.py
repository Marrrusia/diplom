"""Воспроизведение сохранённых ответов, без подмены ответа модели эталоном."""
import json
from pathlib import Path
import pytest
from reqtest.models.domain import Project,Requirement
from reqtest.services.extraction import extract_project
from reqtest.services.coverage import coverage_summary

CASES=json.loads((Path(__file__).parent/'fixtures/saved_extraction_responses.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['label'])
def test_saved_response_returns_reviewable_partial_project(case,tmp_path,monkeypatch):
    monkeypatch.setenv('REQTEST_LOG_DIR',str(tmp_path))
    class Client:
        calls=0
        def complete(self,messages,schema):
            content=case['responses'][min(self.calls,len(case['responses'])-1)]
            self.calls+=1
            return content
    original=Project(name='Replay',requirements=[Requirement.model_validate(case['requirement'])])
    client=Client()
    result=extract_project(original,client).project
    assert not original.elements and result.elements
    assert result.analysis_incomplete==[original.requirements[0].id]
    assert coverage_summary(result)['total']['percent'] is None
    assert all(not any('не определено' in r.text for r in e.source_refs) for e in result.elements)
    assert all(e.source_fragment in original.requirements[0].text for e in result.elements)
    if '175834' in case['label']:
        assert any('ReadSample' in n for n in result.analysis_notes[original.requirements[0].id])
        assert client.calls==3
