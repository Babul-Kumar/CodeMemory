"""Tests for the Rust, Go, JavaScript, TypeScript, and Java AST extractors."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codememory.models import ScanResult


# ---------------------------------------------------------------------------
# Helper: build a minimal fake tree-sitter tree from source text using the
# generic extractor path (no real tree-sitter grammar installed).
# Each extractor gracefully falls back on exception, so we test the
# happy-path by creating MagicMock trees that mimic tree-sitter nodes.
# ---------------------------------------------------------------------------


def _mock_node(ntype: str, text: bytes = b"", children: list | None = None,
               fields: dict | None = None, start: tuple = (0, 0), end: tuple = (1, 0)):
    """Build a recursive MagicMock that behaves like a tree-sitter node."""
    node = MagicMock()
    node.type = ntype
    node.start_byte = 0
    node.end_byte = len(text)
    node.start_point = start
    node.end_point = end
    node.children = children or []

    def _child_by_field_name(name):
        return (fields or {}).get(name)

    node.child_by_field_name.side_effect = _child_by_field_name
    return node


def _leaf(ntype: str, src: bytes, start_byte: int, end_byte: int,
          row: int = 0) -> MagicMock:
    n = MagicMock()
    n.type = ntype
    n.start_byte = start_byte
    n.end_byte = end_byte
    n.start_point = (row, 0)
    n.end_point = (row, end_byte - start_byte)
    n.children = []
    n.child_by_field_name.return_value = None
    return n


# ===========================================================================
# Rust Extractor
# ===========================================================================

class TestRustExtractor:
    """Unit tests for codememory.scanner.extractors.rust_extractor."""

    def _make_fn_node(self, src: bytes, fname: str, start_row: int = 0) -> MagicMock:
        """Create a mock function_item AST node."""
        name_bytes = fname.encode()
        name_node = _leaf("identifier", src, 3, 3 + len(name_bytes), start_row)
        name_node.start_byte = 3
        name_node.end_byte = 3 + len(name_bytes)

        params_node = _leaf("parameters", src, 3 + len(name_bytes),
                            3 + len(name_bytes) + 2, start_row)
        params_node.start_byte = 3 + len(name_bytes)
        params_node.end_byte = params_node.start_byte + 2

        fn_node = MagicMock()
        fn_node.type = "function_item"
        fn_node.start_point = (start_row, 0)
        fn_node.end_point = (start_row + 3, 0)
        fn_node.children = []

        def _fields(name, _name_node=name_node, _params_node=params_node):
            return {"name": _name_node, "parameters": _params_node}.get(name)

        fn_node.child_by_field_name.side_effect = _fields
        return fn_node

    def test_extract_returns_scan_result(self) -> None:
        """extract() should always return a ScanResult."""
        from codememory.scanner.extractors import rust_extractor

        src = b"fn hello() {}"
        tree = MagicMock()
        tree.root_node.children = []
        result = rust_extractor.extract(tree, src, Path("lib.rs"))
        assert isinstance(result, ScanResult)
        assert result.file_info.language == "rust"

    def test_extract_finds_function(self) -> None:
        """_walk() should detect function_item nodes and create function symbols."""
        from codememory.scanner.extractors import rust_extractor

        src = b"fn hello() {}"
        fn_node = self._make_fn_node(src, "hello")

        tree = MagicMock()
        tree.root_node.children = [fn_node]
        result = rust_extractor.extract(tree, src, Path("lib.rs"))

        names = [s.name for s in result.symbols]
        assert "hello" in names

    def test_extract_struct(self) -> None:
        """_walk() should detect struct_item and produce a class-kind symbol."""
        from codememory.scanner.extractors import rust_extractor

        src = b"struct MyStruct { x: i32 }"
        name_node = _leaf("identifier", src, 7, 15)

        struct_node = MagicMock()
        struct_node.type = "struct_item"
        struct_node.start_point = (0, 0)
        struct_node.end_point = (0, 25)
        struct_node.children = []
        struct_node.child_by_field_name.side_effect = lambda n: name_node if n == "name" else None

        tree = MagicMock()
        tree.root_node.children = [struct_node]
        result = rust_extractor.extract(tree, src, Path("lib.rs"))

        kinds = {s.kind for s in result.symbols}
        assert "class" in kinds

    def test_extract_use_declaration(self) -> None:
        """_walk() should collect use declarations as imports."""
        from codememory.scanner.extractors import rust_extractor

        src = b"use std::collections::HashMap;"
        arg_node = _leaf("scoped_identifier", src, 4, 29)

        use_node = MagicMock()
        use_node.type = "use_declaration"
        use_node.start_point = (0, 0)
        use_node.end_point = (0, 29)
        use_node.children = []
        use_node.child_by_field_name.side_effect = lambda n: arg_node if n == "argument" else None

        tree = MagicMock()
        tree.root_node.children = [use_node]
        result = rust_extractor.extract(tree, src, Path("main.rs"))

        assert len(result.imports) > 0

    def test_extract_graceful_failure(self) -> None:
        """extract() should return an empty ScanResult on tree-sitter failure."""
        from codememory.scanner.extractors import rust_extractor

        tree = MagicMock()
        tree.root_node.children = None  # will raise TypeError

        result = rust_extractor.extract(tree, b"", Path("bad.rs"))
        assert isinstance(result, ScanResult)
        assert result.symbols == []


# ===========================================================================
# Go Extractor
# ===========================================================================

class TestGoExtractor:
    """Unit tests for codememory.scanner.extractors.go_extractor."""

    def test_extract_returns_scan_result(self) -> None:
        from codememory.scanner.extractors import go_extractor

        tree = MagicMock()
        tree.root_node.children = []
        result = go_extractor.extract(tree, b"", Path("main.go"))
        assert isinstance(result, ScanResult)
        assert result.file_info.language == "go"

    def test_extract_function_declaration(self) -> None:
        """function_declaration nodes should produce function symbols."""
        from codememory.scanner.extractors import go_extractor

        src = b"func MyFunc() {}"
        name_node = _leaf("identifier", src, 5, 11)
        params_node = _leaf("parameter_list", src, 11, 13)

        fn_node = MagicMock()
        fn_node.type = "function_declaration"
        fn_node.start_point = (0, 0)
        fn_node.end_point = (0, 15)
        fn_node.children = []
        fn_node.child_by_field_name.side_effect = lambda n: (
            name_node if n == "name" else params_node if n == "parameters" else None
        )

        tree = MagicMock()
        tree.root_node.children = [fn_node]
        result = go_extractor.extract(tree, src, Path("main.go"))

        func_syms = [s for s in result.symbols if s.kind == "function"]
        assert len(func_syms) >= 1

    def test_extract_struct_type(self) -> None:
        """type_declaration with struct_type child should produce a class symbol."""
        from codememory.scanner.extractors import go_extractor

        src = b"type MyStruct struct{}"
        name_node = _leaf("type_identifier", src, 5, 13)
        type_node = _leaf("struct_type", src, 14, 20)

        type_spec = MagicMock()
        type_spec.type = "type_spec"
        type_spec.start_point = (0, 0)
        type_spec.end_point = (0, 20)
        type_spec.children = []
        type_spec.child_by_field_name.side_effect = lambda n: (
            name_node if n == "name" else type_node if n == "type" else None
        )

        decl_node = MagicMock()
        decl_node.type = "type_declaration"
        decl_node.start_point = (0, 0)
        decl_node.end_point = (0, 20)
        decl_node.children = [type_spec]
        decl_node.child_by_field_name.return_value = None

        tree = MagicMock()
        tree.root_node.children = [decl_node]
        result = go_extractor.extract(tree, src, Path("types.go"))

        class_syms = [s for s in result.symbols if s.kind == "class"]
        assert len(class_syms) >= 1

    def test_extract_import_declaration(self) -> None:
        """import_declaration nodes should populate imports list."""
        from codememory.scanner.extractors import go_extractor

        src = b'import "fmt"'
        path_node = _leaf("interpreted_string_literal", src, 7, 12)

        spec_node = MagicMock()
        spec_node.type = "import_spec"
        spec_node.children = []
        spec_node.child_by_field_name.side_effect = lambda n: path_node if n == "path" else None

        import_node = MagicMock()
        import_node.type = "import_declaration"
        import_node.start_point = (0, 0)
        import_node.end_point = (0, 12)
        import_node.children = [spec_node]
        import_node.child_by_field_name.return_value = None

        tree = MagicMock()
        tree.root_node.children = [import_node]
        result = go_extractor.extract(tree, src, Path("main.go"))

        assert len(result.imports) >= 1

    def test_extract_graceful_failure(self) -> None:
        from codememory.scanner.extractors import go_extractor

        tree = MagicMock()
        tree.root_node.children = None

        result = go_extractor.extract(tree, b"", Path("bad.go"))
        assert isinstance(result, ScanResult)
        assert result.symbols == []


# ===========================================================================
# JavaScript Extractor
# ===========================================================================

class TestJavaScriptExtractor:
    """Unit tests for codememory.scanner.extractors.javascript_extractor."""

    def test_extract_returns_scan_result(self) -> None:
        from codememory.scanner.extractors import javascript_extractor

        tree = MagicMock()
        tree.root_node.children = []
        result = javascript_extractor.extract(tree, b"", Path("index.js"))
        assert isinstance(result, ScanResult)
        assert result.file_info.language == "javascript"

    def test_extract_function_declaration(self) -> None:
        """function_declaration should produce function symbols."""
        from codememory.scanner.extractors import javascript_extractor

        src = b"function greet(name) { return name; }"
        name_node = _leaf("identifier", src, 9, 14)
        params_node = _leaf("formal_parameters", src, 14, 20)

        fn_node = MagicMock()
        fn_node.type = "function_declaration"
        fn_node.start_point = (0, 0)
        fn_node.end_point = (0, 36)
        fn_node.children = []
        fn_node.child_by_field_name.side_effect = lambda n: (
            name_node if n == "name" else params_node if n == "parameters" else None
        )

        tree = MagicMock()
        tree.root_node.children = [fn_node]
        result = javascript_extractor.extract(tree, src, Path("app.js"))

        func_syms = [s for s in result.symbols if s.kind == "function"]
        assert len(func_syms) >= 1

    def test_extract_class_declaration(self) -> None:
        """class_declaration should produce class symbols."""
        from codememory.scanner.extractors import javascript_extractor

        src = b"class MyClass {}"
        name_node = _leaf("identifier", src, 6, 13)
        body_node = MagicMock()
        body_node.children = []

        cls_node = MagicMock()
        cls_node.type = "class_declaration"
        cls_node.start_point = (0, 0)
        cls_node.end_point = (0, 15)
        cls_node.children = []
        cls_node.child_by_field_name.side_effect = lambda n: (
            name_node if n == "name" else body_node if n == "body" else None
        )

        tree = MagicMock()
        tree.root_node.children = [cls_node]
        result = javascript_extractor.extract(tree, src, Path("app.js"))

        class_syms = [s for s in result.symbols if s.kind == "class"]
        assert len(class_syms) >= 1
        assert class_syms[0].name == "MyClass"

    def test_extract_import_statement(self) -> None:
        """import_statement should add to imports list."""
        from codememory.scanner.extractors import javascript_extractor

        src = b"import React from 'react';"
        source_node = _leaf("string", src, 18, 25)

        import_node = MagicMock()
        import_node.type = "import_statement"
        import_node.start_point = (0, 0)
        import_node.end_point = (0, 25)
        import_node.children = []
        import_node.child_by_field_name.side_effect = lambda n: source_node if n == "source" else None

        tree = MagicMock()
        tree.root_node.children = [import_node]
        result = javascript_extractor.extract(tree, src, Path("app.js"))

        assert len(result.imports) >= 1

    def test_extract_graceful_failure(self) -> None:
        from codememory.scanner.extractors import javascript_extractor

        tree = MagicMock()
        tree.root_node.children = None

        result = javascript_extractor.extract(tree, b"", Path("bad.js"))
        assert isinstance(result, ScanResult)
        assert result.symbols == []


# ===========================================================================
# TypeScript Extractor
# ===========================================================================

class TestTypeScriptExtractor:
    """Unit tests for codememory.scanner.extractors.typescript_extractor."""

    def test_extract_returns_scan_result(self) -> None:
        from codememory.scanner.extractors import typescript_extractor

        tree = MagicMock()
        tree.root_node.children = []
        result = typescript_extractor.extract(tree, b"", Path("index.ts"))
        assert isinstance(result, ScanResult)
        assert result.file_info.language == "typescript"

    def test_extract_ts_interface(self) -> None:
        """interface_declaration should produce a class-kind symbol."""
        from codememory.scanner.extractors import typescript_extractor

        src = b"interface IUser { name: string; }"
        name_node = _leaf("type_identifier", src, 10, 15)

        iface_node = MagicMock()
        iface_node.type = "interface_declaration"
        iface_node.start_point = (0, 0)
        iface_node.end_point = (0, 32)
        iface_node.children = []
        iface_node.child_by_field_name.side_effect = lambda n: name_node if n == "name" else None

        tree = MagicMock()
        # Root children empty for JS part; set root for TS-specific walk
        tree.root_node.children = [iface_node]
        result = typescript_extractor.extract(tree, src, Path("user.ts"))

        class_syms = [s for s in result.symbols if s.kind == "class"]
        assert len(class_syms) >= 1
        assert "IUser" in [s.name for s in class_syms]

    def test_extract_ts_enum(self) -> None:
        """enum_declaration should produce a class-kind symbol."""
        from codememory.scanner.extractors import typescript_extractor

        src = b"enum Direction { Up, Down }"
        name_node = _leaf("identifier", src, 5, 14)

        enum_node = MagicMock()
        enum_node.type = "enum_declaration"
        enum_node.start_point = (0, 0)
        enum_node.end_point = (0, 26)
        enum_node.children = []
        enum_node.child_by_field_name.side_effect = lambda n: name_node if n == "name" else None

        tree = MagicMock()
        tree.root_node.children = [enum_node]
        result = typescript_extractor.extract(tree, src, Path("enums.ts"))

        syms = {s.name for s in result.symbols}
        assert "Direction" in syms

    def test_extract_ts_type_alias(self) -> None:
        """type_alias_declaration should produce a variable-kind symbol."""
        from codememory.scanner.extractors import typescript_extractor

        src = b"type ID = string;"
        name_node = _leaf("type_identifier", src, 5, 7)

        alias_node = MagicMock()
        alias_node.type = "type_alias_declaration"
        alias_node.start_point = (0, 0)
        alias_node.end_point = (0, 16)
        alias_node.children = []
        alias_node.child_by_field_name.side_effect = lambda n: name_node if n == "name" else None

        tree = MagicMock()
        tree.root_node.children = [alias_node]
        result = typescript_extractor.extract(tree, src, Path("types.ts"))

        var_syms = [s for s in result.symbols if s.kind == "variable"]
        assert len(var_syms) >= 1

    def test_extract_graceful_failure(self) -> None:
        from codememory.scanner.extractors import typescript_extractor

        tree = MagicMock()
        tree.root_node.children = None

        result = typescript_extractor.extract(tree, b"", Path("bad.ts"))
        assert isinstance(result, ScanResult)


# ===========================================================================
# Java Extractor
# ===========================================================================

class TestJavaExtractor:
    """Unit tests for codememory.scanner.extractors.java_extractor."""

    def test_extract_returns_scan_result(self) -> None:
        from codememory.scanner.extractors import java_extractor

        tree = MagicMock()
        tree.root_node.children = []
        result = java_extractor.extract(tree, b"", Path("Main.java"))
        assert isinstance(result, ScanResult)
        assert result.file_info.language == "java"

    def test_extract_class_declaration(self) -> None:
        """class_declaration should produce a class symbol."""
        from codememory.scanner.extractors import java_extractor

        src = b"public class HelloWorld {}"
        name_node = _leaf("identifier", src, 13, 23)
        body_node = MagicMock()
        body_node.children = []

        cls_node = MagicMock()
        cls_node.type = "class_declaration"
        cls_node.start_point = (0, 0)
        cls_node.end_point = (0, 25)
        cls_node.children = []
        cls_node.child_by_field_name.side_effect = lambda n: (
            name_node if n == "name" else body_node if n == "body" else None
        )

        tree = MagicMock()
        tree.root_node.children = [cls_node]
        result = java_extractor.extract(tree, src, Path("HelloWorld.java"))

        class_syms = [s for s in result.symbols if s.kind == "class"]
        assert len(class_syms) >= 1
        assert "HelloWorld" in [s.name for s in class_syms]

    def test_extract_interface_declaration(self) -> None:
        """interface_declaration should produce a class-kind symbol."""
        from codememory.scanner.extractors import java_extractor

        src = b"interface Runnable {}"
        name_node = _leaf("identifier", src, 10, 18)
        body_node = MagicMock()
        body_node.children = []

        iface_node = MagicMock()
        iface_node.type = "interface_declaration"
        iface_node.start_point = (0, 0)
        iface_node.end_point = (0, 20)
        iface_node.children = []
        iface_node.child_by_field_name.side_effect = lambda n: (
            name_node if n == "name" else body_node if n == "body" else None
        )

        tree = MagicMock()
        tree.root_node.children = [iface_node]
        result = java_extractor.extract(tree, src, Path("Runnable.java"))

        class_syms = [s for s in result.symbols if s.kind == "class"]
        assert len(class_syms) >= 1

    def test_extract_import_declaration(self) -> None:
        """import_declaration should populate the imports list."""
        from codememory.scanner.extractors import java_extractor

        src = b"import java.util.List;"
        name_node = _leaf("scoped_identifier", src, 7, 21)

        import_node = MagicMock()
        import_node.type = "import_declaration"
        import_node.start_point = (0, 0)
        import_node.end_point = (0, 21)
        import_node.children = [name_node]
        import_node.child_by_field_name.return_value = None

        tree = MagicMock()
        tree.root_node.children = [import_node]
        result = java_extractor.extract(tree, src, Path("Main.java"))

        assert len(result.imports) >= 1

    def test_extract_graceful_failure(self) -> None:
        from codememory.scanner.extractors import java_extractor

        tree = MagicMock()
        tree.root_node.children = None

        result = java_extractor.extract(tree, b"", Path("Bad.java"))
        assert isinstance(result, ScanResult)
        assert result.symbols == []
