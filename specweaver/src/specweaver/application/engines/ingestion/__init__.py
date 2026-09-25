"""Ingestion engine public API."""
from __future__ import annotations

from .discovery import DiscoveredFile, DiscoveryReport, FileDiscovery
from .embedding import ArtifactEmbedder, searchable_text
from .graph_mining import edge_id, mine_relations
from .normalize import artifact_id, to_artifact
from .parsers import (
    MarkdownParser,
    ParsedDocument,
    ParsedSymbol,
    Parser,
    ParserRegistry,
    PythonCodeParser,
    PythonTestParser,
)
from .pipeline import IngestionEngine, IngestionResult
from .taxonomy import classify_by_path, is_ignored, normalize_type

__all__ = [
    "IngestionEngine",
    "IngestionResult",
    "FileDiscovery",
    "DiscoveredFile",
    "DiscoveryReport",
    "ArtifactEmbedder",
    "searchable_text",
    "mine_relations",
    "edge_id",
    "to_artifact",
    "artifact_id",
    "ParserRegistry",
    "Parser",
    "ParsedDocument",
    "ParsedSymbol",
    "MarkdownParser",
    "PythonCodeParser",
    "PythonTestParser",
    "classify_by_path",
    "is_ignored",
    "normalize_type",
]
