"""Строгие модели предметной области; ключи API не входят в проект."""
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class StrictModel(BaseModel):
    """Запретить неизвестные поля и проверять присваивания."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class ElementType(str, Enum):
    CONDITION = "условие"
    ACTION = "действие"
    CONSTRAINT = "ограничение"
    RANGE = "диапазон"
    LOOP = "цикл"
    MODE = "режим"


class ReviewStatus(str, Enum):
    PENDING = "ожидает проверки"
    ACCEPTED = "принят"
    REJECTED = "отклонён"


class TestSource(str, Enum):
    EXISTING = "существующий"
    GENERATED = "сгенерированный"


class CoverageStatus(str, Enum):
    COVERED = "покрыт"
    NOT_COVERED = "не покрыт"
    REVIEW = "требует проверки"


class Requirement(StrictModel):
    """Исходное требование с метаданными импорта."""
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    type: str | None = None
    source: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class SourceReference(StrictModel):
    """Источник, созданный приложением; смещения в символах Python, не байтах."""
    source_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)


class Element(StrictModel):
    """Проверяемый аспект, привязанный к цитате требования."""
    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    type: ElementType
    description: str = Field(min_length=1)
    source_fragment: str = Field(min_length=1)
    source_refs: list[SourceReference] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    condition_ids: list[str] = Field(default_factory=list)
    negated_condition_ids: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PENDING
    analysis_blocked: bool = False


class TestCase(StrictModel):
    """Структурированный существующий или предложенный тест."""
    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    preconditions: list[str] = Field(default_factory=list)
    input_data: dict[str, str] = Field(default_factory=dict)
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    source: TestSource = TestSource.EXISTING
    review_status: ReviewStatus = ReviewStatus.PENDING
    element_ids: list[str] = Field(default_factory=list)

    @field_validator("steps", "preconditions")
    @classmethod
    def nonempty_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Пункты не должны быть пустыми")
        return [value.strip() for value in values]


class CoverageLink(StrictModel):
    """Решение модели и независимое решение пользователя."""
    element_id: str = Field(min_length=1)
    test_case_id: str = Field(min_length=1)
    status: CoverageStatus
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    needs_manual_review: bool = True
    review_status: ReviewStatus = ReviewStatus.PENDING

    manual_status: CoverageStatus | None = None
    manual_rationale: str = ""

    @property
    def effective_status(self) -> CoverageStatus:
        """Ручное уточнение не заменяет сохранённое предложение модели."""
        return self.manual_status if self.review_status == ReviewStatus.ACCEPTED and self.manual_status is not None else self.status

    @property
    def confirmed(self) -> bool:
        """Неподтверждённое предложение не увеличивает покрытие."""
        return self.effective_status == CoverageStatus.COVERED and self.review_status == ReviewStatus.ACCEPTED


class GenerationEntry(StrictModel):
    """Журнал генерации без секретов и необработанных запросов."""
    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mode: str
    test_case_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class CoverageCount(StrictModel):
    """Исторические счётчики подтверждённого покрытия."""
    elements: int = Field(ge=0)
    covered: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_counts(self) -> "CoverageCount":
        if self.covered > self.elements:
            raise ValueError("Покрытых элементов больше общего количества")
        return self

    @property
    def percent(self) -> float | None:
        return round(100 * self.covered / self.elements, 2) if self.elements else None


class CoverageBaseline(StrictModel):
    """Снимок перед первой генерацией, без подмены неизвестных значений нулём."""
    captured_at: str
    total: CoverageCount
    requirements: dict[str, CoverageCount] = Field(default_factory=dict)


class Project(StrictModel):
    """Снимок проекта с проверкой уникальности и связей."""
    schema_version: int = 1
    name: str = Field(min_length=1)
    requirements: list[Requirement] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    coverage: list[CoverageLink] = Field(default_factory=list)
    generation_log: list[GenerationEntry] = Field(default_factory=list)
    initial_coverage: CoverageBaseline | None = None
    analysis_notes: dict[str, list[str]] = Field(default_factory=dict)
    analysis_incomplete: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "Project":
        for items in (self.requirements, self.elements, self.test_cases, self.generation_log):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError("Идентификаторы внутри набора должны быть уникальными")
        requirements = {r.id: r for r in self.requirements}
        if any(identifier not in requirements for identifier in self.analysis_incomplete):
            raise ValueError("Неизвестное требование в замечаниях полноты анализа")
        elements = {e.id: e for e in self.elements}
        tests = {t.id: t for t in self.test_cases}
        for item in [*self.elements, *self.test_cases, *self.generation_log]:
            if item.requirement_id not in requirements:
                raise ValueError("Ссылка на неизвестное требование")
        for element in self.elements:
            if element.source_fragment not in requirements[element.requirement_id].text:
                raise ValueError("Цитата отсутствует в исходном требовании")
            if element.source_refs:
                refs = element.source_refs
                if len({ref.source_id for ref in refs}) != len(refs):
                    raise ValueError("Повторная ссылка на источник")
                original = requirements[element.requirement_id].text
                for ref in refs:
                    if ref.end <= ref.start or original[ref.start:ref.end] != ref.text:
                        raise ValueError("Источник или его смещения не соответствуют требованию")
                envelope = original[min(ref.start for ref in refs):max(ref.end for ref in refs)]
                if element.source_fragment != envelope:
                    raise ValueError("Фрагмент не соответствует ссылкам источника")
        for element in self.elements:
            positive, negative = element.condition_ids, element.negated_condition_ids
            if len(set(positive)) != len(positive) or len(set(negative)) != len(negative) or set(positive) & set(negative):
                raise ValueError("Повторные или противоречивые условия применимости")
            for cid in [*positive, *negative]:
                if cid not in elements or elements[cid].type != ElementType.CONDITION or elements[cid].requirement_id != element.requirement_id or cid == element.id:
                    raise ValueError("Некорректная ссылка на условие применимости")
        visited: set[str] = set()
        visiting: set[str] = set()
        def visit(element_id: str) -> None:
            if element_id in visiting:
                raise ValueError("Циклические условия применимости")
            if element_id in visited:
                return
            visiting.add(element_id)
            element = elements[element_id]
            for condition_id in element.condition_ids + element.negated_condition_ids:
                visit(condition_id)
            visiting.remove(element_id)
            visited.add(element_id)
        for element_id in elements:
            visit(element_id)
        for test in self.test_cases:
            for eid in test.element_ids:
                if eid not in elements or elements[eid].requirement_id != test.requirement_id:
                    raise ValueError("Некорректная связь теста с элементом")
        pairs = set()
        for link in self.coverage:
            if link.element_id not in elements or link.test_case_id not in tests:
                raise ValueError("Неизвестный элемент или тест в покрытии")
            if elements[link.element_id].requirement_id != tests[link.test_case_id].requirement_id:
                raise ValueError("Покрытие связывает разные требования")
            pair = (link.element_id, link.test_case_id)
            if pair in pairs:
                raise ValueError("Повторная связь покрытия")
            pairs.add(pair)
        for entry in self.generation_log:
            if any(tid not in tests or tests[tid].requirement_id != entry.requirement_id for tid in entry.test_case_ids):
                raise ValueError("Некорректная ссылка в журнале генерации")
        return self


class LLMSettings(StrictModel):
    """Настройки сеанса; API-ключ исключён из сериализации."""
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = ""
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
