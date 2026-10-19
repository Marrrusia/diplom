"""Контрактные подмены двух стадий LLM; не оценка качества настоящей модели."""
import json


def clean_review(payload):
    """Явно подтвердить ссылки переданной эталонной фикстуры."""
    return dict(coverage_complete=True, findings=[], source_assessments=[
        dict(source_id=source['id'], role='normative', rationale='Эталонная фикстура',
             element_ids=[e['id'] for e in payload['elements']
                          if source['id'] in [ref['source_id'] for ref in e['source_refs']]])
        for source in payload['sources']])


class AuditedClient:
    """Раздельные программируемые ответы генератора элементов и эксперта."""
    def __init__(self, elements, review=clean_review):
        self.elements = elements
        self.review = review
        self.calls = []

    def complete(self, messages, schema):
        payload = json.loads(messages[1]['content'])
        self.calls.append(schema['title'])
        if schema['title'] == 'ExtractionReview':
            return json.dumps(self.review(payload), ensure_ascii=False)
        elements = self.elements(payload) if callable(self.elements) else self.elements
        return json.dumps(dict(elements=elements), ensure_ascii=False)
