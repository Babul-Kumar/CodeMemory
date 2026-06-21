"""Rust source file extractor using tree-sitter AST traversal."""
from __future__ import annotations

import logging
from pathlib import Path

from codememory.models import FileInfo, ScanResult, SymbolInfo

logger = logging.getLogger(__name__)


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _node_lines(node) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _walk(
    node,
    source_bytes: bytes,
    path_str: str,
    symbols: list[SymbolInfo],
    imports: list[str],
    impl_type: str | None = None,
) -> None:
    """Recursively walk Rust AST nodes."""
    ntype = node.type

    # ── fn declarations ────────────────────────────────────────────────────
    if ntype == "function_item":
        name_node = node.child_by_field_name("name")
        if name_node:
            fname = _node_text(name_node, source_bytes)
            params_node = node.child_by_field_name("parameters")
            params = _node_text(params_node, source_bytes) if params_node else "()"
            start, end = _node_lines(node)
            kind = "method" if impl_type else "function"
            symbols.append(
                SymbolInfo(
                    name=fname,
                    kind=kind,
                    file_path=path_str,
                    start_line=start,
                    end_line=end,
                    signature=f"fn {fname}{params}",
                    parent_name=impl_type,
                )
            )

    # ── struct / enum / trait definitions ────────────────────────────────
    elif ntype in ("struct_item", "enum_item", "trait_item"):
        name_node = node.child_by_field_name("name")
        if name_node:
            sname = _node_text(name_node, source_bytes)
            start, end = _node_lines(node)
            keyword = {"struct_item": "struct", "enum_item": "enum", "trait_item": "trait"}[ntype]
            symbols.append(
                SymbolInfo(
                    name=sname,
                    kind="class",
                    file_path=path_str,
                    start_line=start,
                    end_line=end,
                    signature=f"{keyword} {sname}",
                )
            )

    # ── impl blocks ───────────────────────────────────────────────────────
    elif ntype == "impl_item":
        type_node = node.child_by_field_name("type")
        current_impl = _node_text(type_node, source_bytes) if type_node else None
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                _walk(child, source_bytes, path_str, symbols, imports, impl_type=current_impl)
        return  # skip generic recurse below

    # ── use declarations (imports) ────────────────────────────────────────
    elif ntype == "use_declaration":
        arg_node = node.child_by_field_name("argument")
        if arg_node:
            imports.append(_node_text(arg_node, source_bytes))

    for child in node.children:
        _walk(child, source_bytes, path_str, symbols, imports, impl_type)


def extract(tree, source_bytes: bytes, file_path: Path) -> ScanResult:
    """Extract symbols and use declarations from a parsed Rust source file.

    Args:
        tree:         Parsed ``tree_sitter.Tree``.
        source_bytes: Raw file bytes.
        file_path:    Absolute path to the source file.

    Returns:
        Populated :class:`~codememory.models.ScanResult`.
    """
    path_str = str(file_path)
    symbols: list[SymbolInfo] = []
    imports: list[str] = []

    try:
        root = tree.root_node
        for child in root.children:
            _walk(child, source_bytes, path_str, symbols, imports)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rust extraction failed for %s: %s", file_path, exc)

    file_info = FileInfo(path=path_str, language="rust", size_bytes=len(source_bytes))
    return ScanResult(file_info=file_info, symbols=symbols, imports=list(set(imports)))
