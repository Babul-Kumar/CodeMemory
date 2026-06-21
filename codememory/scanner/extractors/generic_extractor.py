"""Generic fallback extractor for unsupported languages.

Uses simple regex / line-counting heuristics to produce a minimal
:class:`~codememory.models.ScanResult` without detailed symbol information.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from codememory.models import FileInfo, ScanResult, SymbolInfo

logger = logging.getLogger(__name__)

# Very rough heuristics: match function-like definitions across many languages
_FUNC_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*(?:def|func|function|fn|sub|procedure)\s+(\w+)\s*\(", re.MULTILINE),
    re.compile(r"^\s*(?:public|private|protected|static|async)?\s*(?:function|func|def)\s+(\w+)\s*\(", re.MULTILINE),
]

_CLASS_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*(?:class|struct|interface|enum)\s+(\w+)", re.MULTILINE),
]

_IMPORT_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*(?:import|require|include|use|from)\s+[\"']?([^\s\"';]+)", re.MULTILINE),
    re.compile(r"^\s*#\s*include\s+[\"<]([^\">\n]+)", re.MULTILINE),
]


def extract(source_bytes: bytes, file_path: Path, language: str | None = None) -> ScanResult:
    """Produce a minimal ScanResult using regex heuristics.

    This is the fallback extractor invoked when no tree-sitter grammar
    is available for the file's language.

    Args:
        source_bytes: Raw file content.
        file_path:    Absolute path to the file.
        language:     Detected language name (may be ``None``).

    Returns:
        A :class:`~codememory.models.ScanResult` with basic metadata.
    """
    path_str = str(file_path)
    symbols: list[SymbolInfo] = []
    imports: list[str] = []

    try:
        text = source_bytes.decode("utf-8", errors="replace")
        lines = text.splitlines()

        # ── Function-like patterns ─────────────────────────────────────────
        for pattern in _FUNC_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1)
                lineno = text[: match.start()].count("\n") + 1
                # Avoid duplicates
                if not any(s.name == name and s.start_line == lineno for s in symbols):
                    symbols.append(
                        SymbolInfo(
                            name=name,
                            kind="function",
                            file_path=path_str,
                            start_line=lineno,
                            end_line=lineno,
                            signature=match.group(0).strip(),
                        )
                    )

        # ── Class-like patterns ────────────────────────────────────────────
        for pattern in _CLASS_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1)
                lineno = text[: match.start()].count("\n") + 1
                if not any(s.name == name and s.start_line == lineno for s in symbols):
                    symbols.append(
                        SymbolInfo(
                            name=name,
                            kind="class",
                            file_path=path_str,
                            start_line=lineno,
                            end_line=lineno,
                            signature=match.group(0).strip(),
                        )
                    )

        # ── Import-like patterns ───────────────────────────────────────────
        for pattern in _IMPORT_PATTERNS:
            for match in pattern.finditer(text):
                mod = match.group(1).strip()
                if mod and mod not in imports:
                    imports.append(mod)

    except Exception as exc:  # noqa: BLE001
        logger.warning("Generic extraction failed for %s: %s", file_path, exc)

    file_info = FileInfo(
        path=path_str,
        language=language,
        size_bytes=len(source_bytes),
    )
    return ScanResult(file_info=file_info, symbols=symbols, imports=imports)
