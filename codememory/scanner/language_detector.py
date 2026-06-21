"""Language detection from file extensions and shebangs."""
from __future__ import annotations

import logging
from pathlib import Path

from codememory.constants import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# Shebang -> language mapping for extensionless scripts
_SHEBANG_MAP: dict[str, str] = {
    "python": "python",
    "python3": "python",
    "python2": "python",
    "node": "javascript",
    "nodejs": "javascript",
    "ruby": "ruby",
    "perl": "perl",
    "bash": "bash",
    "sh": "bash",
    "zsh": "bash",
    "php": "php",
    "lua": "lua",
    "r": "r",
    "rscript": "r",
}


def detect_language(file_path: Path) -> str | None:
    """Determine the programming language of a source file.

    Detection strategy:
    1. File extension lookup against :data:`~codememory.constants.SUPPORTED_LANGUAGES`.
    2. Shebang line inspection for extensionless files.

    Args:
        file_path: Path to the source file.

    Returns:
        A language name string (e.g. ``"python"``) or ``None`` if unknown.
    """
    ext = file_path.suffix.lower()
    if ext:
        language = SUPPORTED_LANGUAGES.get(ext)
        if language:
            return language

    # Attempt shebang detection for extensionless files or unknown extensions
    try:
        with file_path.open("rb") as fh:
            first_line = fh.readline(128).decode("utf-8", errors="ignore").strip()
    except OSError as exc:
        logger.debug("Could not read shebang from %s: %s", file_path, exc)
        return None

    if first_line.startswith("#!"):
        # Examples: #!/usr/bin/env python3, #!/bin/bash
        parts = first_line[2:].strip().split()
        if parts:
            interpreter = Path(parts[-1]).name.lower()
            return _SHEBANG_MAP.get(interpreter)

    return None
