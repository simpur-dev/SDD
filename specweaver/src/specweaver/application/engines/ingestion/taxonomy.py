from __future__ import annotations

import os

from ....domain.enums import ArtifactType

_CODE_EXTS = frozenset(
    {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".c", ".h",
        ".cpp", ".hpp", ".cc", ".rs", ".rb", ".php", ".cs", ".kt", ".swift",
    }
)
_DOC_EXTS = frozenset({".md", ".markdown", ".rst", ".txt"})

_IGNORE_PARTS = frozenset(
    {
        ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
        ".idea", ".vscode", "dist", "build", ".eggs", ".pytest_cache",
        ".ruff_cache", ".mypy_cache", "htmlcov",
    }
)
_IGNORE_SUFFIX = (".egg-info", ".pyc", ".pyo", ".egg", ".whl")

_TYPE_ALIASES = {
    "requirement": ArtifactType.requirement,
    "requirements": ArtifactType.requirement,
    "spec": ArtifactType.requirement,
    "specification": ArtifactType.requirement,
    "design": ArtifactType.design,
    "adr": ArtifactType.design,
    "architecture": ArtifactType.design,
    "code": ArtifactType.code,
    "source": ArtifactType.code,
    "test": ArtifactType.test,
    "tests": ArtifactType.test,
    "rule": ArtifactType.rule,
    "rules": ArtifactType.rule,
    "constitution": ArtifactType.rule,
    "convention": ArtifactType.rule,
}


def normalize_type(value: object) -> ArtifactType | None:
    """Map a front-matter type value to an ArtifactType."""
    if not isinstance(value, str):
        return None
    return _TYPE_ALIASES.get(value.strip().lower())


def is_ignored(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in _IGNORE_PARTS or part.startswith(".") for part in parts):
        return True
    return normalized.endswith(_IGNORE_SUFFIX)


def classify_by_path(path: str) -> ArtifactType | None:
    """Heuristic classification from path/extension (front-matter wins later)."""
    normalized = path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    parts = normalized.split("/")
    ext = os.path.splitext(name)[1]
    stem = os.path.splitext(name)[0]

    # tests first (test_*.py, *_test, tests/ directory, conftest)
    if (
        "tests" in parts
        or name.startswith("test_")
        or stem.endswith("_test")
        or name == "conftest.py"
    ):
        return ArtifactType.test

    # textual specs / design / rules
    if ext in _DOC_EXTS:
        if any(seg in parts for seg in ("specs", "spec", "requirements")):
            return ArtifactType.requirement
        if "requirement" in name or stem.startswith("spec"):
            return ArtifactType.requirement
        if any(
            seg in parts for seg in ("design", "docs", "adr", "architecture")
        ) or "design" in name or "adr" in stem:
            return ArtifactType.design
        if (
            "constitution" in name
            or "convention" in name
            or "rule" in name
            or "rules" in parts
        ):
            return ArtifactType.rule

    if ext in _CODE_EXTS:
        return ArtifactType.code
    return None
