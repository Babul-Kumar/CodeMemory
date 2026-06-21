"""Async SQLite database layer for CodeMemory."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from codememory.config import get_repo_data_dir
from codememory.constants import DB_FILENAME

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """Async SQLite connection manager with WAL mode and sqlite-vec support.

    Implements the async context manager protocol.  A single long-lived
    connection is reused throughout a session (WAL mode allows concurrent
    reads without blocking writes).

    Usage::

        async with Database(db_path) as db:
            conn = await db.get_connection()
            ...
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the database handle.

        Args:
            db_path: Absolute path to the SQLite database file.
        """
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    # ── Context manager ────────────────────────────────────────────────────

    async def __aenter__(self) -> "Database":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Open the database, apply pragmas, load extensions, and run schema.

        Creates parent directories if they do not exist.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        # Enable WAL and performance pragmas
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA synchronous = NORMAL;")
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA temp_store = MEMORY;")
        await self._conn.execute("PRAGMA mmap_size = 134217728;")  # 128 MB

        # Attempt to load sqlite-vec extension for vector search
        try:
            await self._conn.enable_load_extension(True)
            import sqlite_vec

            vec_path = sqlite_vec.loadable_path()
            await self._conn.load_extension(vec_path)
            logger.debug("sqlite-vec extension loaded from %s", vec_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sqlite-vec extension not available; vector search disabled: %s", exc
            )

        # Apply schema
        await self._apply_schema()
        await self._conn.commit()
        logger.debug("Database initialised at %s", self._db_path)

    async def _apply_schema(self) -> None:
        """Execute the SQL schema file to create tables and triggers."""
        from codememory.storage.migrations import apply_migrations
        try:
            await apply_migrations(self._conn, _SCHEMA_PATH)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to apply database schema and migrations: %s", exc)

    async def close(self) -> None:
        """Close the underlying aiosqlite connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    # Aliases for alternative naming convention
    async def connect(self) -> None:
        """Alias for :meth:`initialize`."""
        await self.initialize()

    async def disconnect(self) -> None:
        """Alias for :meth:`close`."""
        await self.close()

    # ── Connection access ──────────────────────────────────────────────────

    async def get_connection(self) -> aiosqlite.Connection:
        """Return the active aiosqlite connection.

        Returns:
            The open :class:`aiosqlite.Connection`.

        Raises:
            RuntimeError: If the database has not been initialised.
        """
        if self._conn is None:
            raise RuntimeError("Database is not initialised. Use 'async with Database(...)'.")
        return self._conn

    # ── Utility ────────────────────────────────────────────────────────────

    @staticmethod
    def get_db_path(repo_path: Path) -> Path:
        """Compute the database path for a given repository.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            Path under ``~/.codememory/<repo_hash>/codememory.db``.
        """
        return get_repo_data_dir(repo_path) / DB_FILENAME

    # ── Compatibility Delegation Methods ───────────────────────────────────

    async def get_file(self, path: str) -> Any:
        """Compatibility delegate for :meth:`CodeRepository.get_file`."""
        from codememory.storage.repository import CodeRepository
        repo = CodeRepository(Path("."), self)
        return await repo.get_file(path)

    async def fts_search(self, query: str, limit: int = 20) -> list[dict]:
        """Compatibility delegate for :meth:`CodeRepository.search_fts`."""
        from codememory.storage.repository import CodeRepository
        repo = CodeRepository(Path("."), self)
        return await repo.search_fts(query, limit)

    async def semantic_search(self, query_vec: Any, limit: int = 20) -> list[dict]:
        """Find the most similar files to the given vector embedding."""
        from codememory.embeddings.searcher import EmbeddingSearcher
        searcher = EmbeddingSearcher()
        return await searcher.search(self, query_vec, limit)

    async def get_stats(self) -> dict:
        """Compatibility delegate for :meth:`CodeRepository.get_project_stats`."""
        from codememory.storage.repository import CodeRepository
        repo = CodeRepository(Path("."), self)
        return await repo.get_project_stats()

    async def find_symbols_by_name(self, name: str) -> list[Any]:
        """Compatibility delegate for :meth:`CodeRepository.find_symbols_by_name`."""
        from codememory.storage.repository import CodeRepository
        repo = CodeRepository(Path("."), self)
        return await repo.find_symbols_by_name(name)

