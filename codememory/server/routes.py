"""FastAPI route definitions for the CodeMemory REST API."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    """Payload for POST /search."""

    query: str
    max_results: int = 10


# ---------------------------------------------------------------------------
# Dependency helper
# ---------------------------------------------------------------------------

def _state(request: Request) -> Any:
    """Return the shared application state attached to the FastAPI app."""
    return request.app.state


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health", tags=["Meta"])
async def health(request: Request) -> JSONResponse:
    """Return service health status and basic statistics.

    Returns:
        JSON with ``status``, ``repo_path``, and ``stats`` fields.
    """
    state = _state(request)
    stats: dict[str, Any] = {}
    try:
        db = state.db
        stats = await db.get_stats()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stats fetch failed: %s", exc)

    return JSONResponse(
        {
            "status": "ok",
            "repo_path": str(getattr(state, "repo_path", "")),
            "stats": stats,
        }
    )


@router.get("/project/summary", tags=["Project"])
async def project_summary(request: Request) -> JSONResponse:
    """Return a high-level :class:`~codememory.models.ProjectSummary`.

    Returns:
        Serialised ``ProjectSummary`` dict.
    """
    state = _state(request)
    try:
        from codememory.intelligence.summarizer import FileSummarizer  # noqa: PLC0415

        summarizer: FileSummarizer = state.summarizer
        summary = await summarizer.get_project_summary()
        return JSONResponse(summary if isinstance(summary, dict) else summary.__dict__)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/project/architecture", tags=["Project"])
async def project_architecture(request: Request) -> JSONResponse:
    """Return the architecture analysis as a dictionary.

    Returns:
        Architecture dict produced by
        :class:`~codememory.intelligence.architecture.ArchitectureAnalyzer`.
    """
    state = _state(request)
    try:
        engine = state.engine
        arch = await engine.get_architecture_context()
        return JSONResponse(arch)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/search", tags=["Search"])
async def search(body: SearchRequest, request: Request) -> JSONResponse:
    """Perform a hybrid search against the code memory.

    Args:
        body: ``SearchRequest`` with ``query`` and optional ``max_results``.

    Returns:
        JSON array of :class:`~codememory.models.RetrievalResult` dicts.
    """
    state = _state(request)
    try:
        engine = state.engine
        results = await engine.search(body.query, max_results=body.max_results)
        serialised = [
            r.__dict__ if hasattr(r, "__dict__") else r for r in results
        ]
        return JSONResponse(serialised)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/files/{file_path:path}", tags=["Files"])
async def get_file(file_path: str, request: Request) -> JSONResponse:
    """Return :class:`~codememory.models.FileInfo` and symbols for a file.

    Args:
        file_path: Repository-relative path (URL-encoded).

    Returns:
        JSON with ``file_info`` and ``symbols`` keys.
    """
    state = _state(request)
    try:
        engine = state.engine
        ctx = await engine.get_file_context(file_path)
        if "error" in ctx:
            raise HTTPException(status_code=404, detail=ctx["error"])
        return JSONResponse(ctx)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/symbols/{name}", tags=["Symbols"])
async def get_symbol(name: str, request: Request) -> JSONResponse:
    """Look up a symbol by name across the entire codebase.

    Args:
        name: Symbol name (class, function, or variable).

    Returns:
        JSON array of matching symbol records.
    """
    state = _state(request)
    try:
        db = state.db
        symbols = await db.find_symbols_by_name(name)
        serialised = [
            s.__dict__ if hasattr(s, "__dict__") else s for s in symbols
        ]
        return JSONResponse(serialised)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/changes", tags=["Files"])
async def recent_changes(request: Request) -> JSONResponse:
    """Return the most recently indexed files.

    Returns:
        JSON array of :class:`~codememory.models.FileInfo` dicts.
    """
    state = _state(request)
    try:
        engine = state.engine
        files = await engine.get_recent_changes(limit=20)
        serialised = [
            f.__dict__ if hasattr(f, "__dict__") else f for f in files
        ]
        return JSONResponse(serialised)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/graph/neighbors/{file_path:path}", tags=["Graph"])
async def graph_neighbors(file_path: str, request: Request) -> JSONResponse:
    """Return the graph neighbors of *file_path* up to depth 2.

    Args:
        file_path: Repository-relative path of the source node.

    Returns:
        JSON array of connected file path strings.
    """
    state = _state(request)
    try:
        engine = state.engine
        neighbors = await engine.get_connected_files(file_path, depth=2)
        return JSONResponse(neighbors)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
