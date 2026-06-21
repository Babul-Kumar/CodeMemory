"""Shared pytest fixtures for the CodeMemory test suite."""
from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Event loop (module-scoped so fixtures can be async)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Provide a module-scoped asyncio event loop."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Temporary fake Python repository
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def temp_repo(tmp_path_factory) -> Path:  # type: ignore[no-untyped-def]
    """Create a minimal fake Python repository for testing.

    Layout::

        fake_repo/
        ├── .gitignore
        ├── main.py
        ├── utils/
        │   ├── __init__.py
        │   └── helpers.py
        ├── models/
        │   ├── __init__.py
        │   └── user.py
        └── tests/
            └── test_sample.py

    Returns:
        :class:`Path` pointing to the root of the fake repo.
    """
    root: Path = tmp_path_factory.mktemp("fake_repo")

    # .gitignore
    (root / ".gitignore").write_text(
        textwrap.dedent("""\
            __pycache__/
            *.pyc
            .venv/
            dist/
            *.egg-info/
            node_modules/
            .DS_Store
        """)
    )

    # main.py
    (root / "main.py").write_text(
        textwrap.dedent("""\
            \"\"\"Entry point for the fake application.\"\"\"
            from utils.helpers import greet
            from models.user import User


            def main() -> None:
                user = User(name="Alice")
                print(greet(user.name))


            if __name__ == "__main__":
                main()
        """)
    )

    # utils/__init__.py
    (root / "utils").mkdir()
    (root / "utils" / "__init__.py").write_text('"""Utils package."""\n')

    # utils/helpers.py
    (root / "utils" / "helpers.py").write_text(
        textwrap.dedent("""\
            \"\"\"Utility helper functions.\"\"\"
            from __future__ import annotations


            def greet(name: str) -> str:
                \"\"\"Return a greeting string for *name*.\"\"\"
                return f"Hello, {name}!"


            def add(a: int, b: int) -> int:
                \"\"\"Return the sum of *a* and *b*.\"\"\"
                return a + b
        """)
    )

    # models/__init__.py
    (root / "models").mkdir()
    (root / "models" / "__init__.py").write_text('"""Models package."""\n')

    # models/user.py
    (root / "models" / "user.py").write_text(
        textwrap.dedent("""\
            \"\"\"User domain model.\"\"\"
            from __future__ import annotations
            from dataclasses import dataclass


            @dataclass
            class User:
                \"\"\"Represents an application user.\"\"\"
                name: str
                email: str = ""

                def display_name(self) -> str:
                    \"\"\"Return a formatted display name.\"\"\"
                    return self.name.title()

                @classmethod
                def from_dict(cls, data: dict) -> \"User\":
                    \"\"\"Construct a User from a plain dict.\"\"\"
                    return cls(name=data["name"], email=data.get("email", ""))
        """)
    )

    # tests/test_sample.py — inside repo so scanner sees it
    (root / "tests").mkdir()
    (root / "tests" / "test_sample.py").write_text(
        textwrap.dedent("""\
            \"\"\"Placeholder tests.\"\"\"
            from utils.helpers import greet


            def test_greet() -> None:
                assert greet("World") == "Hello, World!"
        """)
    )

    # Ignored directory — should NOT be scanned
    venv = root / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "site.py").write_text("# ignored\n")

    return root


# ---------------------------------------------------------------------------
# In-memory Database fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def db(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Provide a fresh in-memory SQLite :class:`Database` for each test.

    Yields:
        Connected :class:`~codememory.storage.database.Database` instance.
    """
    from codememory.storage.database import Database  # noqa: PLC0415

    db_path = tmp_path / "test.db"
    database = Database(db_path)
    await database.connect()
    yield database
    await database.disconnect()
