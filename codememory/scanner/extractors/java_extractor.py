"""Java source file extractor using tree-sitter AST traversal."""
from __future__ import annotations

import logging
from pathlib import Path

from codememory.models import FileInfo, ScanResult, SymbolInfo

logger = logging.getLogger(__name__)


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _node_lines(node) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _extract_methods(
    class_body,
    source_bytes: bytes,
    path_str: str,
    parent_class: str,
    symbols: list[SymbolInfo],
) -> None:
    """Extract method declarations from a Java class body."""
    for child in class_body.children:
        if child.type == "method_declaration":
            name_node = child.child_by_field_name("name")
            params_node = child.child_by_field_name("formal_parameters")
            type_node = child.child_by_field_name("type")
            if name_node:
                mname = _node_text(name_node, source_bytes)
                params = _node_text(params_node, source_bytes) if params_node else "()"
                ret_type = _node_text(type_node, source_bytes) + " " if type_node else ""
                start, end = _node_lines(child)
                symbols.append(
                    SymbolInfo(
                        name=mname,
                        kind="method",
                        file_path=path_str,
                        start_line=start,
                        end_line=end,
                        signature=f"{ret_type}{mname}{params}",
                        parent_name=parent_class,
                    )
                )
        elif child.type in ("class_declaration", "interface_declaration"):
            # Inner class
            _extract_class(child, source_bytes, path_str, symbols)


def _extract_class(
    node,
    source_bytes: bytes,
    path_str: str,
    symbols: list[SymbolInfo],
) -> None:
    """Extract a Java class or interface declaration."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        return
    cname = _node_text(name_node, source_bytes)
    start, end = _node_lines(node)
    keyword = "class" if node.type == "class_declaration" else "interface"
    symbols.append(
        SymbolInfo(
            name=cname,
            kind="class",
            file_path=path_str,
            start_line=start,
            end_line=end,
            signature=f"{keyword} {cname}",
        )
    )
    body = node.child_by_field_name("body")
    if body:
        _extract_methods(body, source_bytes, path_str, cname, symbols)


def _walk(
    node,
    source_bytes: bytes,
    path_str: str,
    symbols: list[SymbolInfo],
    imports: list[str],
) -> None:
    """Recursively walk Java compilation unit children."""
    ntype = node.type

    if ntype in ("class_declaration", "interface_declaration"):
        _extract_class(node, source_bytes, path_str, symbols)
        return  # already handled recursion

    elif ntype == "import_declaration":
        # Child: qualified_name
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                mod = _node_text(child, source_bytes)
                imports.append(mod)

    elif ntype == "package_declaration":
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                symbols.append(
                    SymbolInfo(
                        name=_node_text(child, source_bytes),
                        kind="variable",
                        file_path=path_str,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=f"package {_node_text(child, source_bytes)}",
                    )
                )

    for child in node.children:
        _walk(child, source_bytes, path_str, symbols, imports)


def extract(tree, source_bytes: bytes, file_path: Path) -> ScanResult:
    """Extract classes, methods, and imports from a parsed Java source file.

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
        logger.warning("Java extraction failed for %s: %s", file_path, exc)

    file_info = FileInfo(path=path_str, language="java", size_bytes=len(source_bytes))
    return ScanResult(file_info=file_info, symbols=symbols, imports=list(set(imports)))
