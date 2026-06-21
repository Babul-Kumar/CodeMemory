"""JavaScript source file extractor using tree-sitter queries."""
from __future__ import annotations

import logging
from pathlib import Path

from codememory.models import FileInfo, ScanResult, SymbolInfo

logger = logging.getLogger(__name__)


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _node_lines(node) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _walk(node, source_bytes: bytes, path_str: str,
          symbols: list[SymbolInfo], imports: list[str], exports: list[str],
          parent_class: str | None = None) -> None:
    """Recursively walk the AST to extract JS symbols."""
    ntype = node.type

    # ── Function declarations ──────────────────────────────────────────────
    if ntype == "function_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            fname = _node_text(name_node, source_bytes)
            params_node = node.child_by_field_name("parameters")
            params = _node_text(params_node, source_bytes) if params_node else "()"
            start, end = _node_lines(node)
            kind = "method" if parent_class else "function"
            symbols.append(SymbolInfo(
                name=fname,
                kind=kind,
                file_path=path_str,
                start_line=start,
                end_line=end,
                signature=f"function {fname}{params}",
                parent_name=parent_class,
            ))

    # ── Arrow functions assigned to variables ──────────────────────────────
    elif ntype == "lexical_declaration":
        for decl in node.children:
            if decl.type == "variable_declarator":
                name_node = decl.child_by_field_name("name")
                value_node = decl.child_by_field_name("value")
                if name_node and value_node and value_node.type in (
                    "arrow_function", "function"
                ):
                    fname = _node_text(name_node, source_bytes)
                    params_node = value_node.child_by_field_name("parameters")
                    params = _node_text(params_node, source_bytes) if params_node else "()"
                    start, end = _node_lines(decl)
                    symbols.append(SymbolInfo(
                        name=fname,
                        kind="function",
                        file_path=path_str,
                        start_line=start,
                        end_line=end,
                        signature=f"const {fname} = {value_node.type}{params}",
                    ))

    # ── Class declarations ─────────────────────────────────────────────────
    elif ntype == "class_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            cname = _node_text(name_node, source_bytes)
            start, end = _node_lines(node)
            symbols.append(SymbolInfo(
                name=cname,
                kind="class",
                file_path=path_str,
                start_line=start,
                end_line=end,
                signature=f"class {cname}",
            ))
            # Walk class body for methods
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    _walk(child, source_bytes, path_str, symbols, imports, exports, parent_class=cname)
            return  # already walked body

    # ── Method definitions (inside class) ─────────────────────────────────
    elif ntype == "method_definition":
        name_node = node.child_by_field_name("name")
        if name_node and parent_class:
            mname = _node_text(name_node, source_bytes)
            params_node = node.child_by_field_name("parameters")
            params = _node_text(params_node, source_bytes) if params_node else "()"
            start, end = _node_lines(node)
            symbols.append(SymbolInfo(
                name=mname,
                kind="method",
                file_path=path_str,
                start_line=start,
                end_line=end,
                signature=f"{mname}{params}",
                parent_name=parent_class,
            ))

    # ── ES6 import statements ─────────────────────────────────────────────
    elif ntype == "import_statement":
        source_node = node.child_by_field_name("source")
        if source_node:
            mod = _node_text(source_node, source_bytes).strip("'\"")
            imports.append(mod)
            start, _ = _node_lines(node)
            symbols.append(SymbolInfo(
                name=mod,
                kind="import",
                file_path=path_str,
                start_line=start,
                end_line=start,
            ))

    # ── CommonJS require() ────────────────────────────────────────────────
    elif ntype == "call_expression":
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")
        if (func_node and _node_text(func_node, source_bytes) == "require"
                and args_node):
            for arg in args_node.children:
                if arg.type == "string":
                    mod = _node_text(arg, source_bytes).strip("'\"")
                    imports.append(mod)
                    start, _ = _node_lines(node)
                    symbols.append(SymbolInfo(
                        name=mod,
                        kind="import",
                        file_path=path_str,
                        start_line=start,
                        end_line=start,
                    ))

    # ── Export statements ─────────────────────────────────────────────────
    elif ntype in ("export_statement", "export_default_statement"):
        decl = node.child_by_field_name("declaration")
        if decl:
            name_node = decl.child_by_field_name("name")
            if name_node:
                exports.append(_node_text(name_node, source_bytes))

    # Recurse for non-class nodes
    if ntype != "class_declaration":
        for child in node.children:
            _walk(child, source_bytes, path_str, symbols, imports, exports, parent_class)


def extract(tree, source_bytes: bytes, file_path: Path) -> ScanResult:
    """Extract symbols, imports, and exports from a parsed JavaScript file.

    Args:
        tree:         A ``tree_sitter.Tree`` for the file.
        source_bytes: Raw file bytes.
        file_path:    Absolute path to the source file.

    Returns:
        Populated :class:`~codememory.models.ScanResult`.
    """
    path_str = str(file_path)
    symbols: list[SymbolInfo] = []
    imports: list[str] = []
    exports: list[str] = []

    try:
        root = tree.root_node
        for child in root.children:
            _walk(child, source_bytes, path_str, symbols, imports, exports)
    except Exception as exc:  # noqa: BLE001
        logger.warning("JavaScript extraction failed for %s: %s", file_path, exc)

    file_info = FileInfo(path=path_str, language="javascript", size_bytes=len(source_bytes))
    return ScanResult(file_info=file_info, symbols=symbols, imports=list(set(imports)), exports=exports)
