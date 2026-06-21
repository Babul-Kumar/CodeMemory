"""Scanner-internal dataclasses (extend main models where needed)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedFile:
    """Lightweight dataclass used internally by scanner components.

    Mirrors the fields of :class:`codememory.models.ScanResult` but uses
    plain dataclasses for performance during the scan hot-path.
    """

    path: Path
    language: str | None = None
    size_bytes: int = 0
    content_hash: str | None = None
    symbols: list[dict] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    error: str | None = None
