"""FastAPI application factory and MCP server factory for CodeMemory.

This module wires together all subsystems (Database, CodeRepository,
EmbeddingEncoder, RetrievalEngine, Graph) and exposes them via:

* A REST API (HTTP mode) through :func:`create_app`.
* An MCP stdio server (Cursor / Cline / Claude Desktop) through
  :func:`get_mcp_server`.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codememory.server.routes import router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _load_state(app: FastAPI, repo_path: Path) -> None:
    """Initialise all subsystems and attach them to *app.state*."""
    from codememory.config import get_repo_data_dir  # noqa: PLC0415
    from codememory.embeddings.encoder import EmbeddingEncoder  # noqa: PLC0415
    from codememory.graph.serializer import GraphSerializer  # noqa: PLC0415
    from codememory.intelligence.summarizer import FileSummarizer  # noqa: PLC0415
    from codememory.retrieval.engine import RetrievalEngine  # noqa: PLC0415
    from codememory.storage.database import Database  # noqa: PLC0415
    from codememory.storage.repository import CodeRepository  # noqa: PLC0415

    data_dir = get_repo_data_dir(repo_path)
    db_path = data_dir / "codememory.db"

    db = Database(db_path)
    await db.connect()
    logger.info("Database connected at %s", db_path)

    repo = CodeRepository(repo_path, db)

    encoder = EmbeddingEncoder()
    await encoder.load()
    logger.info("Embedding encoder loaded.")

    graph_data = None
    graph_path = data_dir / "graph.json"
    try:
        if graph_path.exists():
            graph_data = GraphSerializer.load(graph_path)
            logger.info("Graph loaded from %s.", graph_path)
        else:
            logger.info("No graph file found at %s; graph unavailable.", graph_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Graph not available: %s", exc)

    engine = RetrievalEngine(db, encoder, graph_data)
    summarizer = FileSummarizer()

    # Inject into MCP tools module
    from codememory.server import tools as _tools  # noqa: PLC0415
    _tools._set_state(engine, db, summarizer, repo_path)

    app.state.repo_path = repo_path
    app.state.db = db
    app.state.repo = repo
    app.state.encoder = encoder
    app.state.graph = graph_data
    app.state.engine = engine
    app.state.summarizer = summarizer


async def _shutdown_state(app: FastAPI) -> None:
    """Clean up database connections and any background tasks."""
    try:
        await app.state.db.disconnect()
        logger.info("Database disconnected.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error during shutdown: %s", exc)


# ---------------------------------------------------------------------------
# Public factories
# ---------------------------------------------------------------------------

def create_app(repo_path: Path) -> FastAPI:
    """Create and configure the CodeMemory FastAPI application.

    Args:
        repo_path: Root path of the repository to serve.

    Returns:
        Configured :class:`fastapi.FastAPI` instance.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        await _load_state(app, repo_path)
        yield
        await _shutdown_state(app)

    app = FastAPI(
        title="CodeMemory API",
        description=(
            "Universal context layer for AI coding agents. "
            "Provides hybrid code search, graph traversal, and project intelligence."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — permissive for local development; tighten for production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app


def get_mcp_server(repo_path: Path) -> Any:
    """Create an MCP server in stdio mode for Cursor / Cline / Claude Desktop.

    The server registers all tool functions from
    :mod:`codememory.server.tools` and returns a :class:`FastMCP` instance
    ready for ``server.run()`` / ``asyncio.run(server.run_async())``.

    Args:
        repo_path: Root path of the repository to serve.

    Returns:
        :class:`mcp.server.fastmcp.FastMCP` instance.
    """
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise ImportError(
            "mcp package is required for MCP mode. Install with: pip install mcp"
        ) from exc

    from codememory.server import tools  # noqa: PLC0415

    mcp = FastMCP("CodeMemory")

    # Register all tool functions (20 core tools + compatibility aliases)
    mcp.tool()(tools.get_project_summary)
    mcp.tool()(tools.get_ai_context)
    mcp.tool()(tools.get_architecture_overview)
    mcp.tool()(tools.get_repository_health)
    mcp.tool()(tools.get_deployment_readiness)
    mcp.tool()(tools.get_risk_report)
    mcp.tool()(tools.get_module_summary)
    mcp.tool()(tools.explain_component)
    mcp.tool()(tools.get_important_files)
    mcp.tool()(tools.get_system_hotspots)
    mcp.tool()(tools.get_related_components)
    mcp.tool()(tools.get_dependency_graph)
    mcp.tool()(tools.get_change_impact)
    mcp.tool()(tools.get_test_gaps)
    mcp.tool()(tools.get_feature_status)
    mcp.tool()(tools.get_next_tasks)
    mcp.tool()(tools.get_unfinished_work)
    mcp.tool()(tools.get_context_pack)
    mcp.tool()(tools.get_project_history)
    mcp.tool()(tools.get_leftover_work)
    mcp.tool()(tools.search_codebase)
    # Compatibility aliases
    mcp.tool()(tools.search_memory)
    mcp.tool()(tools.get_recent_changes)
    mcp.tool()(tools.get_architecture)
    mcp.tool()(tools.get_health_status)

    # Bootstrap state synchronously on first call via a startup hook
    import asyncio  # noqa: PLC0415

    async def _bootstrap() -> None:
        from codememory.config import get_repo_data_dir  # noqa: PLC0415
        from codememory.embeddings.encoder import EmbeddingEncoder  # noqa: PLC0415
        from codememory.graph.serializer import GraphSerializer  # noqa: PLC0415
        from codememory.intelligence.summarizer import FileSummarizer  # noqa: PLC0415
        from codememory.retrieval.engine import RetrievalEngine  # noqa: PLC0415
        from codememory.storage.database import Database  # noqa: PLC0415
        from codememory.storage.repository import CodeRepository  # noqa: PLC0415

        data_dir = get_repo_data_dir(repo_path)
        db = Database(data_dir / "codememory.db")
        await db.initialize()
        encoder = EmbeddingEncoder()
        await encoder.load()
        graph_data = None
        graph_path = data_dir / "graph.json"
        try:
            if graph_path.exists():
                graph_data = GraphSerializer.load(graph_path)
        except Exception:  # noqa: BLE001
            pass
        repo = CodeRepository(repo_path, db)
        engine = RetrievalEngine(db, encoder, graph_data)
        summarizer = FileSummarizer()
        tools._set_state(engine, db, summarizer, repo_path)

    # Run bootstrap before serving
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_bootstrap())
        else:
            loop.run_until_complete(_bootstrap())
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP bootstrap deferred: %s", exc)

    return mcp
