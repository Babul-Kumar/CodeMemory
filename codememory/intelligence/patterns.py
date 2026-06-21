"""Design pattern detection from repository graph and symbol data."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from codememory.models import ScanResult

logger = logging.getLogger(__name__)

# Pattern detection heuristics
_PATTERN_CHECKS: list[tuple[str, "callable"]] = []


def _register(name: str):
    """Decorator to register a pattern-detection function."""
    def decorator(fn):
        _PATTERN_CHECKS.append((name, fn))
        return fn
    return decorator


@_register("MVC (Model-View-Controller)")
def _detect_mvc(G: nx.DiGraph, scan_results: list["ScanResult"]) -> bool:
    """Detect MVC pattern by presence of model/view/controller directories."""
    dirs: set[str] = set()
    for result in scan_results:
        parts = [p.lower() for p in Path(result.file_info.path).parts]
        dirs.update(parts)
    has_model = any("model" in d for d in dirs)
    has_view = any("view" in d or "template" in d for d in dirs)
    has_controller = any("controller" in d or "handler" in d or "route" in d for d in dirs)
    return has_model and has_view and has_controller


@_register("Repository Pattern")
def _detect_repository(G: nx.DiGraph, scan_results: list["ScanResult"]) -> bool:
    """Detect Repository pattern by class names or directory names."""
    for result in scan_results:
        # Check directory
        parts = [p.lower() for p in Path(result.file_info.path).parts]
        if any("repositor" in p for p in parts):
            return True
        # Check class names
        for sym in result.symbols:
            if sym.kind == "class" and "repository" in sym.name.lower():
                return True
    return False


@_register("Service Layer")
def _detect_service_layer(G: nx.DiGraph, scan_results: list["ScanResult"]) -> bool:
    """Detect Service Layer by class/directory name patterns."""
    for result in scan_results:
        parts = [p.lower() for p in Path(result.file_info.path).parts]
        if any("service" in p for p in parts):
            return True
        for sym in result.symbols:
            if sym.kind == "class" and sym.name.lower().endswith("service"):
                return True
    return False


@_register("Factory Pattern")
def _detect_factory(G: nx.DiGraph, scan_results: list["ScanResult"]) -> bool:
    """Detect Factory pattern by class/function name patterns."""
    for result in scan_results:
        for sym in result.symbols:
            name_lower = sym.name.lower()
            if "factory" in name_lower or name_lower.startswith("create_"):
                return True
    return False


@_register("Singleton Pattern")
def _detect_singleton(G: nx.DiGraph, scan_results: list["ScanResult"]) -> bool:
    """Detect Singleton pattern by class variable or method names."""
    for result in scan_results:
        for sym in result.symbols:
            if sym.kind == "method" and sym.name.lower() in (
                "get_instance", "instance", "_instance", "singleton"
            ):
                return True
            if sym.kind == "variable" and "_instance" in sym.name.lower():
                return True
    return False


@_register("Event-Driven / Observer")
def _detect_observer(G: nx.DiGraph, scan_results: list["ScanResult"]) -> bool:
    """Detect Observer/event-driven pattern by emit/subscribe/listener names."""
    keywords = {"emit", "subscribe", "unsubscribe", "listener", "event_handler", "on_event", "dispatch"}
    for result in scan_results:
        for sym in result.symbols:
            if sym.name.lower() in keywords or any(kw in sym.name.lower() for kw in keywords):
                return True
    return False


@_register("Middleware Stack")
def _detect_middleware(G: nx.DiGraph, scan_results: list["ScanResult"]) -> bool:
    """Detect middleware pattern by directory or class/function names."""
    for result in scan_results:
        parts = [p.lower() for p in Path(result.file_info.path).parts]
        if any("middleware" in p for p in parts):
            return True
        for sym in result.symbols:
            if "middleware" in sym.name.lower():
                return True
    return False


class PatternDetector:
    """Detects common software design patterns in a repository.

    Uses structural heuristics on the symbol graph and directory layout —
    no semantic analysis or LLM required.
    """

    def detect(self, G: nx.DiGraph, scan_results: list["ScanResult"]) -> list[str]:
        """Run all registered pattern checks.

        Args:
            G:            The repository knowledge graph.
            scan_results: All file extraction results.

        Returns:
            List of detected pattern names.
        """
        detected: list[str] = []
        for pattern_name, check_fn in _PATTERN_CHECKS:
            try:
                if check_fn(G, scan_results):
                    detected.append(pattern_name)
                    logger.debug("Pattern detected: %s", pattern_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Pattern check '%s' raised: %s", pattern_name, exc)
        return detected
