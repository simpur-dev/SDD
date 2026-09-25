from __future__ import annotations

import os

from .....domain.enums import ArtifactType
from .base import ParsedDocument
from .python_code import PythonCodeParser


class PythonTestParser(PythonCodeParser):
    """Extracts test cases; infers the module under test from naming conventions."""

    artifact_type = ArtifactType.test

    def parse(
        self,
        path: str,
        text: str,
        checksum: str | None,
        declared_type: ArtifactType,
    ) -> ParsedDocument:
        doc = super().parse(path, text, checksum, declared_type)

        cases = [
            symbol
            for symbol in doc.symbols
            if symbol.kind in ("function", "method")
            and symbol.name.split(".")[-1].startswith("test_")
        ]
        for symbol in cases:
            symbol.kind = "test_case"

        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.startswith("test_"):
            target = stem[5:]
        elif stem.endswith("_test"):
            target = stem[:-5]
        else:
            target = stem
        front_matter = dict(doc.front_matter)
        front_matter["test_target_module"] = target

        return doc.model_copy(
            update={
                "type": ArtifactType.test,
                "symbols": cases,
                "behavior_points": [s.name.split(".")[-1] for s in cases],
                "front_matter": front_matter,
            }
        )
