"""Tests for ArchitectureAnalyzer and PatternDetector."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import networkx as nx
import pytest

from codememory.models import FileInfo, ScanResult, SymbolInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_node(G: nx.DiGraph, path: str) -> str:
    """Add a file node to graph and return its key."""
    G.add_node(path, node_type="file", path=path)
    return path


def _make_scan_result(path: str, symbols: list[SymbolInfo] | None = None) -> ScanResult:
    fi = FileInfo(path=path, language="python", size_bytes=100)
    return ScanResult(file_info=fi, symbols=symbols or [], imports=[], exports=[])


# ===========================================================================
# ArchitectureAnalyzer tests
# ===========================================================================

class TestArchitectureAnalyzer:
    """Unit tests for codememory.intelligence.architecture.ArchitectureAnalyzer."""

    def test_classify_file_returns_layer_for_api(self) -> None:
        from codememory.intelligence.architecture import _classify_file

        layer = _classify_file("myproject/api/auth.py")
        assert layer == "api"

    def test_classify_file_returns_layer_for_tests(self) -> None:
        from codememory.intelligence.architecture import _classify_file

        assert _classify_file("tests/test_auth.py") == "tests"

    def test_classify_file_returns_layer_for_models(self) -> None:
        from codememory.intelligence.architecture import _classify_file

        assert _classify_file("myapp/models/user.py") == "data"

    def test_classify_file_returns_layer_for_utils(self) -> None:
        from codememory.intelligence.architecture import _classify_file

        assert _classify_file("myapp/utils/helpers.py") == "utils"

    def test_classify_file_returns_none_for_unknown(self) -> None:
        from codememory.intelligence.architecture import _classify_file

        result = _classify_file("myapp/foobar/something.py")
        assert result is None

    def test_analyze_layers(self) -> None:
        """analyze() should correctly group files into layers."""
        from codememory.intelligence.architecture import ArchitectureAnalyzer

        G = nx.DiGraph()
        _file_node(G, "app/api/routes.py")
        _file_node(G, "app/models/user.py")
        _file_node(G, "tests/test_user.py")

        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(G, Path("."))

        assert "api" in result["layers"]
        assert "data" in result["layers"]
        assert "tests" in result["layers"]

    def test_analyze_entry_points(self) -> None:
        """Files with no incoming edges should be entry points."""
        from codememory.intelligence.architecture import ArchitectureAnalyzer

        G = nx.DiGraph()
        a = _file_node(G, "main.py")
        b = _file_node(G, "utils.py")
        G.add_edge(a, b)  # main.py imports utils.py

        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(G, Path("."))

        entry_paths = result["entry_points"]
        # main.py has no incoming file edges → is an entry point
        assert "main.py" in entry_paths
        # utils.py has an incoming edge → NOT an entry point
        assert "utils.py" not in entry_paths

    def test_analyze_hub_files(self) -> None:
        """Files with highest combined degree should be listed as hub files."""
        from codememory.intelligence.architecture import ArchitectureAnalyzer

        G = nx.DiGraph()
        hub = _file_node(G, "core.py")
        for i in range(5):
            leaf = _file_node(G, f"module_{i}.py")
            G.add_edge(hub, leaf)
            G.add_edge(leaf, hub)

        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(G, Path("."))

        assert "core.py" in result["hub_files"]

    def test_analyze_empty_graph(self) -> None:
        """analyze() should work on an empty graph without errors."""
        from codememory.intelligence.architecture import ArchitectureAnalyzer

        G = nx.DiGraph()
        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(G, Path("."))

        assert isinstance(result, dict)
        assert "layers" in result
        assert "entry_points" in result
        assert "hub_files" in result

    def test_analyze_layer_sizes_match_layers(self) -> None:
        """layer_sizes should have same keys as layers and matching counts."""
        from codememory.intelligence.architecture import ArchitectureAnalyzer

        G = nx.DiGraph()
        _file_node(G, "app/services/auth.py")
        _file_node(G, "app/services/billing.py")

        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(G, Path("."))

        for layer, files in result["layers"].items():
            assert result["layer_sizes"][layer] == len(files)


# ===========================================================================
# PatternDetector tests
# ===========================================================================

class TestPatternDetector:
    """Unit tests for codememory.intelligence.patterns.PatternDetector."""

    def test_detect_returns_list(self) -> None:
        """detect() should always return a list."""
        from codememory.intelligence.patterns import PatternDetector

        G = nx.DiGraph()
        detector = PatternDetector()
        result = detector.detect(G, [])
        assert isinstance(result, list)

    def test_detect_mvc_pattern(self) -> None:
        """Should detect MVC when model/view/controller directories are present."""
        from codememory.intelligence.patterns import PatternDetector

        results = [
            _make_scan_result("app/models/user.py"),
            _make_scan_result("app/views/user_view.py"),
            _make_scan_result("app/controllers/user_controller.py"),
        ]
        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, results)

        assert "MVC (Model-View-Controller)" in detected

    def test_detect_repository_pattern_by_classname(self) -> None:
        """Should detect Repository pattern when a class is named *Repository."""
        from codememory.intelligence.patterns import PatternDetector

        sym = SymbolInfo(
            name="UserRepository",
            kind="class",
            file_path="app/data/user_repo.py",
            start_line=1,
            end_line=20,
        )
        results = [_make_scan_result("app/data/user_repo.py", symbols=[sym])]
        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, results)

        assert "Repository Pattern" in detected

    def test_detect_service_layer_by_dirname(self) -> None:
        """Should detect Service Layer when a 'services' directory is present."""
        from codememory.intelligence.patterns import PatternDetector

        results = [_make_scan_result("app/services/auth_service.py")]
        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, results)

        assert "Service Layer" in detected

    def test_detect_factory_pattern(self) -> None:
        """Should detect Factory pattern when a function starts with create_."""
        from codememory.intelligence.patterns import PatternDetector

        sym = SymbolInfo(
            name="create_connection",
            kind="function",
            file_path="db/factory.py",
            start_line=1,
            end_line=5,
        )
        results = [_make_scan_result("db/factory.py", symbols=[sym])]
        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, results)

        assert "Factory Pattern" in detected

    def test_detect_singleton_pattern(self) -> None:
        """Should detect Singleton when a method named get_instance is present."""
        from codememory.intelligence.patterns import PatternDetector

        sym = SymbolInfo(
            name="get_instance",
            kind="method",
            file_path="core/db.py",
            start_line=10,
            end_line=15,
        )
        results = [_make_scan_result("core/db.py", symbols=[sym])]
        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, results)

        assert "Singleton Pattern" in detected

    def test_detect_observer_pattern(self) -> None:
        """Should detect Observer/event-driven when emit or subscribe are present."""
        from codememory.intelligence.patterns import PatternDetector

        sym = SymbolInfo(
            name="emit",
            kind="function",
            file_path="events/bus.py",
            start_line=1,
            end_line=5,
        )
        results = [_make_scan_result("events/bus.py", symbols=[sym])]
        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, results)

        assert "Event-Driven / Observer" in detected

    def test_detect_middleware_pattern(self) -> None:
        """Should detect Middleware when a 'middleware' directory is present."""
        from codememory.intelligence.patterns import PatternDetector

        results = [_make_scan_result("app/middleware/auth.py")]
        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, results)

        assert "Middleware Stack" in detected

    def test_detect_no_false_positives_on_empty(self) -> None:
        """Should detect no patterns for an empty repository."""
        from codememory.intelligence.patterns import PatternDetector

        G = nx.DiGraph()
        detector = PatternDetector()
        detected = detector.detect(G, [])

        # No patterns should fire on empty input
        assert detected == []
