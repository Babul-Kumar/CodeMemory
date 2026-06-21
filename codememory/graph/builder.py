"""NetworkX knowledge graph builder from scan results."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import networkx as nx

from codememory.models import ScanResult

if TYPE_CHECKING:
    from codememory.storage.repository import CodeRepository

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds and incrementally updates a NetworkX DiGraph from scan results.

    Node types:
      - ``file``    — one node per source file
      - ``class``   — class-level symbol
      - ``function`` — top-level function
      - ``method``  — method inside a class

    Edge types:
      - ``contains`` — file → symbol
      - ``imports``  — file → file (import relationship)
      - ``inherits`` — class → class
      - ``calls``    — function/method → function/method (best-effort)
    """

    @staticmethod
    def _file_node_id(path: str) -> str:
        return f"file:{path}"

    @staticmethod
    def _symbol_node_id(path: str, name: str, kind: str) -> str:
        return f"{kind}:{path}:{name}"

    def add_scan_result(self, G: nx.DiGraph, scan_result: ScanResult) -> None:
        """Merge a single scan result into *G* (incremental update).

        Args:
            G:           The graph to update in place.
            scan_result: Extraction result for one file.
        """
        fi = scan_result.file_info
        file_nid = self._file_node_id(fi.path)

        # File node
        G.add_node(
            file_nid,
            node_type="file",
            path=fi.path,
            language=fi.language,
            size_bytes=fi.size_bytes,
        )

        # Symbol nodes + contains edges
        for sym in scan_result.symbols:
            if sym.kind in ("import",):
                continue  # imports handled as edges below
            sym_nid = self._symbol_node_id(fi.path, sym.name, sym.kind)
            G.add_node(
                sym_nid,
                node_type=sym.kind,
                name=sym.name,
                file=fi.path,
                start_line=sym.start_line,
                end_line=sym.end_line,
                signature=sym.signature,
                docstring=sym.docstring,
            )
            G.add_edge(file_nid, sym_nid, edge_type="contains")

            # Parent → child edge (e.g., class contains method)
            if sym.parent_name:
                parent_nid = self._symbol_node_id(fi.path, sym.parent_name, "class")
                if G.has_node(parent_nid):
                    G.add_edge(parent_nid, sym_nid, edge_type="contains")

        # Import edges — will be resolved to target files by RelationshipDetector
        for imp in scan_result.imports:
            G.graph.setdefault("unresolved_imports", {}).setdefault(fi.path, []).append(imp)

    def build_from_scan_results(self, scan_results: list[ScanResult]) -> nx.DiGraph:
        """Build a fresh DiGraph from a list of scan results.

        Args:
            scan_results: All file extraction results for a repository.

        Returns:
            A populated :class:`networkx.DiGraph`.
        """
        G = nx.DiGraph()
        for result in scan_results:
            self.add_scan_result(G, result)
        return G

    async def build_from_repository(self, repo: "CodeRepository") -> nx.DiGraph:
        """Build a graph by loading all files + symbols from the database.

        Args:
            repo: An open :class:`~codememory.storage.repository.CodeRepository`.

        Returns:
            A populated :class:`networkx.DiGraph`.
        """
        G = nx.DiGraph()
        files = await repo.get_all_files()
        for fi in files:
            file_nid = self._file_node_id(fi.path)
            G.add_node(
                file_nid,
                node_type="file",
                path=fi.path,
                language=fi.language,
                size_bytes=fi.size_bytes,
                summary=fi.summary,
            )

        # Load relationships from DB
        conn = await repo._db.get_connection()
        cursor = await conn.execute(
            """
            SELECT f1.path AS from_path, f2.path AS to_path, r.rel_type,
                   r.from_symbol, r.to_symbol
            FROM relationships r
            JOIN files f1 ON r.from_file_id = f1.id
            JOIN files f2 ON r.to_file_id   = f2.id
            """
        )
        for row in await cursor.fetchall():
            from_nid = self._file_node_id(row["from_path"])
            to_nid = self._file_node_id(row["to_path"])
            if G.has_node(from_nid) and G.has_node(to_nid):
                G.add_edge(
                    from_nid,
                    to_nid,
                    edge_type=row["rel_type"],
                    from_symbol=row["from_symbol"],
                    to_symbol=row["to_symbol"],
                )
        logger.info("Graph built: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
        return G
