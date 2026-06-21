"""Unit tests for the codebase intelligence layer (report_generator.py)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from codememory.intelligence.report_generator import (
    CodebaseIntelligenceCompiler,
    initialize_db,
)


@pytest.fixture
def test_ai_dir(tmp_path: Path) -> Path:
    """Fixture returning a temporary .ai directory."""
    ai_dir = tmp_path / ".ai"
    ai_dir.mkdir(exist_ok=True)
    return ai_dir


def test_initialize_db(test_ai_dir: Path) -> None:
    """initialize_db should create all intelligence tables in SQLite."""
    db_path = test_ai_dir / "intelligence.db"
    initialize_db(db_path)

    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query sqlite_master to verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    expected_tables = {
        "components",
        "relationships",
        "features",
        "agent_memory",
        "context_packs",
        "leftover_tasks",
    }
    for t in expected_tables:
        assert t in tables, f"Expected table '{t}' to be created"

    conn.close()


def test_compile_from_codememory(tmp_path: Path, test_ai_dir: Path) -> None:
    """compile_from_codememory should populate components and relationships."""
    # Create fake codememory scanner database
    cm_db_path = tmp_path / "codememory.db"
    conn = sqlite3.connect(cm_db_path)
    conn.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            language TEXT,
            size_bytes INTEGER,
            summary TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE symbols (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            name TEXT,
            kind TEXT,
            signature TEXT,
            docstring TEXT,
            start_line INTEGER,
            end_line INTEGER,
            parent_id INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE relationships (
            id INTEGER PRIMARY KEY,
            from_file_id INTEGER,
            to_file_id INTEGER,
            from_symbol TEXT,
            to_symbol TEXT,
            rel_type TEXT
        )
        """
    )

    # Insert fake file and symbols
    conn.execute(
        "INSERT INTO files (id, path, language, size_bytes, summary) VALUES (?, ?, ?, ?, ?)",
        (1, "models/user.py", "python", 120, "User models summary"),
    )
    conn.execute(
        "INSERT INTO symbols (id, file_id, name, kind, signature, docstring, start_line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 1, "User", "class", "class User:", "User representation", 1, 10),
    )
    conn.execute(
        "INSERT INTO relationships (from_file_id, to_file_id, from_symbol, to_symbol, rel_type) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, 1, "User", None, "imports"),
    )
    conn.commit()
    conn.close()

    # Run compiler
    compiler = CodebaseIntelligenceCompiler(tmp_path)
    # Redirect compiler paths to tmp_path
    compiler.ai_dir = test_ai_dir
    compiler.intel_db_path = test_ai_dir / "intelligence.db"
    initialize_db(compiler.intel_db_path)

    # Re-run compile
    compiler.compile_from_codememory(cm_db_path, tmp_path / "graph.json")

    # Verify intelligence.db was populated
    intel_conn = sqlite3.connect(compiler.intel_db_path)
    intel_conn.row_factory = sqlite3.Row

    # Verify components
    cursor = intel_conn.execute("SELECT * FROM components")
    comps = [dict(r) for r in cursor.fetchall()]
    assert len(comps) >= 2  # file and symbol

    file_comp = next((c for c in comps if c["kind"] == "file"), None)
    assert file_comp is not None
    assert file_comp["path"] == "models/user.py"
    assert file_comp["name"] == "user.py"

    symbol_comp = next((c for c in comps if c["kind"] == "class"), None)
    assert symbol_comp is not None
    assert symbol_comp["name"] == "User"

    # Verify features table exists and is populated
    cursor = intel_conn.execute("SELECT * FROM features")
    features = [dict(r) for r in cursor.fetchall()]
    assert len(features) > 0
    # CI/CD and Docker must be "Implemented"
    docker_feat = next((f for f in features if f["name"] == "Docker Configuration"), None)
    assert docker_feat is not None
    assert docker_feat["status"] == "Implemented"

    intel_conn.close()


