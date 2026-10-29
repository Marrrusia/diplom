"""Диагностика покрытия без изменения запроса и решений."""
import json
from reqtest.services.extraction_diagnostics import DiagnosticClient


class CoverageDiagnosticClient(DiagnosticClient):
    """Сохранить ответ до разбора, заполнения значений по умолчанию и проверки цитат."""
    def __init__(self,client,project):
        super().__init__(client,project)
        self.path=self.path.with_name(self.path.name.replace('extraction-diagnostics-','coverage-diagnostics-',1))
        self.data.update(format='coverage-diagnostics-1',
            elements=[e.model_dump(mode='json') for e in project.elements],
            test_cases=[t.model_dump(mode='json') for t in project.test_cases])

    def complete(self,messages,schema):
        """Связать каждую попытку с парой, в том числе при сетевой ошибке."""
        try:
            return super().complete(messages,schema)
        finally:
            entry=self.data['attempts'][-1]
            try:
                payload=json.loads(messages[1]['content'])
                element_id=payload['element']['id'];test_id=payload['test_case']['id']
            except (ValueError,KeyError,TypeError,IndexError):
                element_id=test_id=None
            entry.update(element_id=element_id,test_case_id=test_id,
                attempt=sum(a.get('element_id')==element_id and a.get('test_case_id')==test_id for a in self.data['attempts'][:-1])+1)
            self.save()

    def record_parsed(self,answer):
        """Показать, какие поля реально пришли, а какие заполнены по умолчанию."""
        self.data['attempts'][-1].update(parsed_before_validation=answer.model_dump(mode='json'),
            provided_fields=sorted(answer.model_fields_set))
        self.save()

    def record_quotes(self,answer,invalid):
        """Сохранить результат нормализации цитат без изменения самого решения."""
        self.data['attempts'][-1].update(parsed_after_quote_validation=answer.model_dump(mode='json'),invalid_quotes=invalid)
        self.save()

    def record_decision(self,link,issues):
        """Сохранить итоговый статус и причины его изменения."""
        self.data['attempts'][-1].update(final_decision=link.model_dump(mode='json'),validation_issues=list(issues))
        self.save()
