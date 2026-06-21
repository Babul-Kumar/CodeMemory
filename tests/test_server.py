"""Tests for the REST API server endpoints using FastAPI TestClient."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from codememory.models import FileInfo, RetrievalResult


# ---------------------------------------------------------------------------
# Minimal fake state for dependency injection
# ---------------------------------------------------------------------------

def _make_retrieval_result(file_path: str = "main.py") -> RetrievalResult:
    return RetrievalResult(
        file_path=file_path,
        score=0.95,
        snippet="def main():",
        language="python",
        symbol=None,
        match_type="hybrid",
    )


def _make_file_info(path: str = "main.py") -> FileInfo:
    return FileInfo(
        path=path,
        language="python",
        content="def main(): pass\n",
        hash="abc",
        symbols=[],
        size=18,
        last_modified=0.0,
    )


def _build_mock_state() -> dict[str, Any]:
    """Return a dict of mocked subsystems to attach to app.state."""
    mock_engine = MagicMock()
    mock_engine.search = AsyncMock(return_value=[_make_retrieval_result()])
    mock_engine.get_architecture_context = AsyncMock(return_value={"modules": []})
    mock_engine.get_file_context = AsyncMock(
        return_value={
            "file_info": _make_file_info().__dict__,
            "symbols": [],
            "connected_files": [],
        }
    )
    mock_engine.get_connected_files = AsyncMock(return_value=["utils/helpers.py"])
    mock_engine.get_recent_changes = AsyncMock(return_value=[_make_file_info()])

    mock_db = MagicMock()
    mock_db.get_stats = AsyncMock(return_value={"file_count": 42, "symbol_count": 150})
    mock_db.find_symbols_by_name = AsyncMock(return_value=[])

    mock_summarizer = MagicMock()
    mock_summarizer.get_project_summary = AsyncMock(
        return_value={"name": "TestProject", "file_count": 42}
    )

    return {
        "engine": mock_engine,
        "db": mock_db,
        "summarizer": mock_summarizer,
        "repo_path": Path("/fake/repo"),
    }


def _make_test_client() -> TestClient:
    """Create a TestClient with mocked application state (no lifespan)."""
    from fastapi import FastAPI

    from codememory.server.routes import router

    test_app = FastAPI()
    test_app.include_router(router)

    state_dict = _build_mock_state()
    for key, value in state_dict.items():
        setattr(test_app.state, key, value)

    return TestClient(test_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_health_returns_200(self) -> None:
        response = self.client.get("/health")
        assert response.status_code == 200

    def test_health_has_status_ok(self) -> None:
        response = self.client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    def test_health_includes_stats(self) -> None:
        response = self.client.get("/health")
        data = response.json()
        assert "stats" in data
        assert data["stats"]["file_count"] == 42


class TestProjectSummaryEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_summary_returns_200(self) -> None:
        response = self.client.get("/project/summary")
        assert response.status_code == 200

    def test_summary_has_name(self) -> None:
        response = self.client.get("/project/summary")
        data = response.json()
        assert data["name"] == "TestProject"


class TestArchitectureEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_architecture_returns_200(self) -> None:
        response = self.client.get("/project/architecture")
        assert response.status_code == 200

    def test_architecture_has_modules(self) -> None:
        response = self.client.get("/project/architecture")
        data = response.json()
        assert "modules" in data


class TestSearchEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_search_returns_200(self) -> None:
        response = self.client.post("/search", json={"query": "user authentication"})
        assert response.status_code == 200

    def test_search_returns_list(self) -> None:
        response = self.client.post("/search", json={"query": "user"})
        data = response.json()
        assert isinstance(data, list)

    def test_search_result_has_file_path(self) -> None:
        response = self.client.post("/search", json={"query": "main"})
        data = response.json()
        assert len(data) > 0
        assert "file_path" in data[0]

    def test_search_with_max_results(self) -> None:
        response = self.client.post(
            "/search", json={"query": "test", "max_results": 5}
        )
        assert response.status_code == 200

    def test_search_empty_query(self) -> None:
        response = self.client.post("/search", json={"query": ""})
        assert response.status_code == 200


class TestFilesEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_get_file_returns_200(self) -> None:
        response = self.client.get("/files/main.py")
        assert response.status_code == 200

    def test_get_file_has_file_info(self) -> None:
        response = self.client.get("/files/main.py")
        data = response.json()
        assert "file_info" in data

    def test_get_file_has_symbols(self) -> None:
        response = self.client.get("/files/main.py")
        data = response.json()
        assert "symbols" in data


class TestChangesEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_changes_returns_200(self) -> None:
        response = self.client.get("/changes")
        assert response.status_code == 200

    def test_changes_returns_list(self) -> None:
        response = self.client.get("/changes")
        data = response.json()
        assert isinstance(data, list)


class TestGraphNeighborsEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_neighbors_returns_200(self) -> None:
        response = self.client.get("/graph/neighbors/main.py")
        assert response.status_code == 200

    def test_neighbors_returns_list(self) -> None:
        response = self.client.get("/graph/neighbors/main.py")
        data = response.json()
        assert isinstance(data, list)
        assert "utils/helpers.py" in data


class TestSymbolsEndpoint:
    def setup_method(self) -> None:
        self.client = _make_test_client()

    def test_symbol_lookup_returns_200(self) -> None:
        response = self.client.get("/symbols/User")
        assert response.status_code == 200

    def test_symbol_lookup_returns_list(self) -> None:
        response = self.client.get("/symbols/User")
        data = response.json()
        assert isinstance(data, list)
