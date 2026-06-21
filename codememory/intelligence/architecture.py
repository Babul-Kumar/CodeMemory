"""Architecture layer detection from the file graph."""
from __future__ import annotations

import logging
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)

# Layer definitions: layer_name -> list of directory name fragments
_LAYER_PATTERNS: dict[str, list[str]] = {
    "frontend": ["frontend", "ui", "components", "pages", "views", "client", "web", "public"],
    "api": ["api", "routes", "endpoints", "handlers", "controllers", "rest", "graphql"],
    "services": ["services", "service", "domain", "business", "usecases", "use_cases"],
    "data": ["models", "db", "database", "repositories", "repo", "migrations", "entities"],
    "utils": ["utils", "util", "helpers", "helper", "lib", "shared", "common"],
    "tests": ["test", "tests", "spec", "specs", "__tests__", "e2e", "integration"],
    "config": ["config", "configuration", "settings", "env"],
    "scripts": ["scripts", "tools", "bin", "cmd"],
}


def _classify_file(file_path: str) -> str | None:
    """Return the architecture layer for a file path.

    Args:
        file_path: File path string to classify.

    Returns:
        Layer name string or ``None`` if no layer matches.
    """
    parts = Path(file_path).parts
    lower_parts = [p.lower() for p in parts]
    for layer, patterns in _LAYER_PATTERNS.items():
        for part in lower_parts:
            if any(part == pat or part.startswith(pat) for pat in patterns):
                return layer
    return None


class ArchitectureAnalyzer:
    """Analyzes the repository graph to detect architectural layers and patterns.

    Results include:
    - Per-layer file groupings
    - Entry points (files with no incoming import edges)
    - Hub files (highest in-degree + out-degree)
    """

    def analyze(self, G: nx.DiGraph, repo_path: Path) -> dict:
        """Run architecture analysis on a repository graph.

        Args:
            G:         The full :class:`networkx.DiGraph` of the repository.
            repo_path: Absolute path to the repository root.

        Returns:
            Dict with keys:
            - ``layers``: ``{layer_name: [file_path, ...]}``,
            - ``entry_points``: list of file paths with no incoming edges,
            - ``hub_files``: list of most-connected file paths,
            - ``layer_sizes``: ``{layer_name: count}``.
        """
        layers: dict[str, list[str]] = {k: [] for k in _LAYER_PATTERNS}
        unclassified: list[str] = []

        # Classify each file node
        for node, data in G.nodes(data=True):
            if data.get("node_type") != "file":
                continue
            file_path = data.get("path", node)
            layer = _classify_file(file_path)
            if layer:
                layers[layer].append(file_path)
            else:
                unclassified.append(file_path)

        # Entry points: file nodes with in_degree == 0 (no files import them)
        entry_points: list[str] = []
        for node, data in G.nodes(data=True):
            if data.get("node_type") != "file":
                continue
            # Only count file→file import edges
            incoming = [
                u for u, v, d in G.in_edges(node, data=True)
                if G.nodes[u].get("node_type") == "file"
            ]
            if not incoming:
                entry_points.append(data.get("path", node))

        # Hub files: highest combined degree (in + out) among file nodes
        file_degrees: list[tuple[int, str]] = []
        for node, data in G.nodes(data=True):
            if data.get("node_type") != "file":
                continue
            degree = G.in_degree(node) + G.out_degree(node)
            file_degrees.append((degree, data.get("path", node)))

        file_degrees.sort(key=lambda x: x[0], reverse=True)
        hub_files = [fp for _, fp in file_degrees[:10]]

        # Remove empty layers from output
        non_empty_layers = {k: v for k, v in layers.items() if v}

        logger.info(
            "Architecture: %d layers, %d entry points, %d hub files",
            len(non_empty_layers),
            len(entry_points),
            len(hub_files),
        )

        return {
            "layers": non_empty_layers,
            "layer_sizes": {k: len(v) for k, v in non_empty_layers.items()},
            "entry_points": entry_points[:20],
            "hub_files": hub_files,
            "unclassified_count": len(unclassified),
        }
