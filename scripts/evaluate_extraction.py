"""Повторяемый прогон корпуса: реальные модели или явно обозначенная подмена.

Эталонные элементы в запросы настоящей модели не передаются. JSON предназначен
для ручного сопоставления; количество успешно разобранных ответов не равно качеству.
"""
import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reqtest.llm.client import LLMClient, LLMError
from reqtest.models.domain import Project, Requirement, LLMSettings
from reqtest.services.extraction import extract_project


class ReferenceFixture:
    """Подмена для проверки протокола и файлов; не измеряет качество LLM."""
    def __init__(self, cases):
        self.cases = {case['id']: case for case in cases}

    def complete(self, messages, schema):
        payload = json.loads(messages[1]['content'])
        if schema['title'] == 'ExtractionResponse':
            return json.dumps({'elements': self.cases[payload['id']]['elements']})
        return json.dumps(dict(coverage_complete=True, findings=[], source_assessments=[
            dict(source_id=source['id'], role='normative', rationale='Эталонная подмена', element_ids=[
                e['id'] for e in payload['elements'] if source['id'] in [r['source_id'] for r in e['source_refs']]])
            for source in payload['sources']]))


def main() -> int:
    """Сохранить тексты, эталоны, предложения и замечания для ручной экспертизы."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path(__file__).resolve().parents[1] / 'examples/validation_corpus.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider', choices=['ollama', 'openai'], default='ollama')
    parser.add_argument('--base-url', default='http://localhost:11434')
    parser.add_argument('--model', default='')
    parser.add_argument('--fixture', action='store_true', help='Подмена модели эталонными ответами; только проверка протокола')
    args = parser.parse_args()
    if not args.fixture and not args.model:
        parser.error('Для реального запуска укажите --model')
    cases = json.loads(args.corpus.read_text(encoding='utf-8'))
    client = ReferenceFixture(cases) if args.fixture else LLMClient(LLMSettings(
        provider=args.provider, base_url=args.base_url, model=args.model,
        api_key=os.environ.get('REQTEST_API_KEY') or None))
    results = []
    for case in cases:
        started = time.monotonic()
        item = {'id': case['id'], 'text': case['text'], 'reference_elements': case['elements']}
        try:
            project = extract_project(Project(name='Корпус', requirements=[Requirement(id=case['id'], text=case['text'])]), client).project
            item.update(operation='completed', actual=project.model_dump(mode='json'))
        except LLMError as error:
            item.update(operation='failed', error=str(error))
        item['seconds'] = round(time.monotonic() - started, 3)
        results.append(item)
    report = dict(mode='reference_fixture' if args.fixture else 'real_model', model=args.model or None,
                  python=platform.python_version(), platform=platform.platform(), cases=results,
                  interpretation='Успешная операция не доказывает правильность. Сверьте предикаты, источники, '
                  'условия, ветви, числа/единицы, пропуски и добавленные факты с эталоном и исходным текстом. '
                  'Эталоны корпуса иллюстративны и не являются полной методикой верификации.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Operations completed: {sum(item["operation"] == "completed" for item in results)}/{len(results)}; mode={report["mode"]}')
    return int(any(item['operation'] == 'failed' for item in results))


if __name__ == '__main__':
    raise SystemExit(main())
