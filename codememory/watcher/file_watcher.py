"""File watcher for CodeMemory using the *watchdog* library.

Monitors a repository directory for file-system events, debounces rapid
bursts of changes, and enqueues normalised events into an :mod:`asyncio`
queue for consumption by :class:`~codememory.watcher.incremental_scanner.IncrementalScanner`.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from codememory.constants import CODE_EXTENSIONS  # set of extensions e.g. {".py", ".js", …}

logger = logging.getLogger(__name__)

# Fallback extension set in case the constant is not yet available.
_FALLBACK_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
        ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".swift", ".kt",
        ".cs", ".scala", ".lua", ".r", ".jl", ".ex", ".exs",
        ".md", ".toml", ".yaml", ".yml", ".json",
    }
)

_DEBOUNCE_SECONDS: float = 0.5


class _DebounceHandler(FileSystemEventHandler):
    """Watchdog event handler that debounces and filters file-system events."""

    def __init__(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        loop: asyncio.AbstractEventLoop,
        extensions: frozenset[str],
    ) -> None:
        super().__init__()
        self._queue = queue
        self._loop = loop
        self._extensions = extensions
        self._pending: dict[str, tuple[str, float]] = {}  # path → (event_type, timestamp)
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    # Watchdog callbacks
    # ------------------------------------------------------------------

    def on_modified(self, event: FileSystemEvent) -> None:  # noqa: D102
        if not event.is_directory:
            self._register(event.src_path, "modified")

    def on_created(self, event: FileSystemEvent) -> None:  # noqa: D102
        if not event.is_directory:
            self._register(event.src_path, "created")

    def on_deleted(self, event: FileSystemEvent) -> None:  # noqa: D102
        if not event.is_directory:
            self._register(event.src_path, "deleted")

    def on_moved(self, event: FileMovedEvent) -> None:  # noqa: D102
        """Handle Windows rename-on-save behaviour."""
        if not event.is_directory:
            # Source file effectively deleted, destination is new/modified.
            self._register(event.src_path, "deleted")
            self._register(event.dest_path, "created")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_code_file(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._extensions

    def _register(self, path: str, event_type: str) -> None:
        if not self._is_code_file(path):
            return
        with self._lock:
            self._pending[path] = (event_type, time.monotonic())
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            events = dict(self._pending)
            self._pending.clear()
            self._timer = None

        for path, (event_type, _) in events.items():
            payload = {"event_type": event_type, "path": path}
            logger.debug("Queuing event: %s %s", event_type, path)
            # Thread-safe put into the asyncio queue
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, payload)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to enqueue event: %s", exc)


class CodeFileWatcher:
    """High-level file watcher that integrates watchdog with asyncio.

    Usage::

        async def handle(event_type: str, path: str) -> None:
            print(event_type, path)

        watcher = CodeFileWatcher(Path("/my/repo"), on_change=handle)
        watcher.start()
        # … later …
        watcher.stop()

    The *on_change* callable receives ``(event_type: str, path: str)`` where
    *event_type* is one of ``"created"``, ``"modified"``, ``"deleted"``.
    """

    def __init__(
        self,
        repo_path: Path,
        on_change: Callable[[str, str], Any],
    ) -> None:
        """Initialise the watcher.

        Args:
            repo_path: Root directory of the repository to watch.
            on_change:  Async or sync callable invoked with
                        ``(event_type, absolute_path)`` for each debounced event.
        """
        self._repo_path = repo_path
        self._on_change = on_change
        self._observer: Observer | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        try:
            extensions = frozenset(CODE_EXTENSIONS)
        except Exception:  # noqa: BLE001
            extensions = _FALLBACK_EXTENSIONS

        self._extensions = extensions

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the watchdog observer and asyncio consumer task."""
        if self._observer is not None:
            logger.warning("CodeFileWatcher already started.")
            return

        loop = asyncio.get_event_loop()
        handler = _DebounceHandler(self._queue, loop, self._extensions)

        self._observer = Observer()
        self._observer.schedule(handler, str(self._repo_path), recursive=True)
        self._observer.start()
        logger.info("Watching %s for changes …", self._repo_path)

        self._consumer_task = loop.create_task(self._consume())

    def stop(self) -> None:
        """Stop the watcher and cancel the consumer task."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("CodeFileWatcher stopped.")

        if self._consumer_task is not None and not self._consumer_task.done():
            self._consumer_task.cancel()
            self._consumer_task = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _consume(self) -> None:
        """Drain the event queue and call *on_change* for each event."""
        while True:
            payload = await self._queue.get()
            event_type: str = payload["event_type"]
            path: str = payload["path"]
            try:
                if asyncio.iscoroutinefunction(self._on_change):
                    await self._on_change(event_type, path)  # type: ignore[arg-type]
                else:
                    self._on_change(event_type, path)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in on_change handler: %s", exc)
            finally:
                self._queue.task_done()
