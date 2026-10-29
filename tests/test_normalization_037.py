"""Проверки смысловых рисков из реальных ответов без облачных запросов."""
from reqtest.models.domain import Requirement, ElementType
from reqtest.services.extraction import ExtractionResponse, _resolve
from reqtest.services.source_catalog import build_source_catalog
from reqtest.services.source_normalization import definition_sources
from reqtest.services.branch_context import build_context_catalog


def resolve(text, items):
    return _resolve(Requirement(id='R',text=text),ExtractionResponse.model_validate({'elements':items}))


def test_paraphrased_condition_has_one_literal_node():
    elements,errors,_=resolve('При вызове Run компонент должен вернуть RESULT_OK.',[
        dict(type='условие',description='Компонент вызвал метод Run',source_ids=['F001'],context_ids=['C001']),
        dict(type='действие',description='Вернуть RESULT_OK',source_ids=['F001'],context_ids=['C001'])])
    assert not errors
    conditions=[e for e in elements if e.type==ElementType.CONDITION]
    assert len(conditions)==1 and conditions[0].description=='При вызове Run'
    assert next(e for e in elements if e.type==ElementType.ACTION).condition_ids==[conditions[0].id]


def test_formula_definition_added_with_visible_note():
    text='При вызове Merge компонент должен вычислить output_bits по формуле old_bits | mask_bits. Биты вне маски сохраняют old_bits.'
    elements,errors,notes=resolve(text,[dict(type='ограничение',description='Биты output_bits вне маски сохраняют old_bits',source_ids=['F002'],context_ids=['C001'])])
    assert not errors and not elements[0].analysis_blocked
    assert {'F001','F002'} <= {r.source_id for r in elements[0].source_refs}
    assert any('определение' in n for n in notes)


def test_unrelated_name_or_number_is_not_recovered():
    sources=build_source_catalog('Выдать SECRET_FLAG. Вернуть RESULT_OK. Значение 17.')
    assert not definition_sources('Вернуть SECRET_FLAG 17',[sources[1]],sources)


def test_negated_invocation_is_blocked():
    text='При вызове Tick, если elapsed_ms больше 9, компонент должен вызвать Poll(). Если elapsed_ms меньше 10, не вызывать Poll().'
    contexts=build_context_catalog(Requirement(id='R',text=text))
    compound=next(r for r in contexts if 'При вызове' in r.text and 'если' in r.text)
    small=next(r for r in contexts if r.text.startswith('Если'))
    elements,errors,_=resolve(text,[dict(type='ограничение',description='Не вызывать Poll()',source_ids=['F002'],context_ids=[small.source_id],negated_context_ids=[compound.source_id])])
    assert not errors and elements[0].analysis_blocked


def test_expected_result_is_not_canonicalized_as_precondition():
    elements,_,_=resolve('При вызове Run компонент должен вернуть RESULT_OK.',[
        dict(type='условие',description='Компонент возвращает RESULT_OK',source_ids=['F001'],context_ids=['C001'])])
    assert elements[0].analysis_blocked
    assert elements[0].description=='Компонент возвращает RESULT_OK'


def test_unspecified_behavior_stays_only_in_notes():
    elements,errors,notes=resolve('Поведение в режиме RUN не определено.',[
        dict(type='условие',description='Режим RUN',source_ids=['F001'])])
    assert not elements and not errors and notes
