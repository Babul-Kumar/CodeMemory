"""Unit tests for the watch/incremental scanning layer (watcher package)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import numpy as np
import pytest

from codememory.watcher.incremental_scanner import IncrementalScanner
from codememory.watcher.file_watcher import CodeFileWatcher


class MockEncoder:
    """Mock EmbeddingEncoder that returns dummy vectors without loading FastEmbed."""
    
    async def load(self) -> None:
        pass
        
    def encode(self, texts: list[str]) -> list[np.ndarray]:
        return [np.zeros(384, dtype=np.float32) for _ in texts]
        
    async def encode_and_store(self, file_path: str, text: str, db: any) -> None:
        pass


@pytest.mark.asyncio
async def test_incremental_scanner_reindex(tmp_path: Path, db) -> None:
    """reindex_file should scan, upsert, and update graph and intelligence layers."""
    # Write a test python file
    test_file = tmp_path / "hello.py"
    test_file.write_text("def greet(name: str) -> None:\n    print(f'Hello, {name}')\n")

    # Set up watcher DB directory structure
    (tmp_path / ".ai").mkdir(exist_ok=True)

    encoder = MockEncoder()
    scanner = IncrementalScanner(tmp_path, db, encoder)  # type: ignore[arg-type]

    # Run reindex
    await scanner.reindex_file(test_file)

    # Verify file is in main DB using absolute path
    file_info = await db.get_file(str(test_file))
    assert file_info is not None
    assert file_info.path == str(test_file)
    assert file_info.language == "python"

    # Verify symbols in main DB
    conn = await db.get_connection()
    cursor = await conn.execute("SELECT id FROM files WHERE path = ?", (str(test_file),))
    row = await cursor.fetchone()
    assert row is not None
    file_id = row["id"]
    cursor = await conn.execute("SELECT name FROM symbols WHERE file_id = ?", (file_id,))
    symbols = {r["name"] for r in await cursor.fetchall()}
    assert "greet" in symbols

    # Verify intelligence.db was updated
    intel_db_path = tmp_path / ".ai" / "intelligence.db"
    assert intel_db_path.exists()
    
    import sqlite3
    conn2 = sqlite3.connect(intel_db_path)
    conn2.row_factory = sqlite3.Row
    cursor2 = conn2.execute("SELECT * FROM components WHERE path = 'hello.py'")
    comps = [dict(r) for r in cursor2.fetchall()]
    conn2.close()

    assert len(comps) >= 2
    names = {c["name"] for c in comps}
    assert "hello.py" in names
    assert "greet" in names


@pytest.mark.asyncio
async def test_incremental_scanner_remove(tmp_path: Path, db) -> None:
    """remove_file should delete records from DB, graph, and intelligence databases."""
    # Setup test DB directory structure
    (tmp_path / ".ai").mkdir(exist_ok=True)
    
    # 1. Insert file into main DB using absolute path
    from codememory.storage.repository import CodeRepository
    from codememory.models import FileInfo
    
    repo = CodeRepository(tmp_path, db)
    test_file = tmp_path / "hello.py"
    fi = FileInfo(
        path=str(test_file),
        language="python",
        content="def hello(): pass\n",
        hash="hash123",
        size_bytes=18,
        symbols=[]
    )
    await repo.upsert_file(fi)
    
    # Verify it exists first
    assert await db.get_file(str(test_file)) is not None

    encoder = MockEncoder()
    scanner = IncrementalScanner(tmp_path, db, encoder)  # type: ignore[arg-type]

    # Pre-populate intelligence DB
    from codememory.intelligence.report_generator import initialize_db
    intel_db_path = tmp_path / ".ai" / "intelligence.db"
    initialize_db(intel_db_path)
    
    import sqlite3
    conn = sqlite3.connect(intel_db_path)
    conn.execute("INSERT INTO components (path, name, kind) VALUES ('hello.py', 'hello.py', 'file')")
    conn.commit()
    conn.close()

    # Run remove_file
    await scanner.remove_file(test_file)

    # Verify deleted from main DB
    assert await db.get_file(str(test_file)) is None

    # Verify deleted from intelligence DB
    conn = sqlite3.connect(intel_db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM components WHERE path = 'hello.py'")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 0


@pytest.mark.asyncio
async def test_incremental_scanner_process_change(tmp_path: Path, db) -> None:
    """process_change should route created/modified and deleted events correctly."""
    encoder = MockEncoder()
    scanner = IncrementalScanner(tmp_path, db, encoder)  # type: ignore[arg-type]

    scanner.reindex_file = AsyncMock()  # type: ignore[method-assign]
    scanner.remove_file = AsyncMock()  # type: ignore[method-assign]

    # Created/Modified route to reindex_file
    await scanner.process_change("created", tmp_path / "a.py")
    scanner.reindex_file.assert_awaited_once_with(tmp_path / "a.py")
    
    scanner.reindex_file.reset_mock()
    await scanner.process_change("modified", tmp_path / "a.py")
    scanner.reindex_file.assert_awaited_once_with(tmp_path / "a.py")

    # Deleted routes to remove_file
    await scanner.process_change("deleted", tmp_path / "a.py")
    scanner.remove_file.assert_awaited_once_with(tmp_path / "a.py")


@pytest.mark.asyncio
async def test_code_file_watcher_lifecycle(tmp_path: Path) -> None:
    """CodeFileWatcher start and stop should create and join observer instances."""
    on_change = MagicMock()
    watcher = CodeFileWatcher(tmp_path, on_change)

    watcher.start()
    assert watcher._observer is not None
    assert watcher._observer.is_alive()

    watcher.stop()
    assert watcher._observer is None
