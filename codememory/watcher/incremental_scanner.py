"""Incremental scanner for CodeMemory.

Orchestrates the change detection → re-scan → DB update → embedding
re-index loop triggered by file-system events from :class:`CodeFileWatcher`.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from codememory.embeddings.encoder import EmbeddingEncoder
from codememory.storage.database import Database
from codememory.storage.repository import CodeRepository
from codememory.watcher.change_detector import ChangeDetector
from codememory.watcher.file_watcher import CodeFileWatcher

logger = logging.getLogger(__name__)


class IncrementalScanner:
    """Process file-system events and keep the code-memory index up-to-date.

    This class glues together the :class:`CodeFileWatcher`, the
    :class:`~codememory.storage.repository.CodeRepository`, and the
    :class:`~codememory.embeddings.encoder.EmbeddingEncoder` to handle
    single-file changes efficiently without a full re-scan.
    """

    def __init__(
        self,
        repo_path: Path,
        db: Database,
        encoder: EmbeddingEncoder,
    ) -> None:
        """Initialise the incremental scanner.

        Args:
            repo_path: Root path of the monitored repository.
            db:        Open :class:`~codememory.storage.database.Database`
                       instance for the repository.
            encoder:   Embedding encoder used to update the vector index.
        """
        self._repo_path = repo_path
        self._db = db
        self._encoder = encoder
        self._repo: CodeRepository | None = None
        self._change_detector = ChangeDetector()
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._watcher: CodeFileWatcher | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_change(self, event_type: str, file_path: Path) -> None:
        """Dispatch a single file-system event to the appropriate handler.

        Args:
            event_type: One of ``"created"``, ``"modified"``, ``"deleted"``.
            file_path:  Absolute path to the affected file.
        """
        logger.debug("Processing %s event for %s", event_type, file_path)
        if event_type in ("created", "modified"):
            await self.reindex_file(file_path)
        elif event_type == "deleted":
            await self.remove_file(file_path)
        else:
            logger.warning("Unknown event type: %s", event_type)

    async def reindex_file(self, file_path: Path) -> None:
        """Re-scan *file_path*, update DB, embeddings, and graph edges.

        The method is a best-effort operation: individual failures are
        logged but do not propagate so the watch loop stays alive.

        Args:
            file_path: Absolute path to the file to re-index.
        """
        try:
            repo = await self._get_repo()

            # --- 1. Import the scanner lazily to avoid circular imports ----
            from codememory.scanner import RepositoryScanner  # noqa: PLC0415

            scanner = RepositoryScanner(self._repo_path)
            file_info = await scanner.scan_file(file_path)
            if file_info is None:
                logger.warning("Scanner returned None for %s; skipping.", file_path)
                return

            # --- 2. Persist to database ------------------------------------
            await repo.upsert_file(file_info)
            logger.info("DB updated for %s", file_path.name)

            # --- 3. Update embeddings --------------------------------------
            text = file_info.file_info.content or ""
            if text:
                await self._encoder.encode_and_store(
                    file_path=str(file_path),
                    text=text,
                    db=self._db,
                )
                logger.info("Embeddings updated for %s", file_path.name)

            # --- 4. Rebuild graph edges for this file ----------------------
            try:
                import networkx as nx  # noqa: PLC0415
                from codememory.graph.builder import GraphBuilder  # noqa: PLC0415
                from codememory.graph.serializer import GraphSerializer  # noqa: PLC0415
                from codememory.config import get_repo_data_dir  # noqa: PLC0415

                data_dir = get_repo_data_dir(self._repo_path)
                graph_path = data_dir / "graph.json"

                try:
                    G = GraphSerializer.load(graph_path)
                except FileNotFoundError:
                    G = nx.DiGraph()

                # Clean old nodes for this file
                rel_path = self._to_rel(file_path)
                file_nid = f"file:{rel_path}"
                if G.has_node(file_nid):
                    contain_symbols = [
                        v for u, v, d in G.out_edges(file_nid, data=True)
                        if d.get("edge_type") == "contains"
                    ]
                    G.remove_nodes_from(contain_symbols)
                    G.remove_node(file_nid)

                builder = GraphBuilder()
                builder.add_scan_result(G, file_info)
                GraphSerializer.save(G, graph_path)
                logger.info("Graph updated for %s", file_path.name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Graph update failed for %s: %s", file_path, exc)

            # --- 5. Update intelligence database incrementally -------------
            try:
                from codememory.intelligence.report_generator import CodebaseIntelligenceCompiler  # noqa: PLC0415
                compiler = CodebaseIntelligenceCompiler(self._repo_path)
                compiler.update_file_incremental(file_path, deleted=False)
                logger.info("Intelligence DB updated for %s", file_path.name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Intelligence DB update failed for %s: %s", file_path, exc)

        except Exception as exc:  # noqa: BLE001
            logger.error("reindex_file failed for %s: %s", file_path, exc)

    async def remove_file(self, file_path: Path) -> None:
        """Remove *file_path* from the DB and graph index.

        Args:
            file_path: Absolute path (or relative path string) of the
                       deleted file.
        """
        try:
            repo = await self._get_repo()
            rel_path = self._to_rel(file_path)
            await repo.delete_file(str(file_path))
            await repo.delete_file(rel_path)
            logger.info("Removed %s from DB", rel_path)

            # Remove from graph
            try:
                from codememory.graph.serializer import GraphSerializer  # noqa: PLC0415
                from codememory.config import get_repo_data_dir  # noqa: PLC0415

                data_dir = get_repo_data_dir(self._repo_path)
                graph_path = data_dir / "graph.json"

                if graph_path.exists():
                    G = GraphSerializer.load(graph_path)
                    file_nid = f"file:{rel_path}"
                    if G.has_node(file_nid):
                        contain_symbols = [
                            v for u, v, d in G.out_edges(file_nid, data=True)
                            if d.get("edge_type") == "contains"
                        ]
                        G.remove_nodes_from(contain_symbols)
                        G.remove_node(file_nid)
                    GraphSerializer.save(G, graph_path)
                    logger.info("Removed %s from graph", rel_path)
            except Exception as exc:  # noqa: BLE001
                logger.error("Graph removal failed for %s: %s", file_path, exc)

            # Remove from intelligence database incrementally
            try:
                from codememory.intelligence.report_generator import CodebaseIntelligenceCompiler  # noqa: PLC0415
                compiler = CodebaseIntelligenceCompiler(self._repo_path)
                compiler.update_file_incremental(file_path, deleted=True)
                logger.info("Removed %s from Intelligence DB", rel_path)
            except Exception as exc:  # noqa: BLE001
                logger.error("Intelligence DB removal failed for %s: %s", file_path, exc)

        except Exception as exc:  # noqa: BLE001
            logger.error("remove_file failed for %s: %s", file_path, exc)

    async def run_watch_loop(self, repo_path: Path) -> None:
        """Start the file watcher and process events until cancelled.

        This coroutine runs indefinitely (until the task is cancelled).
        It sets up a :class:`CodeFileWatcher` and drains the event queue,
        calling :meth:`process_change` for each debounced event.

        Args:
            repo_path: Root directory of the repository to watch.
        """
        self._repo_path = repo_path

        async def _enqueue(event_type: str, path: str) -> None:
            await self._event_queue.put({"event_type": event_type, "path": path})

        self._watcher = CodeFileWatcher(repo_path, on_change=_enqueue)
        self._watcher.start()
        logger.info("Incremental watch loop started for %s", repo_path)

        try:
            while True:
                payload = await self._event_queue.get()
                event_type: str = payload["event_type"]
                path_str: str = payload["path"]
                await self.process_change(event_type, Path(path_str))
                self._event_queue.task_done()
        except asyncio.CancelledError:
            logger.info("Watch loop cancelled.")
        finally:
            if self._watcher is not None:
                self._watcher.stop()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_repo(self) -> CodeRepository:
        if self._repo is None:
            self._repo = CodeRepository(self._repo_path, self._db)
        return self._repo

    def _to_rel(self, file_path: Path) -> str:
        try:
            return str(file_path.relative_to(self._repo_path))
        except ValueError:
            return str(file_path)
