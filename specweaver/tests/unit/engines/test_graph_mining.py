from __future__ import annotations

from specweaver.application.engines.ingestion.graph_mining import mine_relations
from specweaver.application.engines.ingestion.normalize import to_artifact
from specweaver.application.engines.ingestion.parsers import (
    MarkdownParser,
    PythonCodeParser,
    PythonTestParser,
)
from specweaver.domain.enums import ArtifactType

REQUIREMENT = "---\nid: REQ-1\n---\n# 按站调整发车时间\n"
SCHEDULE = (
    '"""调度。"""\nfrom occupancy import Occupancy\n\n\n'
    'class Schedule:\n    """@implements REQ-1"""\n    pass\n'
)
OCCUPANCY = '"""占用。"""\n\n\nclass Occupancy:\n    pass\n'
TEST = 'def test_schedule_adjust():\n    """@covers REQ-1"""\n    pass\n'


def _make(path: str, text: str, declared: ArtifactType):
    if path.endswith(".md"):
        parser = MarkdownParser()
    elif declared is ArtifactType.test:
        parser = PythonTestParser()
    else:
        parser = PythonCodeParser()
    doc = parser.parse(path, text, "chk", declared)
    return doc, to_artifact("railway", doc)


def test_multi_evidence_graph_mining() -> None:
    pairs = [
        _make("specs/req.md", REQUIREMENT, ArtifactType.requirement),
        _make("railway/schedule.py", SCHEDULE, ArtifactType.code),
        _make("railway/occupancy.py", OCCUPANCY, ArtifactType.code),
        _make("tests/test_schedule.py", TEST, ArtifactType.test),
    ]
    ids = {artifact.source.uri: artifact.id for _, artifact in pairs}
    sch = ids["railway/schedule.py"]
    occ = ids["railway/occupancy.py"]
    tst = ids["tests/test_schedule.py"]

    relations = mine_relations("railway", pairs)
    edges = {(r.src, r.kind.value, r.dst): r for r in relations}

    assert (sch, "realizes", "REQ-1") in edges
    assert (tst, "covers", "REQ-1") in edges
    assert (tst, "tests", sch) in edges
    assert (sch, "depends_on", occ) in edges

    assert edges[(sch, "realizes", "REQ-1")].confidence == 0.95
    assert edges[(tst, "tests", sch)].confidence == 0.6
    assert edges[(sch, "depends_on", occ)].confidence == 0.85
