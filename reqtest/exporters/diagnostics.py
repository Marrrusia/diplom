"""Экспорт диагностики выделения без настроек соединения и ключей."""
import json
import os
import tempfile
from pathlib import Path
from reqtest import __version__
from reqtest.models.domain import Project
from reqtest.services.source_catalog import build_source_catalog
from reqtest.services.branch_context import build_context_catalog


def export_diagnostics(project: Project, path: Path) -> None:
    """Атомарно записать исходники и ответы модели для воспроизводимого разбора."""
    data = dict(version=__version__, requirements=[r.model_dump(mode='json') for r in project.requirements],
                attempts=[a.model_dump(mode='json') for a in project.extraction_log],
                notes=project.analysis_notes,
                elements=[e.model_dump(mode='json') for e in project.elements],
                catalogs={r.id:dict(sources=[s.model_dump(mode='json') for s in build_source_catalog(r.text)],
                                   contexts=[c.model_dump(mode='json') for c in build_context_catalog(r)])
                          for r in project.requirements})
    path=path.resolve()
    descriptor, temporary=tempfile.mkstemp(prefix='.reqtest-diagnostics-',suffix='.json',dir=path.parent)
    os.close(descriptor)
    try:
        Path(temporary).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)
