"""Stores and maintains vector embeddings using sqlite-vec."""
from __future__ import annotations

import logging

import numpy as np

from codememory.constants import EMBEDDING_DIMENSIONS
from codememory.models import ScanResult
from codememory.storage.database import Database

logger = logging.getLogger(__name__)

_CREATE_VEC_TABLE = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS file_embeddings USING vec0(
    file_id INTEGER PRIMARY KEY,
    embedding FLOAT[{EMBEDDING_DIMENSIONS}]
);
"""


class EmbeddingIndexer:
    """Manages storage of file-level vector embeddings in sqlite-vec.

    Each file is represented by a single embedding vector derived from the
    concatenated text of its path, language, symbols, imports, and docstrings.
    """

    async def ensure_table(self, db: Database) -> None:
        """Create the ``file_embeddings`` vec0 virtual table if absent.

        Args:
            db: Active :class:`~codememory.storage.database.Database`.
        """
        conn = await db.get_connection()
        try:
            await conn.execute(_CREATE_VEC_TABLE)
            await conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not create vec0 table (sqlite-vec may be absent): %s", exc)

    async def index_scan_result(
        self,
        db: Database,
        encoder,  # EmbeddingEncoder – avoid circular import
        scan_result: ScanResult,
    ) -> None:
        """Compute and store the embedding for a single file.

        Args:
            db:          Active :class:`~codememory.storage.database.Database`.
            encoder:     A loaded :class:`~codememory.embeddings.encoder.EmbeddingEncoder`.
            scan_result: Extraction result for the file to embed.
        """
        await self.ensure_table(db)
        conn = await db.get_connection()

        # Retrieve the file_id
        cursor = await conn.execute(
            "SELECT id FROM files WHERE path = ?", (scan_result.file_info.path,)
        )
        row = await cursor.fetchone()
        if row is None:
            logger.debug("File not yet indexed in DB; skipping embedding: %s", scan_result.file_info.path)
            return

        file_id: int = row["id"]

        # Build text and encode
        from codememory.embeddings.encoder import EmbeddingEncoder  # noqa: PLC0415

        text = EmbeddingEncoder.encode_file(scan_result)
        vectors = encoder.encode([text])
        if not vectors:
            return

        vec: np.ndarray = vectors[0]

        try:
            # sqlite-vec uses a serialized blob for vectors
            vec_blob = vec.astype(np.float32).tobytes()
            await conn.execute("DELETE FROM file_embeddings WHERE file_id = ?", (file_id,))
            await conn.execute(
                """
                INSERT INTO file_embeddings (file_id, embedding)
                VALUES (?, ?)
                """,
                (file_id, vec_blob),
            )
            await conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to store embedding for file_id %d: %s", file_id, exc)

    async def index_batch(
        self,
        db: Database,
        encoder,
        scan_results: list[ScanResult],
        batch_size: int = 32,
    ) -> None:
        """Index a batch of scan results efficiently.

        Encodes all files in batches before writing to the database.

        Args:
            db:           Active database.
            encoder:      Embedding encoder.
            scan_results: Files to embed.
            batch_size:   Number of files to embed per batch.
        """
        await self.ensure_table(db)
        conn = await db.get_connection()

        from codememory.embeddings.encoder import EmbeddingEncoder  # noqa: PLC0415

        # Build (file_id, text) pairs
        pairs: list[tuple[int, str]] = []
        for sr in scan_results:
            cursor = await conn.execute(
                "SELECT id FROM files WHERE path = ?", (sr.file_info.path,)
            )
            row = await cursor.fetchone()
            if row:
                text = EmbeddingEncoder.encode_file(sr)
                pairs.append((row["id"], text))

        # Process in batches
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i: i + batch_size]
            texts = [t for _, t in batch]
            vectors = encoder.encode(texts)
            for (file_id, _), vec in zip(batch, vectors):
                try:
                    vec_blob = vec.astype(np.float32).tobytes()
                    await conn.execute("DELETE FROM file_embeddings WHERE file_id = ?", (file_id,))
                    await conn.execute(
                        "INSERT INTO file_embeddings (file_id, embedding) VALUES (?, ?)",
                        (file_id, vec_blob),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Batch embedding insert failed for file_id %d: %s", file_id, exc)
        await conn.commit()
        logger.info("Indexed %d file embeddings.", len(pairs))
