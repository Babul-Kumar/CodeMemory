"""Python source file extractor using tree-sitter queries."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from codememory.models import FileInfo, ScanResult, SymbolInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tree-sitter S-expression queries for Python
# ---------------------------------------------------------------------------

_FUNCTION_QUERY = """
(function_definition
  name: (identifier) @func.name
  parameters: (parameters) @func.params
  body: (block
    (expression_statement
      (string) @func.docstring)?) @func.body)
"""

_CLASS_QUERY = """
(class_definition
  name: (identifier) @class.name
  body: (block
    (expression_statement
      (string) @class.docstring)?))
"""

_METHOD_QUERY = """
(class_definition
  name: (identifier) @class.name
  body: (block
    (function_definition
      name: (identifier) @method.name
      parameters: (parameters) @method.params
      body: (block
        (expression_statement
          (string) @method.docstring)?)? )))
"""

_IMPORT_QUERY = """
(import_statement
  name: (dotted_name) @import.name)

(import_from_statement
  module_name: (dotted_name)? @from.module
  name: (dotted_name) @from.name)

(import_from_statement
  module_name: (relative_import
    (dotted_name)? @rel.module)
  name: (dotted_name) @from.name)
"""

_ALL_QUERY = """
(expression_statement
  (assignment
    left: (identifier) @all.name
    (#eq? @all.name "__all__")
    right: (list) @all.value))
"""


def _node_text(node, source_bytes: bytes) -> str:
    """Extract UTF-8 text for a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _node_lines(node) -> tuple[int, int]:
    """Return 1-based (start_line, end_line) for a tree-sitter node."""
    return node.start_point[0] + 1, node.end_point[0] + 1


def _run_query(query: Any, root_node: Any) -> list[tuple[str, Any]]:
    from tree_sitter import QueryCursor
    cursor = QueryCursor(query)
    captures_dict = cursor.captures(root_node)
    captures = []
    for cap_name, nodes in captures_dict.items():
        for n in nodes:
            captures.append((cap_name, n))
    captures.sort(key=lambda x: x[1].start_byte)
    return captures


def extract(tree, source_bytes: bytes, file_path: Path) -> ScanResult:
    """Extract symbols, imports, and exports from a parsed Python file.

    Args:
        tree:         A ``tree_sitter.Tree`` produced by the Python parser.
        source_bytes: Raw file content as bytes.
        file_path:    Absolute path of the source file (used for ``FileInfo``).

    Returns:
        A populated :class:`~codememory.models.ScanResult`.
    """
    path_str = str(file_path)
    symbols: list[SymbolInfo] = []
    imports: list[str] = []
    exports: list[str] = []

    try:
        from tree_sitter import Language
        import tree_sitter_python as tspython

        lang = Language(tspython.language())
        root = tree.root_node

        # ── Classes ──────────────────────────────────────────────────────────
        from tree_sitter import Query
        class_query = Query(lang, _CLASS_QUERY)
        class_captures = _run_query(class_query, root)

        # Build class name -> node mapping
        class_nodes: dict[str, object] = {}
        i = 0
        while i < len(class_captures):
            cap_name, node = class_captures[i]
            if cap_name == "class.name":
                class_name = _node_text(node, source_bytes)
                # Walk up to the class_definition node
                class_def = node.parent
                docstring: str | None = None
                if i + 1 < len(class_captures) and class_captures[i + 1][0] == "class.docstring":
                    docstring_node = class_captures[i + 1][1]
                    raw = _node_text(docstring_node, source_bytes).strip("'\"")
                    docstring = raw.strip()
                    i += 1
                start, end = _node_lines(class_def)
                symbols.append(
                    SymbolInfo(
                        name=class_name,
                        kind="class",
                        file_path=path_str,
                        start_line=start,
                        end_line=end,
                        signature=f"class {class_name}",
                        docstring=docstring,
                    )
                )
                class_nodes[class_name] = class_def
            i += 1

        # ── Top-level functions ───────────────────────────────────────────────
        from tree_sitter import Query
        func_query = Query(lang, _FUNCTION_QUERY)
        func_captures = _run_query(func_query, root)

        seen_names: set[str] = set()
        j = 0
        while j < len(func_captures):
            cap_name, node = func_captures[j]
            if cap_name == "func.name":
                func_name = _node_text(node, source_bytes)
                func_def = node.parent  # function_definition node
                # Determine if this function is inside a class
                parent = func_def.parent
                while parent:
                    if parent.type == "class_definition":
                        break
                    parent = parent.parent
                is_method = parent is not None and parent.type == "class_definition"

                params_text: str | None = None
                docstring = None
                # Look ahead for params and docstring
                k = j + 1
                while k < len(func_captures) and func_captures[k][0] in (
                    "func.params",
                    "func.docstring",
                    "func.body",
                ):
                    sub_name, sub_node = func_captures[k]
                    if sub_name == "func.params":
                        params_text = _node_text(sub_node, source_bytes)
                    elif sub_name == "func.docstring":
                        docstring = _node_text(sub_node, source_bytes).strip("'\"").strip()
                    k += 1

                start, end = _node_lines(func_def)
                signature = f"def {func_name}{params_text or '()'}"
                uid = f"{func_name}:{start}"
                if uid not in seen_names:
                    seen_names.add(uid)
                    if is_method:
                        # Find parent class name
                        p = func_def.parent
                        while p and p.type != "class_definition":
                            p = p.parent
                        parent_class = None
                        if p:
                            for child in p.children:
                                if child.type == "identifier":
                                    parent_class = _node_text(child, source_bytes)
                                    break
                        symbols.append(
                            SymbolInfo(
                                name=func_name,
                                kind="method",
                                file_path=path_str,
                                start_line=start,
                                end_line=end,
                                signature=signature,
                                docstring=docstring,
                                parent_name=parent_class,
                            )
                        )
                    else:
                        symbols.append(
                            SymbolInfo(
                                name=func_name,
                                kind="function",
                                file_path=path_str,
                                start_line=start,
                                end_line=end,
                                signature=signature,
                                docstring=docstring,
                            )
                        )
            j += 1

        # ── Imports ───────────────────────────────────────────────────────────
        from tree_sitter import Query
        import_query = Query(lang, _IMPORT_QUERY)
        import_captures = _run_query(import_query, root)
        seen_imports: set[str] = set()
        for cap_name, node in import_captures:
            text = _node_text(node, source_bytes)
            if text not in seen_imports:
                seen_imports.add(text)
                imports.append(text)
                symbols.append(
                    SymbolInfo(
                        name=text,
                        kind="import",
                        file_path=path_str,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    )
                )

        # ── __all__ exports ───────────────────────────────────────────────────
        try:
            from tree_sitter import Query
            all_query = Query(lang, _ALL_QUERY)
            all_captures = _run_query(all_query, root)
            for cap_name, node in all_captures:
                if cap_name == "all.value":
                    # Extract string elements from the list
                    for child in node.children:
                        if child.type == "string":
                            name = _node_text(child, source_bytes).strip("'\"")
                            if name:
                                exports.append(name)
        except Exception:  # noqa: BLE001
            pass

    except Exception as exc:  # noqa: BLE001
        logger.warning("Python extraction failed for %s: %s", file_path, exc)

    file_info = FileInfo(
        path=path_str,
        language="python",
        size_bytes=len(source_bytes),
    )
    return ScanResult(
        file_info=file_info,
        symbols=symbols,
        imports=imports,
        exports=exports,
    )
