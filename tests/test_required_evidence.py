"""Доказательства обязательны в схеме и при разборе; пустой список допустим."""
import pytest
from pydantic import ValidationError
from reqtest.services.coverage import SemanticDecision

FIELDS=['precondition_evidence','step_evidence','result_evidence']


def test_evidence_arrays_required_in_schema():
    schema=SemanticDecision.model_json_schema()
    assert set(FIELDS)<=set(schema['required'])
    assert all('default' not in schema['properties'][field] for field in FIELDS)


@pytest.mark.parametrize('field',FIELDS)
def test_missing_evidence_is_not_silently_defaulted(field):
    value=dict(status='покрыт',rationale='Проверено',confidence=1,**{key:[] for key in FIELDS})
    value.pop(field)
    with pytest.raises(ValidationError) as error:SemanticDecision.model_validate(value)
    assert any(item['loc']==(field,) and item['type']=='missing' for item in error.value.errors())


def test_explicit_empty_evidence_is_valid_structure():
    value=dict(status='требует проверки',rationale='Нет доказательства',confidence=0,**{field:[] for field in FIELDS})
    answer=SemanticDecision.model_validate(value)
    assert answer.result_evidence==[]
