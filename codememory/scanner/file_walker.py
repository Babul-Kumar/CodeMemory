"""File system walker that discovers source files for indexing."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import pathspec
from rich.progress import Progress, SpinnerColumn, TextColumn

from codememory.config import CodeMemoryConfig
from codememory.constants import BINARY_EXTENSIONS, IGNORED_DIRS, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    """Load ``.gitignore`` from the repository root.

    Args:
        root: Repository root directory.

    Returns:
        A compiled :class:`pathspec.PathSpec` or ``None`` if not present.
    """
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return None
    try:
        lines = gitignore_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except OSError as exc:
        logger.warning("Could not read .gitignore: %s", exc)
        return None


class FileWalker:
    """Recursively walks a repository and yields candidate source files.

    Respects ``.gitignore``, ``IGNORED_DIRS``, binary extension filters,
    configurable max file sizes, and user-defined include/ignore glob patterns.
    """

    def __init__(self, root_path: Path, config: CodeMemoryConfig) -> None:
        """Initialise the walker.

        Args:
            root_path: Absolute path to the repository root.
            config:    Active :class:`~codememory.config.CodeMemoryConfig`.
        """
        self.root_path = root_path.resolve()
        self.config = config
        self._gitignore = _load_gitignore(self.root_path)

        # Pre-compile user patterns
        self._ignored_spec: pathspec.PathSpec | None = (
            pathspec.PathSpec.from_lines("gitwildmatch", config.ignored_patterns)
            if config.ignored_patterns
            else None
        )
        self._include_spec: pathspec.PathSpec | None = (
            pathspec.PathSpec.from_lines("gitwildmatch", config.include_patterns)
            if config.include_patterns
            else None
        )

    def _is_ignored_dir(self, directory: Path) -> bool:
        """Return ``True`` if *directory* should be skipped entirely."""
        name = directory.name
        if name in IGNORED_DIRS or name.startswith("."):
            return True
        rel = str(directory.relative_to(self.root_path))
        if self._gitignore and self._gitignore.match_file(rel + "/"):
            return True
        if self._ignored_spec and self._ignored_spec.match_file(rel + "/"):
            return True
        return False

    def _is_accepted_file(self, file_path: Path) -> bool:
        """Return ``True`` if *file_path* should be yielded by :meth:`walk`."""
        # Binary extension check
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            return False

        # Size check
        try:
            size = file_path.stat().st_size
        except OSError:
            return False
        if size > self.config.max_file_size_bytes:
            logger.debug("Skipping large file (%d bytes): %s", size, file_path)
            return False

        rel = str(file_path.relative_to(self.root_path))

        # gitignore check
        if self._gitignore and self._gitignore.match_file(rel):
            return False

        # User-defined ignore patterns
        if self._ignored_spec and self._ignored_spec.match_file(rel):
            return False

        # Include patterns filter (whitelist)
        if self._include_spec and not self._include_spec.match_file(rel):
            return False

        return True

    def walk(self) -> Iterator[Path]:
        """Yield all accepted source files under ``root_path``.

        Shows a Rich spinner while scanning so the user knows progress is
        being made even for very large repositories.

        Yields:
            Absolute :class:`pathlib.Path` objects for each accepted file.
        """
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Scanning {task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task(str(self.root_path), total=None)

            def _recurse(directory: Path) -> Iterator[Path]:
                try:
                    entries = sorted(directory.iterdir())
                except PermissionError:
                    logger.warning("Permission denied: %s", directory)
                    return

                for entry in entries:
                    if entry.is_dir():
                        if not self._is_ignored_dir(entry):
                            yield from _recurse(entry)
                    elif entry.is_file():
                        if self._is_accepted_file(entry):
                            progress.update(task, description=entry.name)
                            yield entry

            yield from _recurse(self.root_path)
