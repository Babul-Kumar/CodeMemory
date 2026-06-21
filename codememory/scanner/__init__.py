"""RepositoryScanner — orchestrates file walking, parsing, and extraction."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, AsyncIterator

from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn

from codememory.config import CodeMemoryConfig
from codememory.models import FileInfo, ScanResult
from codememory.scanner.extractors import generic_extractor
from codememory.scanner.file_walker import FileWalker
from codememory.scanner.language_detector import detect_language
from codememory.scanner.tree_sitter_parser import TreeSitterParser

logger = logging.getLogger(__name__)

# Map language -> extractor module
_EXTRACTOR_MAP: dict[str, str] = {
    "python": "codememory.scanner.extractors.python_extractor",
    "javascript": "codememory.scanner.extractors.javascript_extractor",
    "typescript": "codememory.scanner.extractors.typescript_extractor",
    "go": "codememory.scanner.extractors.go_extractor",
    "rust": "codememory.scanner.extractors.rust_extractor",
    "java": "codememory.scanner.extractors.java_extractor",
}


def _file_hash(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file's contents.

    Args:
        path: Absolute path to the file.

    Returns:
        64-character hex digest string.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_single(file_path: Path, parser: TreeSitterParser) -> ScanResult | None:
    """Parse and extract a single file synchronously (runs in thread pool).

    Args:
        file_path: Absolute path to the source file.
        parser:    Shared :class:`~codememory.scanner.tree_sitter_parser.TreeSitterParser`.

    Returns:
        A :class:`~codememory.models.ScanResult` or ``None`` on hard failure.
    """
    try:
        language = detect_language(file_path)
        source_bytes = file_path.read_bytes()
        content_hash = hashlib.sha256(source_bytes).hexdigest()
        size = len(source_bytes)

        extractor_module_name = _EXTRACTOR_MAP.get(language or "")
        result: ScanResult | None = None

        if extractor_module_name:
            tree = parser.parse_bytes(source_bytes, language)
            if tree is not None:
                import importlib
                extractor_mod = importlib.import_module(extractor_module_name)
                result = extractor_mod.extract(tree, source_bytes, file_path)
            else:
                # Tree-sitter parse failed; fall back
                result = generic_extractor.extract(source_bytes, file_path, language)
        else:
            result = generic_extractor.extract(source_bytes, file_path, language)

        if result is not None:
            result.file_info.hash = content_hash
            result.file_info.size_bytes = size
            result.file_info.language = language
            result.file_info.last_scanned = time.time()

        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to scan %s: %s", file_path, exc)
        return ScanResult(
            file_info=FileInfo(
                path=str(file_path),
                language=detect_language(file_path),
                size_bytes=0,
                last_scanned=time.time(),
            )
        )


class RepositoryScanner:
    """Coordinates parallel scanning of an entire repository.

    Attributes:
        repo_path: Absolute path to the repository root.
        config:    Active configuration.
    """

    def __init__(self, repo_path: Path, config: CodeMemoryConfig | None = None) -> None:
        """Initialise the scanner.

        Args:
            repo_path: Absolute path to the repository root.
            config:    Optional config; defaults are used if not provided.
        """
        self.repo_path = repo_path.resolve()
        self.config = config or CodeMemoryConfig()
        self._parser = TreeSitterParser()

    async def scan_repository(self) -> AsyncIterator[ScanResult]:
        """Yield :class:`~codememory.models.ScanResult` for each file in the repo.

        Files are walked by :class:`~codememory.scanner.file_walker.FileWalker`
        and parsed concurrently using a :class:`~concurrent.futures.ThreadPoolExecutor`.

        Yields:
            One :class:`~codememory.models.ScanResult` per accepted file.
        """
        walker = FileWalker(self.repo_path, self.config)
        file_list = list(walker.walk())
        total = len(file_list)
        logger.info("Found %d files to scan in %s", total, self.repo_path)

        loop = asyncio.get_running_loop()
        parser = self._parser

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Scanning files…", total=total)

            with ThreadPoolExecutor(max_workers=self.config.max_workers) as pool:
                futures = [
                    loop.run_in_executor(pool, _scan_single, fp, parser)
                    for fp in file_list
                ]
                for coro in asyncio.as_completed(futures):
                    result = await coro
                    progress.advance(task)
                    if result is not None:
                        yield result

    async def scan_file(self, file_path: Path) -> ScanResult | None:
        """Scan a single file asynchronously.

        Args:
            file_path: Absolute path to the file.

        Returns:
            A :class:`~codememory.models.ScanResult` or ``None``.
        """
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            return await loop.run_in_executor(pool, _scan_single, file_path, self._parser)

    async def scan(self) -> Any:
        """Run a full repository scan and return a summary object for compatibility."""
        from collections import Counter
        from typing import Any as TypAny

        files = []
        languages: Counter[str] = Counter()

        async for result in self.scan_repository():
            fi = result.file_info
            fi.symbols = result.symbols
            files.append(fi)
            if fi.language:
                languages[fi.language] += 1

        class ScanResultSummary:
            def __init__(self, files_list: list[Any], lang_breakdown: Counter[str]):
                self.files = files_list
                self.languages = dict(lang_breakdown)

        return ScanResultSummary(files, languages)

