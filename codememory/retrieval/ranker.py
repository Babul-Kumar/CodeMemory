"""Result ranking for the CodeMemory retrieval engine.

Implements Reciprocal Rank Fusion (RRF) to merge full-text-search and
semantic-search result lists, followed by graph-aware re-ranking that
boosts files connected to already high-ranked results.
"""
from __future__ import annotations

import logging
from typing import Any

try:
    import networkx as nx
except ModuleNotFoundError:
    nx = None  # type: ignore[assignment]

from codememory.models import RetrievalResult
from codememory.retrieval.query_parser import ParsedQuery

logger = logging.getLogger(__name__)

# RRF smoothing constant — higher values reduce the impact of top positions.
_RRF_K: int = 60


class ResultRanker:
    """Merge and re-rank retrieval results using RRF and graph proximity."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fuse_results(
        self,
        fts_results: list[dict[str, Any]],
        semantic_results: list[dict[str, Any]],
    ) -> list[RetrievalResult]:
        """Fuse full-text-search and semantic search results via RRF.

        Each result dict must contain at minimum a ``"file_path"`` key and
        should contain a ``"score"`` key (float, higher = better).  Optional
        keys ``"snippet"``, ``"language"``, ``"symbol"`` are forwarded into
        :class:`~codememory.models.RetrievalResult`.

        Args:
            fts_results:      Ranked list from full-text search (best first).
            semantic_results: Ranked list from semantic/embedding search
                              (best first).

        Returns:
            Merged and re-ranked list of :class:`~codememory.models.RetrievalResult`
            objects (best first).
        """
        scores: dict[str, float] = {}

        for rank, result in enumerate(fts_results, start=1):
            fp = result.get("file_path", "")
            raw_score = result.get("score")
            score_contrib = 1.0 / (_RRF_K + rank)
            if raw_score is not None:
                try:
                    score_contrib += float(raw_score) * 0.1
                except (ValueError, TypeError):
                    pass
            scores[fp] = scores.get(fp, 0.0) + score_contrib

        for rank, result in enumerate(semantic_results, start=1):
            fp = result.get("file_path", "")
            raw_score = result.get("score")
            score_contrib = 1.0 / (_RRF_K + rank)
            if raw_score is not None:
                try:
                    score_contrib += float(raw_score) * 0.1
                except (ValueError, TypeError):
                    pass
            scores[fp] = scores.get(fp, 0.0) + score_contrib

        # Build a lookup for metadata from both result lists
        metadata: dict[str, dict[str, Any]] = {}
        for result in fts_results + semantic_results:
            fp = result.get("file_path", "")
            if fp not in metadata:
                metadata[fp] = result

        sorted_paths = sorted(scores, key=lambda p: scores[p], reverse=True)

        retrieval_results: list[RetrievalResult] = []
        for fp in sorted_paths:
            meta = metadata.get(fp, {})
            retrieval_results.append(
                RetrievalResult(
                    file_path=fp,
                    score=round(scores[fp], 6),
                    snippet=meta.get("snippet", ""),
                    language=meta.get("language", ""),
                    symbol=meta.get("symbol"),
                    match_type=meta.get("match_type", "hybrid"),
                )
            )

        return retrieval_results

    def rerank_with_graph(
        self,
        results: list[RetrievalResult],
        G: "nx.DiGraph",  # type: ignore[name-defined]
        query: ParsedQuery,
    ) -> list[RetrievalResult]:
        """Re-rank *results* using graph connectivity and query hints.

        Two boosting strategies are applied:

        1. **Graph proximity boost** — files directly connected to the
           top-ranked result receive a small score increase proportional
           to their edge weight (or ``0.1`` if unweighted).
        2. **Hint boost** — files whose path or base name matches a
           ``file_hint`` or ``symbol_hint`` from *query* receive an
           additional ``+0.15`` boost.

        Args:
            results: Already RRF-fused results (modified in-place, then
                     re-sorted).
            G:       NetworkX directed graph produced by GraphBuilder.
            query:   Parsed query with file/symbol hints.

        Returns:
            Re-ranked list (new list object, results objects mutated).
        """
        if nx is None or G is None or G.number_of_nodes() == 0:
            return results

        if not results:
            return results

        # Build hint sets for O(1) lookup
        file_hints_lower = {h.lower() for h in query.file_hints}
        symbol_hints_lower = {h.lower() for h in query.symbol_hints}

        # Index existing scores for quick update
        score_map: dict[str, float] = {r.file_path: r.score for r in results}

        # Graph boost: use the top-ranked file as the seed
        top_file = results[0].file_path
        if top_file in G:
            for neighbour in G.successors(top_file):
                edge_data = G.get_edge_data(top_file, neighbour) or {}
                weight: float = float(edge_data.get("weight", 0.1))
                boost = weight * 0.1
                score_map[neighbour] = score_map.get(neighbour, 0.0) + boost

        # Hint boost
        for fp in list(score_map.keys()):
            fp_lower = fp.lower()
            for hint in file_hints_lower | symbol_hints_lower:
                if hint in fp_lower:
                    score_map[fp] = score_map.get(fp, 0.0) + 0.15
                    break

        # Apply updated scores and re-sort
        for result in results:
            result.score = round(score_map.get(result.file_path, result.score), 6)

        results.sort(key=lambda r: r.score, reverse=True)
        return results
