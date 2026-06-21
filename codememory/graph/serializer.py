"""Serialization and deserialization of NetworkX graphs to/from JSON."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

logger = logging.getLogger(__name__)


class GraphSerializer:
    """Persists and restores :class:`networkx.DiGraph` objects as JSON files.

    The ``node_link`` format from :mod:`networkx.readwrite.json_graph` is used,
    which is stable and human-readable.
    """

    @staticmethod
    def save(G: nx.DiGraph, path: Path) -> None:
        """Serialize a graph to a JSON file.

        Args:
            G:    The :class:`~networkx.DiGraph` to save.
            path: Destination file path (created/overwritten).
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json_graph.node_link_data(G)
            with path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            logger.debug("Graph saved to %s (%d nodes, %d edges)", path, G.number_of_nodes(), G.number_of_edges())
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to save graph to %s: %s", path, exc)
            raise

    @staticmethod
    def load(path: Path) -> nx.DiGraph:
        """Deserialize a graph from a JSON file.

        Args:
            path: Path to the saved JSON graph file.

        Returns:
            A reconstructed :class:`~networkx.DiGraph`.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"Graph file not found: {path}")
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            G = json_graph.node_link_graph(data, directed=True)
            logger.debug("Graph loaded from %s (%d nodes, %d edges)", path, G.number_of_nodes(), G.number_of_edges())
            return G
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load graph from %s: %s", path, exc)
            raise

    @staticmethod
    def get_subgraph(G: nx.DiGraph, node: str, depth: int = 2) -> nx.DiGraph:
        """Extract the ego-network (neighborhood) of *node* up to *depth* hops.

        Args:
            G:     The full :class:`~networkx.DiGraph`.
            node:  Node ID to center the subgraph on.
            depth: Number of hops to include.

        Returns:
            A subgraph view (not a copy) of *G*.
        """
        if node not in G:
            logger.warning("Node '%s' not found in graph; returning empty graph.", node)
            return nx.DiGraph()

        # Use ego_graph which works on both directed and undirected
        sub = nx.ego_graph(G, node, radius=depth, undirected=True)
        return sub
