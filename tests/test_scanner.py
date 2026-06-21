"""Tests for the RepositoryScanner (Phase 6-10 perspective)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_file_walking_respects_gitignore(temp_repo: Path) -> None:
    """Files matched by .gitignore should not be included in scan results."""
    from codememory.scanner import RepositoryScanner

    scanner = RepositoryScanner(temp_repo)
    result = await scanner.scan()

    discovered_paths = [fi.path for fi in result.files]

    # .venv directory must be excluded
    venv_files = [p for p in discovered_paths if ".venv" in p]
    assert venv_files == [], f"Expected .venv to be ignored, got: {venv_files}"

    # Main source files must be present
    expected_files = {"main.py", "utils/helpers.py", "models/user.py"}
    discovered_names = {Path(p).name for p in discovered_paths}
    for expected in expected_files:
        base = Path(expected).name
        assert base in discovered_names, f"Expected {expected} to be scanned"


@pytest.mark.asyncio
async def test_language_detection_py(temp_repo: Path) -> None:
    """Python files should be detected as 'python'."""
    from codememory.scanner import RepositoryScanner

    scanner = RepositoryScanner(temp_repo)
    result = await scanner.scan()

    py_files = [fi for fi in result.files if fi.path.endswith(".py")]
    assert py_files, "Should find at least one Python file"
    for fi in py_files:
        assert fi.language == "python", f"Expected 'python', got {fi.language!r} for {fi.path}"


@pytest.mark.asyncio
async def test_python_extractor_finds_classes(temp_repo: Path) -> None:
    """Python extractor should find the User class in models/user.py."""
    from codememory.scanner import RepositoryScanner

    scanner = RepositoryScanner(temp_repo)
    result = await scanner.scan()

    user_file = next(
        (fi for fi in result.files if "user.py" in fi.path),
        None,
    )
    assert user_file is not None, "user.py should be in scan results"
    symbol_names = [s.name for s in (user_file.symbols or [])]
    assert "User" in symbol_names, f"Expected 'User' class in symbols, got: {symbol_names}"


@pytest.mark.asyncio
async def test_python_extractor_finds_functions(temp_repo: Path) -> None:
    """Python extractor should find functions in utils/helpers.py."""
    from codememory.scanner import RepositoryScanner

    scanner = RepositoryScanner(temp_repo)
    result = await scanner.scan()

    helpers_file = next(
        (fi for fi in result.files if "helpers.py" in fi.path),
        None,
    )
    assert helpers_file is not None, "helpers.py should be in scan results"
    symbol_names = [s.name for s in (helpers_file.symbols or [])]
    assert "greet" in symbol_names, f"Expected 'greet' function, got: {symbol_names}"
    assert "add" in symbol_names, f"Expected 'add' function, got: {symbol_names}"


@pytest.mark.asyncio
async def test_scan_result_has_language_breakdown(temp_repo: Path) -> None:
    """ScanResult.languages should map language → file count."""
    from codememory.scanner import RepositoryScanner

    scanner = RepositoryScanner(temp_repo)
    result = await scanner.scan()

    assert result.languages is not None
    assert "python" in result.languages
    assert result.languages["python"] >= 4  # main, helpers, user, test_sample, etc.
