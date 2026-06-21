"""Tests for the storage layer (Database + CodeRepository + ChangeDetector)."""
from __future__ import annotations

from pathlib import Path

import pytest

from codememory.models import FileInfo, SymbolInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file_info(path: str = "utils/helpers.py", language: str = "python") -> FileInfo:
    return FileInfo(
        path=path,
        language=language,
        content="def greet(name: str) -> str:\n    return f'Hello, {name}!'\n",
        hash="abc123",
        symbols=[
            SymbolInfo(name="greet", kind="function", line=1, docstring="Greet a user.")
        ],
        size=60,
        last_modified=1_700_000_000.0,
    )


# ---------------------------------------------------------------------------
# Database — upsert_file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_file_creates_record(db) -> None:  # type: ignore[no-untyped-def]
    """upsert_file should persist a FileInfo to the database."""
    from codememory.storage.repository import CodeRepository

    repo = CodeRepository(Path("/fake/repo"), db)
    fi = _make_file_info()
    await repo.upsert_file(fi)

    retrieved = await db.get_file(fi.path)
    assert retrieved is not None
    assert retrieved.path == fi.path
    assert retrieved.language == "python"


@pytest.mark.asyncio
async def test_upsert_file_updates_existing(db) -> None:  # type: ignore[no-untyped-def]
    """A second upsert should overwrite the existing record."""
    from codememory.storage.repository import CodeRepository

    repo = CodeRepository(Path("/fake/repo"), db)
    fi = _make_file_info()
    await repo.upsert_file(fi)

    # Update hash to simulate a modified file
    fi2 = _make_file_info()
    fi2.hash = "def456"
    fi2.content = "# updated\n"
    await repo.upsert_file(fi2)

    retrieved = await db.get_file(fi.path)
    assert retrieved is not None
    assert retrieved.hash == "def456"


# ---------------------------------------------------------------------------
# FTS search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fts_search_returns_matching_files(db) -> None:  # type: ignore[no-untyped-def]
    """Full-text search should find files whose content contains the query."""
    from codememory.storage.repository import CodeRepository

    repo = CodeRepository(Path("/fake/repo"), db)
    fi = _make_file_info()
    await repo.upsert_file(fi)

    results = await db.fts_search("greet", limit=10)
    paths = [r["file_path"] for r in results]
    assert fi.path in paths, f"Expected {fi.path!r} in FTS results, got: {paths}"


@pytest.mark.asyncio
async def test_fts_search_no_match(db) -> None:  # type: ignore[no-untyped-def]
    """FTS search should return an empty list for queries with no matches."""
    from codememory.storage.repository import CodeRepository

    repo = CodeRepository(Path("/fake/repo"), db)
    fi = _make_file_info()
    await repo.upsert_file(fi)

    results = await db.fts_search("XXXXXXXXNOTFOUND", limit=10)
    assert results == []


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_detection_new_file(tmp_path: Path, db) -> None:  # type: ignore[no-untyped-def]
    """A file not yet tracked should be identified as new."""
    from codememory.storage.repository import CodeRepository
    from codememory.watcher.change_detector import ChangeDetector

    repo = CodeRepository(tmp_path, db)
    new_file = tmp_path / "new_module.py"
    new_file.write_text("x = 1\n")

    detector = ChangeDetector()
    changed, deleted = await detector.get_changed_files(repo, [new_file])

    assert new_file in changed
    assert deleted == []


@pytest.mark.asyncio
async def test_change_detection_modified_file(tmp_path: Path, db) -> None:  # type: ignore[no-untyped-def]
    """A file whose hash changed should appear in the changed list."""
    from codememory.storage.repository import CodeRepository
    from codememory.watcher.change_detector import ChangeDetector

    repo = CodeRepository(tmp_path, db)
    existing = tmp_path / "existing.py"
    existing.write_text("a = 1\n")

    # Store the original hash
    detector = ChangeDetector()
    original_hash = detector.compute_hash(existing)
    fi = FileInfo(
        path="existing.py",
        language="python",
        content="a = 1\n",
        hash=original_hash,
        symbols=[],
        size=6,
        last_modified=0.0,
    )
    await repo.upsert_file(fi)

    # Modify the file
    existing.write_text("a = 2  # changed\n")

    changed, deleted = await detector.get_changed_files(repo, [existing])
    assert existing in changed


@pytest.mark.asyncio
async def test_change_detection_deleted_file(tmp_path: Path, db) -> None:  # type: ignore[no-untyped-def]
    """A file tracked in DB but missing on disk should appear in deleted."""
    from codememory.storage.repository import CodeRepository
    from codememory.watcher.change_detector import ChangeDetector

    repo = CodeRepository(tmp_path, db)
    fi = FileInfo(
        path="gone.py",
        language="python",
        content="",
        hash="somehash",
        symbols=[],
        size=0,
        last_modified=0.0,
    )
    await repo.upsert_file(fi)

    detector = ChangeDetector()
    # Pass empty current file list — the file has been deleted
    changed, deleted = await detector.get_changed_files(repo, [])
    assert "gone.py" in deleted


@pytest.mark.asyncio
async def test_compute_hash_deterministic(tmp_path: Path) -> None:
    """compute_hash should return the same digest for unchanged content."""
    from codememory.watcher.change_detector import ChangeDetector

    f = tmp_path / "stable.py"
    f.write_text("hello world\n")
    detector = ChangeDetector()
    h1 = detector.compute_hash(f)
    h2 = detector.compute_hash(f)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length
