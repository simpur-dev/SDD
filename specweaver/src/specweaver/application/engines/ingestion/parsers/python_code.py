from __future__ import annotations

import ast
import os

from .....domain.enums import ArtifactType
from .base import ParsedDocument, ParsedSymbol
from .markdown import extract_refs


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args_spec = node.args
    params: list[str] = [p.arg for p in args_spec.posonlyargs]
    params.extend(p.arg for p in args_spec.args)
    if args_spec.vararg:
        params.append(f"*{args_spec.vararg.arg}")
    params.extend(p.arg for p in args_spec.kwonlyargs)
    if args_spec.kwarg:
        params.append(f"**{args_spec.kwarg.arg}")
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(params)})"


def _symbol(
    node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str, qualified: str = ""
) -> ParsedSymbol:
    name = f"{qualified}{node.name}" if qualified else node.name
    docstring = ast.get_docstring(node)
    return ParsedSymbol(
        name=name,
        kind=kind,
        line=node.lineno,
        end_line=node.end_lineno,
        signature=_signature(node),
        docstring=docstring,
        refs=extract_refs(docstring or ""),
    )


class PythonCodeParser:
    """Extracts module symbols, imports and explicit references via the ast module."""

    artifact_type = ArtifactType.code

    def parse(
        self,
        path: str,
        text: str,
        checksum: str | None,
        declared_type: ArtifactType,
    ) -> ParsedDocument:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            # A non-parseable file must not abort the whole ingestion; index its
            # raw text (still searchable) without extracting symbols/imports.
            tree = ast.Module(body=[], type_ignores=[])
        symbols: list[ParsedSymbol] = []
        imports: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                symbols.append(
                    ParsedSymbol(
                        name=node.name,
                        kind="class",
                        line=node.lineno,
                        end_line=node.end_lineno,
                        signature=f"class {node.name}",
                        docstring=ast.get_docstring(node),
                        refs=extract_refs(ast.get_docstring(node) or ""),
                    )
                )
                for method in node.body:
                    if isinstance(
                        method, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        symbols.append(
                            _symbol(method, "method", f"{node.name}.")
                        )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(_symbol(node, "function"))
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        title = os.path.splitext(os.path.basename(path))[0]
        return ParsedDocument(
            path=path,
            type=ArtifactType.code,
            title=title,
            summary=(ast.get_docstring(tree) or "")[:400],
            symbols=symbols,
            references=extract_refs(text),
            imports=_dedupe(imports),
            checksum=checksum,
            raw_text=text,
        )
