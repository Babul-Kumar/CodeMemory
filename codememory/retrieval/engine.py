"""Retrieval engine — the central hub for querying CodeMemory.

Combines full-text search, semantic/embedding search, Reciprocal Rank
Fusion, and graph-aware re-ranking into a single ``search()`` coroutine.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    import networkx as nx
except ModuleNotFoundError:
    nx = None  # type: ignore[assignment]

from codememory.embeddings.encoder import EmbeddingEncoder
from codememory.models import FileInfo, RetrievalResult
from codememory.retrieval.query_parser import QueryParser
from codememory.retrieval.ranker import ResultRanker
from codememory.storage.database import Database

logger = logging.getLogger(__name__)


class RetrievalEngine:
    """Orchestrate multi-modal search over the CodeMemory knowledge base.

    Args:
        db:      Open :class:`~codememory.storage.database.Database` for
                 the project.
        encoder: Embedding encoder used for semantic search.
        G:       NetworkX directed graph representing the codebase
                 dependency / call graph.
    """

    def __init__(
        self,
        db: Database,
        encoder: EmbeddingEncoder,
        G: "nx.DiGraph | None",  # type: ignore[name-defined]
    ) -> None:
        self._db = db
        self._encoder = encoder
        self._G = G
        self._query_parser = QueryParser()
        self._ranker = ResultRanker()

    # ------------------------------------------------------------------
    # Primary search interface
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[RetrievalResult]:
        """Run a hybrid search and return ranked results.

        Pipeline:
        1. Parse query → extract hints and intent.
        2. Full-text search (FTS5 via SQLite).
        3. Semantic search (FAISS / embedding index).
        4. RRF fusion.
        5. Graph-aware re-ranking.

        Args:
            query:       Free-text query string.
            max_results: Maximum number of results to return.

        Returns:
            Ranked list of :class:`~codememory.models.RetrievalResult`.
        """
        parsed = self._query_parser.parse(query)
        logger.debug("Parsed query: intent=%s keywords=%s", parsed.intent, parsed.keywords)

        # --- 1. Full-text search -------------------------------------------
        fts_results: list[dict[str, Any]] = []
        try:
            fts_results = await self._db.fts_search(query, limit=max_results * 2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FTS search failed: %s", exc)

        # --- 2. Semantic search -------------------------------------------
        semantic_results: list[dict[str, Any]] = []
        try:
            embedding = await self._encoder.encode(query)
            semantic_results = await self._db.semantic_search(embedding, limit=max_results * 2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Semantic search failed: %s", exc)

        # --- 3. RRF fusion ------------------------------------------------
        fused = self._ranker.fuse_results(fts_results, semantic_results)

        # --- 4. Graph re-rank ---------------------------------------------
        if self._G is not None:
            fused = self._ranker.rerank_with_graph(fused, self._G, parsed)

        return fused[:max_results]

    # ------------------------------------------------------------------
    # Contextual helpers
    # ------------------------------------------------------------------

    async def get_file_context(self, file_path: str) -> dict[str, Any]:
        """Return full metadata and content for a single file.

        Args:
            file_path: Relative or absolute path string.

        Returns:
            Dictionary with keys ``file_info``, ``symbols``, ``imports``,
            ``connected_files``.
        """
        try:
            file_info: FileInfo | None = await self._db.get_file(file_path)
            if file_info is None:
                return {"error": f"File not found: {file_path}"}
            symbols = await self._db.get_symbols_for_file(file_path)
            connected = await self.get_connected_files(file_path, depth=1)
            return {
                "file_info": file_info.__dict__ if hasattr(file_info, "__dict__") else str(file_info),
                "symbols": [s.__dict__ if hasattr(s, "__dict__") else str(s) for s in symbols],
                "connected_files": connected,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("get_file_context failed: %s", exc)
            return {"error": str(exc)}

    async def get_connected_files(
        self,
        file_path: str,
        depth: int = 2,
    ) -> list[str]:
        """Return file paths reachable within *depth* hops in the graph.

        Args:
            file_path: Source node (relative path string).
            depth:     BFS depth limit.

        Returns:
            List of connected file path strings.
        """
        if self._G is None or file_path not in self._G:
            return []

        try:
            import networkx as _nx  # noqa: PLC0415

            lengths = _nx.single_source_shortest_path_length(
                self._G, file_path, cutoff=depth
            )
            return [node for node in lengths if node != file_path]
        except Exception as exc:  # noqa: BLE001
            logger.error("get_connected_files failed: %s", exc)
            return []

    async def get_architecture_context(self) -> dict[str, Any]:
        """Return a high-level architecture summary of the project.

        Returns:
            Dictionary with ``modules``, ``entry_points``, ``top_files``.
        """
        try:
            from codememory.intelligence.architecture import ArchitectureAnalyzer  # noqa: PLC0415

            analyzer = ArchitectureAnalyzer(self._db, self._G)
            return await analyzer.analyze()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Architecture analysis failed: %s", exc)
            return {"error": str(exc)}

    async def get_recent_changes(self, limit: int = 20) -> list[FileInfo]:
        """Return the most recently modified files tracked in the DB.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of :class:`~codememory.models.FileInfo` ordered by
            last-modified timestamp descending.
        """
        try:
            return await self._db.get_recent_files(limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.error("get_recent_changes failed: %s", exc)
            return []