def test_sync_leftover_tasks_noise_filtering(tmp_path: Path, test_ai_dir: Path) -> None:
    """sync_leftover_tasks should filter out non-code files (e.g. .md, .toml) from test gap analysis."""
    compiler = CodebaseIntelligenceCompiler(tmp_path)
    compiler.ai_dir = test_ai_dir
    compiler.intel_db_path = test_ai_dir / "intelligence.db"
    initialize_db(compiler.intel_db_path)

    conn = sqlite3.connect(compiler.intel_db_path)
    # Insert code and non-code files
    conn.execute(
        "INSERT INTO components (path, name, kind, status) VALUES (?, ?, ?, ?)",
        ("README.md", "README.md", "file", "Implemented"),
    )
    conn.execute(
        "INSERT INTO components (path, name, kind, status) VALUES (?, ?, ?, ?)",
        ("pyproject.toml", "pyproject.toml", "file", "Implemented"),
    )
    conn.execute(
        "INSERT INTO components (path, name, kind, status) VALUES (?, ?, ?, ?)",
        ("codememory/core.py", "core.py", "file", "Implemented"),
    )
    conn.commit()
    conn.close()

    compiler.sync_leftover_tasks()

    # Verify leftover_tasks
    conn = sqlite3.connect(compiler.intel_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM leftover_tasks WHERE category = 'testing'")
    tasks = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # The code file core.py should be a test gap, but README.md and pyproject.toml should be filtered out
    task_names = [t["task_name"] for t in tasks]
    assert any("core.py" in name for name in task_names), "core.py should trigger a test gap task"
    assert not any("README.md" in name for name in task_names), "README.md should not trigger a test gap task"
    assert not any("pyproject.toml" in name for name in task_names), "pyproject.toml should not trigger a test gap task"


def test_update_file_incremental(tmp_path: Path, test_ai_dir: Path) -> None:
    """update_file_incremental should update single file components on file events."""
    compiler = CodebaseIntelligenceCompiler(tmp_path)
    compiler.ai_dir = test_ai_dir
    compiler.intel_db_path = test_ai_dir / "intelligence.db"
    initialize_db(compiler.intel_db_path)

    # Write a dummy python file
    test_file = tmp_path / "dummy.py"
    test_file.write_text("class DummyClass:\n    pass\n\ndef dummy_func():\n    pass\n")

    compiler.update_file_incremental(test_file, deleted=False)

    conn = sqlite3.connect(compiler.intel_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM components WHERE path = 'dummy.py'")
    comps = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Should find file, class, and function
    kinds = {c["kind"] for c in comps}
    names = {c["name"] for c in comps}
    assert "file" in kinds
    assert "class" in kinds
    assert "function" in kinds
    assert "DummyClass" in names
    assert "dummy_func" in names

    # Delete test_file
    compiler.update_file_incremental(test_file, deleted=True)

    conn = sqlite3.connect(compiler.intel_db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM components WHERE path = 'dummy.py'")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 0


def test_agent_memory_and_views(tmp_path: Path, test_ai_dir: Path) -> None:
    """record_decision and record_task should populate agent memory and export views."""
    compiler = CodebaseIntelligenceCompiler(tmp_path)
    compiler.ai_dir = test_ai_dir
    compiler.intel_db_path = test_ai_dir / "intelligence.db"
    initialize_db(compiler.intel_db_path)

    # Record decision
    compiler.record_decision("Test Decision", "We decided to test the memory system", ["dummy.py"])
    # Record task
    compiler.record_task("Test Task Completed", "Tests verified successfully", ["dummy.py"])

    # Verify database
    conn = sqlite3.connect(compiler.intel_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM agent_memory")
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    assert len(records) == 2
    types = {r["type"] for r in records}
    assert "decision" in types
    assert "task_history" in types

    # Verify JSON files were exported
    dec_json = test_ai_dir / "agent_memory" / "decisions.json"
    task_json = test_ai_dir / "agent_memory" / "task_history.json"
    adr_md = test_ai_dir / "agent_memory" / "architecture_decisions.md"

    assert dec_json.exists()
    assert task_json.exists()
    assert adr_md.exists()

    with open(dec_json, encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["title"] == "Test Decision"


def test_automatic_architectural_decision_recording(tmp_path: Path, test_ai_dir: Path) -> None:
    """compile_from_codememory should detect and record added files/classes if a previous database state exists."""
    # 1. Create source db
    cm_db_path = tmp_path / "codememory.db"
    conn = sqlite3.connect(cm_db_path)
    conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, language TEXT, size_bytes INTEGER, summary TEXT)")
    conn.execute("CREATE TABLE symbols (id INTEGER PRIMARY KEY, file_id INTEGER, name TEXT, kind TEXT, signature TEXT, docstring TEXT, start_line INTEGER, end_line INTEGER, parent_id INTEGER)")
    conn.execute("CREATE TABLE relationships (id INTEGER PRIMARY KEY, from_file_id INTEGER, to_file_id INTEGER, from_symbol TEXT, to_symbol TEXT, rel_type TEXT)")
    
    # Base state: seed a file
    conn.execute("INSERT INTO files (id, path, language, size_bytes, summary) VALUES (999, 'base_file.py', 'python', 50, 'Base file')")
    conn.commit()
    conn.close()

    compiler = CodebaseIntelligenceCompiler(tmp_path)
    compiler.ai_dir = test_ai_dir
    compiler.intel_db_path = test_ai_dir / "intelligence.db"
    initialize_db(compiler.intel_db_path)

    # First compile (should not record anything because there was no previous files in components)
    compiler.compile_from_codememory(cm_db_path, tmp_path / "graph.json")

    conn = sqlite3.connect(compiler.intel_db_path)
    count = conn.execute("SELECT COUNT(*) FROM agent_memory").fetchone()[0]
    conn.close()
    assert count == 0

    # 2. Add files and classes to source DB
    conn = sqlite3.connect(cm_db_path)
    conn.execute("INSERT INTO files (id, path, language, size_bytes, summary) VALUES (1, 'new_file.py', 'python', 100, 'New file')")
    conn.execute("INSERT INTO symbols (id, file_id, name, kind, start_line, end_line) VALUES (1, 1, 'NewClass', 'class', 1, 5)")
    conn.commit()
    conn.close()

    # Re-compile (should detect new_file.py and NewClass and log them)
    compiler.compile_from_codememory(cm_db_path, tmp_path / "graph.json")

    conn = sqlite3.connect(compiler.intel_db_path)
    conn.row_factory = sqlite3.Row
    records = [dict(r) for r in conn.execute("SELECT * FROM agent_memory WHERE type = 'decision'").fetchall()]
    conn.close()

    assert len(records) >= 2
    titles = {r["title"] for r in records}
    assert "Added file: new_file.py" in titles
    assert "New Class: NewClass" in titles
