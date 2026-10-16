"""Готовые учебные файлы совместимы с настоящими импортёрами и моделями."""
import json
from pathlib import Path
import pytest
from reqtest.importers.files import (read_table, import_requirements_document,
    import_requirements_table, import_tests_table)
from reqtest.models.domain import Project
from reqtest.services.project_import import merge_import
from reqtest.services.generation import _signature

ROOT = Path(__file__).resolve().parents[1] / 'examples' / 'demo_suite'
FIELDS = ['id','requirement_id','title','preconditions','input_data','steps','expected_result']


@pytest.mark.parametrize('format', ['txt','docx','xlsx'])
def test_requirements_formats_agree(format):
    file = ROOT / ('requirements.' + format)
    records = (import_requirements_table(read_table(file), {f:f for f in ['id','text','type','source']}, str(file))
               if format == 'xlsx' else import_requirements_document(file))
    expected = import_requirements_document(ROOT / 'requirements.txt')
    assert [(r.id,r.text) for r in records] == [(r.id,r.text) for r in expected]


@pytest.mark.parametrize('format', ['csv','xlsx'])
def test_demo_test_formats_and_oracle_references(format):
    requirements = import_requirements_document(ROOT / 'requirements.txt')
    tests = import_tests_table(read_table(ROOT / ('test_cases.'+format)), {f:f for f in FIELDS})
    project = Project(name='Demo',requirements=requirements,test_cases=tests)
    oracle = json.loads((ROOT/'expected_results.json').read_text())
    assert len(project.requirements)==6 and len(project.test_cases)==21
    assert {t.id for t in tests} == {e['test_id'] for e in oracle['test_expectations']}
    for item in oracle['test_expectations']:
        reference_ids = {a[0] for a in oracle['reference_elements'][item['requirement_id']]}
        assert set(item['aspects']) <= reference_ids
    by_id = {t.id:t for t in tests}
    assert _signature(by_id['TC_MASK_GOOD']) == _signature(by_id['TC_MASK_DUPLICATE'])
    assert ((0xA5 & ~0x0F) | (0x3C & 0x0F)) == 0xAC


@pytest.mark.parametrize('filename', ['invalid_unknown_requirement.csv','invalid_duplicate_id.csv'])
def test_demo_bad_imports_atomic(filename):
    project = Project(name='Demo',requirements=import_requirements_document(ROOT/'requirements.txt'))
    original = project.model_dump_json()
    records = import_tests_table(read_table(ROOT/filename), {f:f for f in FIELDS}) if 'unknown' in filename else None
    with pytest.raises(ValueError):
        if records is None:
            records = import_tests_table(read_table(ROOT/filename), {f:f for f in FIELDS})
        merge_import(project, records, 'test_cases')
    assert project.model_dump_json() == original


def test_small_sets_exactly_partition_full_suite():
    all_tests = import_tests_table(read_table(ROOT/'test_cases.csv'), {f:f for f in FIELDS})
    collected = []
    for folder in (ROOT/'small_sets').iterdir():
        requirements = import_requirements_document(folder/'requirements.txt')
        tests = import_tests_table(read_table(folder/'test_cases.csv'), {f:f for f in FIELDS})
        Project(name=folder.name,requirements=requirements,test_cases=tests)
        collected.extend(tests)
    assert {t.id for t in collected} == {t.id for t in all_tests}
    assert len(collected) == len(all_tests)
