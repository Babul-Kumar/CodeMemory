"""Go source file extractor using tree-sitter AST traversal."""
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
) -> None:
    """Recursively walk Go AST nodes."""
    ntype = node.type

    # ── Function declarations (including methods with receivers) ───────────
    if ntype == "function_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            fname = _node_text(name_node, source_bytes)
            params_node = node.child_by_field_name("parameters")
            params = _node_text(params_node, source_bytes) if params_node else "()"
            start, end = _node_lines(node)
            symbols.append(
                SymbolInfo(
                    name=fname,
                    kind="function",
                    file_path=path_str,
                    start_line=start,
                    end_line=end,
                    signature=f"func {fname}{params}",
                )
            )

    elif ntype == "method_declaration":
        name_node = node.child_by_field_name("name")
        receiver_node = node.child_by_field_name("receiver")
        receiver_text = _node_text(receiver_node, source_bytes) if receiver_node else ""
        if name_node:
            mname = _node_text(name_node, source_bytes)
            params_node = node.child_by_field_name("parameters")
            params = _node_text(params_node, source_bytes) if params_node else "()"
            start, end = _node_lines(node)
            # Extract receiver type
            parent_name: str | None = None
            if receiver_node:
                # Receiver looks like "(r *ReceiverType)"
                for child in receiver_node.children:
                    if child.type == "parameter_declaration":
                        for subchild in child.children:
                            if subchild.type in ("type_identifier", "pointer_type"):
                                parent_name = _node_text(subchild, source_bytes).lstrip("*")
                                break
            symbols.append(
                SymbolInfo(
                    name=mname,
                    kind="method",
                    file_path=path_str,
                    start_line=start,
                    end_line=end,
                    signature=f"func {receiver_text} {mname}{params}",
                    parent_name=parent_name,
                )
            )

    # ── Struct types ───────────────────────────────────────────────────────
    elif ntype == "type_declaration":
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node and type_node:
                    tname = _node_text(name_node, source_bytes)
                    start, end = _node_lines(child)
                    kind = "class" if type_node.type in ("struct_type", "interface_type") else "variable"
                    symbols.append(
                        SymbolInfo(
                            name=tname,
                            kind=kind,
                            file_path=path_str,
                            start_line=start,
                            end_line=end,
                            signature=f"type {tname} {type_node.type}",
                        )
                    )

    # ── Import declarations ────────────────────────────────────────────────
    elif ntype == "import_declaration":
        for child in node.children:
            if child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        path_node = spec.child_by_field_name("path")
                        if path_node:
                            mod = _node_text(path_node, source_bytes).strip('"')
                            imports.append(mod)
            elif child.type == "import_spec":
                path_node = child.child_by_field_name("path")
                if path_node:
                    mod = _node_text(path_node, source_bytes).strip('"')
                    imports.append(mod)

    for child in node.children:
        _walk(child, source_bytes, path_str, symbols, imports)


def extract(tree, source_bytes: bytes, file_path: Path) -> ScanResult:
    """Extract symbols and imports from a parsed Go source file.

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
        logger.warning("Go extraction failed for %s: %s", file_path, exc)

    file_info = FileInfo(path=path_str, language="go", size_bytes=len(source_bytes))
    return ScanResult(file_info=file_info, symbols=symbols, imports=list(set(imports)))
