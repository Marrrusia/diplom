"""Проверки инвариантов моделей первого этапа."""
import pytest
from pydantic import ValidationError
from reqtest.models.demo import demo_project
from reqtest.models.domain import CoverageLink, CoverageStatus, LLMSettings, Project, ReviewStatus, TestCase as Case


def test_demo_round_trip():
    project = demo_project()
    assert Project.model_validate_json(project.model_dump_json()) == project
    assert len(project.elements) == 4
    assert not project.test_cases


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        Project(name="Проект", unexpected=True)


def test_duplicate_ids_rejected():
    data = demo_project().model_dump()
    data["requirements"].append(data["requirements"][0])
    with pytest.raises(ValidationError, match="уникальными"):
        Project.model_validate(data)


def test_invented_fragment_rejected():
    data = demo_project().model_dump()
    data["elements"][0]["source_fragment"] = "Instance не равен CRC"
    with pytest.raises(ValidationError, match="Цитата"):
        Project.model_validate(data)


def test_dangling_requirement_rejected():
    data = demo_project().model_dump()
    data["elements"][0]["requirement_id"] = "missing"
    with pytest.raises(ValidationError, match="неизвестное требование"):
        Project.model_validate(data)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan")])
def test_invalid_confidence(confidence):
    with pytest.raises(ValidationError):
        CoverageLink(element_id="E1", test_case_id="T1", status="покрыт",
                     rationale="Проверка", confidence=confidence)


def test_confirmation_is_explicit():
    link = CoverageLink(element_id="E1", test_case_id="T1", status=CoverageStatus.COVERED,
                        rationale="Действия и результат проверены", confidence=1)
    assert not link.confirmed
    link.review_status = ReviewStatus.ACCEPTED
    assert link.confirmed
    link.review_status = ReviewStatus.REJECTED
    assert not link.confirmed


def test_api_key_not_serialized():
    settings = LLMSettings(api_key="example-test-key")
    assert "api_key" not in settings.model_dump()
    assert "example-test-key" not in repr(settings)
    assert "example-test-key" not in settings.model_dump_json()


def test_blank_steps_rejected():
    with pytest.raises(ValidationError):
        Case(id="T1", requirement_id="R1", title="Тест", steps=[" "], expected_result="Результат")


def test_unknown_coverage_reference_rejected():
    data = demo_project().model_dump()
    data["coverage"] = [dict(element_id="E001", test_case_id="missing", status="покрыт",
                             rationale="Обоснование", confidence=0.8)]
    with pytest.raises(ValidationError, match="Неизвестный"):
        Project.model_validate(data)
