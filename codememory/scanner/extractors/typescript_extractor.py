"""TypeScript extractor — extends the JavaScript extractor with TS-specific nodes."""
from __future__ import annotations

import logging
from pathlib import Path

from codememory.models import FileInfo, ScanResult, SymbolInfo
from codememory.scanner.extractors import javascript_extractor

logger = logging.getLogger(__name__)


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _node_lines(node) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _extract_ts_specific(
    root,
    source_bytes: bytes,
    path_str: str,
    symbols: list[SymbolInfo],
) -> None:
    """Walk AST to extract TypeScript-specific constructs.

    Handles:
    - ``interface_declaration``
    - ``type_alias_declaration``
    - ``enum_declaration``

    Args:
        root:         Root AST node.
        source_bytes: Raw file bytes.
        path_str:     String path of the file.
        symbols:      Symbol list to append to.
    """

    def _walk(node) -> None:
        ntype = node.type

        if ntype == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                iname = _node_text(name_node, source_bytes)
                start, end = _node_lines(node)
                symbols.append(
                    SymbolInfo(
                        name=iname,
                        kind="class",  # treated as class-like for storage
                        file_path=path_str,
                        start_line=start,
                        end_line=end,
                        signature=f"interface {iname}",
                    )
                )

        elif ntype == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                tname = _node_text(name_node, source_bytes)
                start, end = _node_lines(node)
                symbols.append(
                    SymbolInfo(
                        name=tname,
                        kind="variable",  # type aliases stored as variables
                        file_path=path_str,
                        start_line=start,
                        end_line=end,
                        signature=f"type {tname}",
                    )
                )

        elif ntype == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                ename = _node_text(name_node, source_bytes)
                start, end = _node_lines(node)
                symbols.append(
                    SymbolInfo(
                        name=ename,
                        kind="class",  # enums stored as class-like
                        file_path=path_str,
                        start_line=start,
                        end_line=end,
                        signature=f"enum {ename}",
                    )
                )

        for child in node.children:
            _walk(child)

    _walk(root)


def extract(tree, source_bytes: bytes, file_path: Path) -> ScanResult:
    """Extract symbols from a TypeScript file.

    Delegates to the JavaScript extractor for shared constructs, then
    additionally extracts TypeScript-specific syntax.

    Args:
        tree:         Parsed ``tree_sitter.Tree``.
        source_bytes: Raw file bytes.
        file_path:    Absolute path to the source file.

    Returns:
        Populated :class:`~codememory.models.ScanResult`.
    """
    # Start with the JavaScript extractor result
    result = javascript_extractor.extract(tree, source_bytes, file_path)
    # Override language
    result.file_info.language = "typescript"

    path_str = str(file_path)
    ts_symbols: list[SymbolInfo] = []
    try:
        root = tree.root_node
        _extract_ts_specific(root, source_bytes, path_str, ts_symbols)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TypeScript extra extraction failed for %s: %s", file_path, exc)

    result.symbols.extend(ts_symbols)
    return result
