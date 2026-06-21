"""Change detection for incremental repository scanning.

Computes SHA-256 hashes of files and compares them against stored values
in the database to find which files are new, modified, or deleted.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from codememory.storage.repository import CodeRepository

logger = logging.getLogger(__name__)


class ChangeDetector:
    """Detects file additions, modifications, and deletions via hash comparison."""

    # ---------------------------------------------------------------------------
    # Public helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Return the SHA-256 hex digest of *file_path*'s contents.

        Args:
            file_path: Absolute path to the file to hash.

        Returns:
            Lowercase hexadecimal SHA-256 digest string.

        Raises:
            OSError: If the file cannot be read.
        """
        sha256 = hashlib.sha256()
        with file_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65_536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    async def get_changed_files(
        self,
        repo: CodeRepository,
        file_paths: list[Path],
    ) -> tuple[list[Path], list[str]]:
        """Compare *file_paths* against the DB and return what changed.

        Iterates through every tracked file in the repository.  Files whose
        hash differs from the stored value (or that are not yet tracked) are
        collected as *changed_or_new*.  Files that exist in the DB but are
        absent from *file_paths* are collected as *deleted*.

        Args:
            repo:       Initialised :class:`CodeRepository` backed by the
                        project database.
            file_paths: Current list of file paths discovered on disk.

        Returns:
            A 2-tuple ``(changed_or_new_files, deleted_file_paths)`` where
            *changed_or_new_files* is a list of :class:`Path` objects and
            *deleted_file_paths* is a list of path strings (relative to the
            repo root, as stored in the DB).
        """
        # Build a mapping: relative-path-string → absolute Path for quick lookup
        current_map: dict[str, Path] = {}
        for fp in file_paths:
            try:
                rel = str(fp.relative_to(repo.root_path))
            except ValueError:
                rel = str(fp)
            current_map[rel] = fp

        # Fetch all files currently tracked in the database
        stored_files: dict[str, str] = await repo.get_all_file_hashes()  # rel_path → hash

        changed_or_new: list[Path] = []
        deleted: list[str] = []

        # ---- Detect modified / new files ----------------------------------------
        for rel_path, abs_path in current_map.items():
            try:
                current_hash = self.compute_hash(abs_path)
            except OSError as exc:
                logger.warning("Cannot hash %s: %s", abs_path, exc)
                continue

            stored_hash = stored_files.get(rel_path)
            if stored_hash is None:
                logger.debug("New file: %s", rel_path)
                changed_or_new.append(abs_path)
            elif stored_hash != current_hash:
                logger.debug("Modified file: %s", rel_path)
                changed_or_new.append(abs_path)

        # ---- Detect deleted files -----------------------------------------------
        for rel_path in stored_files:
            if rel_path not in current_map:
                logger.debug("Deleted file: %s", rel_path)
                deleted.append(rel_path)

        logger.info(
            "Change detection complete — %d changed/new, %d deleted",
            len(changed_or_new),
            len(deleted),
        )
        return changed_or_new, deleted
