"""High-level CRUD operations for the CodeMemory SQLite database."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from codememory.models import FileInfo, RelationshipInfo, ScanResult, SymbolInfo
from codememory.storage.database import Database

logger = logging.getLogger(__name__)


class CodeRepository:
    """Provides all data access methods for the CodeMemory knowledge store.

    All methods are async and expect a live :class:`~codememory.storage.database.Database`
    instance (used as an async context manager at a higher level).
    """

    def __init__(self, repo_path: Path, db: Database) -> None:
        """Initialise the repository.

        Args:
            repo_path: Root path of the repository.
            db:        An initialised :class:`~codememory.storage.database.Database`.
        """
        self.root_path = repo_path
        self._db = db

    # ── File CRUD ─────────────────────────────────────────────────────────

    async def upsert_file(self, scan_result: ScanResult) -> int:
        """Insert or update a file record and its associated symbols.

        Rebuilds the FTS index entry for the file after upsert.

        Args:
            scan_result: The full extraction result for a file.

        Returns:
            The ``id`` of the upserted file row.
        """
        conn = await self._db.get_connection()
        if hasattr(scan_result, "file_info"):
            fi = scan_result.file_info
            symbols = scan_result.symbols
        else:
            fi = scan_result
            symbols = getattr(scan_result, "symbols", []) or []
        now = time.time()

        # Upsert file row
        await conn.execute(
            """
            INSERT INTO files (path, language, hash, last_indexed, size_bytes, summary, metadata)
            VALUES (:path, :language, :hash, :last_indexed, :size_bytes, :summary, :metadata)
            ON CONFLICT(path) DO UPDATE SET
                language     = excluded.language,
                hash         = excluded.hash,
                last_indexed = excluded.last_indexed,
                size_bytes   = excluded.size_bytes,
                summary      = excluded.summary,
                metadata     = excluded.metadata
            """,
            {
                "path": fi.path,
                "language": fi.language,
                "hash": fi.hash,
                "last_indexed": fi.last_scanned or now,
                "size_bytes": fi.size_bytes,
                "summary": fi.summary,
                "metadata": None,
            },
        )

        # Retrieve file_id
        cursor = await conn.execute("SELECT id FROM files WHERE path = ?", (fi.path,))
        row = await cursor.fetchone()
        file_id: int = row["id"]

        # Delete existing symbols (cascade) and re-insert
        await conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))

        # Insert symbols
        parent_map: dict[str, int] = {}
        for sym in symbols:
            cur = await conn.execute(
                """
                INSERT INTO symbols (file_id, name, kind, signature, docstring, start_line, end_line, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    sym.name,
                    sym.kind,
                    sym.signature,
                    sym.docstring,
                    sym.start_line,
                    sym.end_line,
                    parent_map.get(sym.parent_name) if sym.parent_name else None,
                ),
            )
            if sym.kind == "class":
                parent_map[sym.name] = cur.lastrowid

        await conn.commit()
        return file_id

    async def get_file(self, path: str) -> FileInfo | None:
        """Retrieve file metadata by path.

        Args:
            path: Repository-relative or absolute file path.

        Returns:
            A :class:`~codememory.models.FileInfo` or ``None`` if not found.
        """
        conn = await self._db.get_connection()
        cursor = await conn.execute(
            "SELECT path, language, hash, last_indexed, size_bytes, summary FROM files WHERE path = ?",
            (path,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return FileInfo(
            path=row["path"],
            language=row["language"],
            hash=row["hash"],
            last_scanned=row["last_indexed"],
            size_bytes=row["size_bytes"],
            summary=row["summary"],
        )

    async def get_all_files(self) -> list[FileInfo]:
        """Return all indexed files.

        Returns:
            List of :class:`~codememory.models.FileInfo` objects.
        """
        conn = await self._db.get_connection()
        cursor = await conn.execute(
            "SELECT path, language, hash, last_indexed, size_bytes, summary FROM files ORDER BY path"
        )
        rows = await cursor.fetchall()
        return [
            FileInfo(
                path=r["path"],
                language=r["language"],
                hash=r["hash"],
                last_scanned=r["last_indexed"],
                size_bytes=r["size_bytes"],
                summary=r["summary"],
            )
            for r in rows
        ]

    async def get_changed_files(self, hashes: dict[str, str]) -> list[str]:
        """Identify files whose stored hash differs from the provided hash.

        Args:
            hashes: Mapping of ``{file_path: sha256_hex}`` from a fresh disk scan.

        Returns:
            List of file paths that need re-indexing.
        """
        if not hashes:
            return []
        conn = await self._db.get_connection()
        changed: list[str] = []
        for path, new_hash in hashes.items():
            cursor = await conn.execute(
                "SELECT hash FROM files WHERE path = ?", (path,)
            )
            row = await cursor.fetchone()
            if row is None or row["hash"] != new_hash:
                changed.append(path)
        return changed

    async def get_all_file_hashes(self) -> dict[str, str]:
        """Retrieve a mapping of relative file paths to their stored SHA-256 hashes.

        Returns:
            Dict of ``{path: hash}``.
        """
        conn = await self._db.get_connection()
        cursor = await conn.execute("SELECT path, hash FROM files")
        rows = await cursor.fetchall()
        return {r["path"]: r["hash"] or "" for r in rows}

    async def delete_file(self, path: str) -> None:
        """Delete a file record (symbols and relationships cascade).

        Args:
            path: File path to delete.
        """
        conn = await self._db.get_connection()
        await conn.execute("DELETE FROM files WHERE path = ?", (path,))
        await conn.commit()

    async def update_file_summary(self, path: str, summary: str) -> None:
        """Update the human-readable summary for a file.

        Args:
            path:    File path.
            summary: Generated summary text.
        """
        conn = await self._db.get_connection()
        await conn.execute(
            "UPDATE files SET summary = ? WHERE path = ?", (summary, path)
        )
        await conn.commit()

    # ── Symbol CRUD ───────────────────────────────────────────────────────

    async def get_symbols_for_file(self, file_id: int) -> list[SymbolInfo]:
        """Retrieve all symbols for a given file id.

        Args:
            file_id: Primary key of the file row.

        Returns:
            List of :class:`~codememory.models.SymbolInfo` objects.
        """
        conn = await self._db.get_connection()
        cursor = await conn.execute(
            """
            SELECT s.name, s.kind, f.path, s.start_line, s.end_line, s.signature, s.docstring,
                   p.name AS parent_name
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            LEFT JOIN symbols p ON s.parent_id = p.id
            WHERE s.file_id = ?
            ORDER BY s.start_line
            """,
            (file_id,),
        )
        rows = await cursor.fetchall()
        return [
            SymbolInfo(
                name=r["name"],
                kind=r["kind"],
                file_path=r["path"],
                start_line=r["start_line"] or 0,
                end_line=r["end_line"] or 0,
                signature=r["signature"],
                docstring=r["docstring"],
                parent_name=r["parent_name"],
            )
            for r in rows
        ]

    async def find_symbols_by_name(self, name: str) -> list[SymbolInfo]:
        """Look up symbols by name across the entire codebase.

        Args:
            name: The symbol name to search for.

        Returns:
            List of matching :class:`~codememory.models.SymbolInfo` objects.
        """
        conn = await self._db.get_connection()
        cursor = await conn.execute(
            """
            SELECT s.name, s.kind, f.path, s.start_line, s.end_line, s.signature, s.docstring,
                   p.name AS parent_name
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            LEFT JOIN symbols p ON s.parent_id = p.id
            WHERE s.name = ?
            ORDER BY f.path, s.start_line
            """,
            (name,),
        )
        rows = await cursor.fetchall()
        return [
            SymbolInfo(
                name=r["name"],
                kind=r["kind"],
                file_path=r["path"],
                start_line=r["start_line"] or 0,
                end_line=r["end_line"] or 0,
                signature=r["signature"],
                docstring=r["docstring"],
                parent_name=r["parent_name"],
            )
            for r in rows
        ]

    # ── Relationships ─────────────────────────────────────────────────────

    async def upsert_relationship(self, rel: RelationshipInfo) -> None:
        """Insert a relationship if it does not already exist.

        Args:
            rel: :class:`~codememory.models.RelationshipInfo` to store.
        """
        conn = await self._db.get_connection()

        async def _get_file_id(path: str) -> int | None:
            c = await conn.execute("SELECT id FROM files WHERE path = ?", (path,))
            r = await c.fetchone()
            return r["id"] if r else None

        from_id = await _get_file_id(rel.from_file)
        to_id = await _get_file_id(rel.to_file)
        if from_id is None or to_id is None:
            logger.debug(
                "Skipping relationship %s -> %s: one or both files not indexed.",
                rel.from_file,
                rel.to_file,
            )
            return

        await conn.execute(
            """
            INSERT OR IGNORE INTO relationships
                (from_file_id, to_file_id, from_symbol, to_symbol, rel_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (from_id, to_id, rel.from_symbol, rel.to_symbol, rel.rel_type),
        )
        await conn.commit()

    # ── Search ────────────────────────────────────────────────────────────

    async def search_fts(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across symbol names, docstrings, and signatures.

        Uses FTS5 for fast token-based lookup.

        Args:
            query: Search query string (FTS5 syntax supported).
            limit: Maximum number of results.

        Returns:
            List of dicts with keys: ``file_path``, ``symbol_name``, ``kind``,
            ``snippet``, ``rank``.
        """
        conn = await self._db.get_connection()
        results: list[dict] = []
        try:
            cursor = await conn.execute(
                """
                SELECT f.path AS file_path,
                       s.name AS symbol_name,
                       s.kind,
                       snippet(symbols_fts, 0, '<b>', '</b>', '…', 10) AS snippet,
                       symbols_fts.rank
                FROM symbols_fts
                JOIN symbols s ON symbols_fts.rowid = s.id
                JOIN files f ON s.file_id = f.id
                WHERE symbols_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
            rows = await cursor.fetchall()
            for r in rows:
                results.append(dict(r))
        except Exception as exc:  # noqa: BLE001
            logger.warning("FTS search error for query '%s': %s", query, exc)
        return results

    # ── Statistics ────────────────────────────────────────────────────────

    async def get_project_stats(self) -> dict:
        """Return aggregate statistics about the indexed repository.

        Returns:
            Dict with keys: ``total_files``, ``total_symbols``,
            ``languages`` (dict), ``last_indexed``.
        """
        conn = await self._db.get_connection()

        cursor = await conn.execute("SELECT COUNT(*) AS cnt FROM files")
        total_files: int = (await cursor.fetchone())["cnt"]

        cursor = await conn.execute("SELECT COUNT(*) AS cnt FROM symbols")
        total_symbols: int = (await cursor.fetchone())["cnt"]

        cursor = await conn.execute(
            "SELECT language, COUNT(*) AS cnt FROM files GROUP BY language ORDER BY cnt DESC"
        )
        lang_rows = await cursor.fetchall()
        languages = {r["language"] or "unknown": r["cnt"] for r in lang_rows}

        cursor = await conn.execute("SELECT MAX(last_indexed) AS ts FROM files")
        last_row = await cursor.fetchone()
        last_indexed = last_row["ts"] if last_row else None

        return {
            "total_files": total_files,
            "total_symbols": total_symbols,
            "languages": languages,
            "last_indexed": last_indexed,
        }

    async def get_recently_changed(self, limit: int = 20) -> list[FileInfo]:
        """Return the most recently indexed files.

        Args:
            limit: Maximum number of results.

        Returns:
            List of :class:`~codememory.models.FileInfo` sorted by recency.
        """
        conn = await self._db.get_connection()
        cursor = await conn.execute(
            """
            SELECT path, language, hash, last_indexed, size_bytes, summary
            FROM files
            ORDER BY last_indexed DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            FileInfo(
                path=r["path"],
                language=r["language"],
                hash=r["hash"],
                last_scanned=r["last_indexed"],
                size_bytes=r["size_bytes"],
                summary=r["summary"],
            )
            for r in rows
        ]
