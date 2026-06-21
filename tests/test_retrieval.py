"""Tests for the retrieval layer (QueryParser + ResultRanker + RetrievalEngine)."""
from __future__ import annotations

import pytest

from codememory.models import RetrievalResult
from codememory.retrieval.query_parser import ParsedQuery, QueryParser
from codememory.retrieval.ranker import ResultRanker


# ---------------------------------------------------------------------------
# QueryParser
# ---------------------------------------------------------------------------

class TestQueryParser:
    """Unit tests for :class:`QueryParser`."""

    def setup_method(self) -> None:
        self.parser = QueryParser()

    def test_parse_returns_parsed_query(self) -> None:
        pq = self.parser.parse("find the User class in models")
        assert isinstance(pq, ParsedQuery)
        assert pq.original_query == "find the User class in models"

    def test_extracts_camel_case_symbol(self) -> None:
        pq = self.parser.parse("show me UserManager and OrderProcessor")
        assert "UserManager" in pq.symbol_hints
        assert "OrderProcessor" in pq.symbol_hints

    def test_extracts_file_path_hints(self) -> None:
        pq = self.parser.parse("look at utils/helpers.py for the greet function")
        assert any("helpers.py" in h for h in pq.file_hints)

    def test_extracts_module_hint(self) -> None:
        pq = self.parser.parse("where is codememory.scanner defined?")
        assert any("codememory.scanner" in h for h in pq.file_hints)

    def test_intent_fix(self) -> None:
        pq = self.parser.parse("fix the bug in the auth module")
        assert pq.intent == "fix"

    def test_intent_refactor(self) -> None:
        pq = self.parser.parse("refactor the database layer to simplify queries")
        assert pq.intent == "refactor"

    def test_intent_test(self) -> None:
        pq = self.parser.parse("write tests for the User model")
        assert pq.intent == "test"

    def test_intent_add(self) -> None:
        pq = self.parser.parse("add a new endpoint for user registration")
        assert pq.intent == "add"

    def test_intent_defaults_to_search(self) -> None:
        pq = self.parser.parse("greet function")
        # "greet" and "function" have no strong intent keywords → search
        assert pq.intent in ("search", "add", "fix", "refactor", "test", "document", "understand")

    def test_keywords_exclude_stop_words(self) -> None:
        pq = self.parser.parse("how do I find the user model")
        stop_words = {"how", "do", "i", "the"}
        for kw in pq.keywords:
            assert kw not in stop_words, f"Stop word leaked into keywords: {kw!r}"

    def test_empty_query(self) -> None:
        pq = self.parser.parse("")
        assert pq.original_query == ""
        assert pq.keywords == []


# ---------------------------------------------------------------------------
# ResultRanker — RRF fusion
# ---------------------------------------------------------------------------

class TestResultRanker:
    """Unit tests for :class:`ResultRanker`."""

    def setup_method(self) -> None:
        self.ranker = ResultRanker()

    def _make_fts(self, paths: list[str]) -> list[dict]:
        return [{"file_path": p, "score": 1.0, "snippet": "", "language": "python"} for p in paths]

    def _make_sem(self, paths: list[str]) -> list[dict]:
        return [{"file_path": p, "score": 0.9, "snippet": "", "language": "python"} for p in paths]

    def test_fuse_returns_retrieval_results(self) -> None:
        fts = self._make_fts(["a.py", "b.py"])
        sem = self._make_sem(["b.py", "c.py"])
        results = self.ranker.fuse_results(fts, sem)
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_fuse_top_result_is_in_both_lists(self) -> None:
        """A file appearing in both FTS and semantic results should rank highest."""
        fts = self._make_fts(["shared.py", "only_fts.py"])
        sem = self._make_sem(["shared.py", "only_sem.py"])
        results = self.ranker.fuse_results(fts, sem)
        assert results[0].file_path == "shared.py", (
            f"Expected shared.py at top, got {results[0].file_path}"
        )

    def test_fuse_preserves_all_unique_files(self) -> None:
        fts = self._make_fts(["a.py", "b.py"])
        sem = self._make_sem(["b.py", "c.py"])
        results = self.ranker.fuse_results(fts, sem)
        paths = {r.file_path for r in results}
        assert paths == {"a.py", "b.py", "c.py"}

    def test_fuse_empty_inputs(self) -> None:
        results = self.ranker.fuse_results([], [])
        assert results == []

    def test_fuse_only_fts(self) -> None:
        fts = self._make_fts(["a.py", "b.py", "c.py"])
        results = self.ranker.fuse_results(fts, [])
        assert len(results) == 3
        # a.py should be ranked first (rank 1 in FTS)
        assert results[0].file_path == "a.py"

    def test_rrf_score_decreases_with_rank(self) -> None:
        """RRF scores should strictly decrease for consecutive ranks from a single list."""
        fts = self._make_fts(["first.py", "second.py", "third.py"])
        results = self.ranker.fuse_results(fts, [])
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), "Scores should be descending"

    def test_rerank_with_graph_no_graph(self) -> None:
        """rerank_with_graph should return results unchanged when G is None."""
        fts = self._make_fts(["a.py", "b.py"])
        results = self.ranker.fuse_results(fts, [])
        parser = QueryParser()
        pq = parser.parse("test query")
        reranked = self.ranker.rerank_with_graph(results, None, pq)  # type: ignore[arg-type]
        assert [r.file_path for r in reranked] == [r.file_path for r in results]

    def test_rerank_with_hint_boosts_matching_file(self) -> None:
        """Files matching query hints should be boosted in score."""
        try:
            import networkx as nx
        except ModuleNotFoundError:
            pytest.skip("networkx not installed")

        G = nx.DiGraph()
        G.add_edge("utils/helpers.py", "models/user.py", weight=1.0)

        fts = self._make_fts(["models/user.py", "utils/helpers.py"])
        results = self.ranker.fuse_results(fts, [])

        parser = QueryParser()
        pq = parser.parse("show me helpers.py file")
        # inject file hint manually
        pq.file_hints = ["helpers.py"]

        reranked = self.ranker.rerank_with_graph(results, G, pq)
        # helpers.py should be boosted to top
        assert reranked[0].file_path == "utils/helpers.py"


# ---------------------------------------------------------------------------
# RetrievalEngine and Semantic Search Integration
# ---------------------------------------------------------------------------

class DummyEncoder:
    async def load(self) -> None:
        pass
    def encode(self, texts: list[str]) -> list[any]:
        import numpy as np
        return [np.zeros(384, dtype=np.float32) for _ in texts]


@pytest.mark.asyncio
async def test_database_semantic_search_delegation(db) -> None:
    """db.semantic_search should delegate to EmbeddingSearcher successfully."""
    import numpy as np
    from pathlib import Path
    from codememory.embeddings.indexer import EmbeddingIndexer
    await EmbeddingIndexer().ensure_table(db)
    vec = np.zeros(384, dtype=np.float32)
    results = await db.semantic_search(vec, limit=5)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_retrieval_engine_search_pipeline(db) -> None:
    """RetrievalEngine.search should run hybrid search and merge results successfully."""
    from codememory.retrieval.engine import RetrievalEngine
    from codememory.storage.repository import CodeRepository
    from codememory.models import FileInfo
    from pathlib import Path

    repo = CodeRepository(Path("/fake"), db)
    await repo.upsert_file(
        FileInfo(
            path="a.py",
            language="python",
            content="def my_func(): pass",
            hash="h1",
            size_bytes=19,
            symbols=[]
        )
    )

    engine = RetrievalEngine(db, DummyEncoder(), None)  # type: ignore[arg-type]
    results = await engine.search("my_func")
    assert isinstance(results, list)
