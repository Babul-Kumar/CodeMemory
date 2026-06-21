"""Vector similarity search using sqlite-vec."""
from __future__ import annotations

import logging

import numpy as np

from codememory.storage.database import Database

logger = logging.getLogger(__name__)


class EmbeddingSearcher:
    """Performs approximate nearest-neighbour search using sqlite-vec.

    Falls back to a Python-based cosine similarity scan when the vec0
    extension is unavailable (e.g. in test environments).
    """

    async def search(
        self,
        db: Database,
        query_vec: np.ndarray,
        limit: int = 10,
    ) -> list[dict]:
        """Find the most similar files to *query_vec*.

        Uses the ``file_embeddings`` vec0 virtual table when available,
        otherwise falls back to an in-memory cosine scan.

        Args:
            db:        Active :class:`~codememory.storage.database.Database`.
            query_vec: Query vector (shape ``(EMBEDDING_DIMENSIONS,)``).
            limit:     Maximum results to return.

        Returns:
            List of dicts: ``{file_path, file_id, score}``, sorted by
            descending cosine similarity.
        """
        conn = await db.get_connection()
        results: list[dict] = []

        # Try sqlite-vec KNN query
        try:
            vec_blob = query_vec.astype(np.float32).tobytes()
            cursor = await conn.execute(
                """
                SELECT fe.file_id,
                       f.path AS file_path,
                       fe.distance
                FROM file_embeddings fe
                JOIN files f ON fe.file_id = f.id
                WHERE embedding MATCH ?
                  AND k = ?
                ORDER BY distance
                """,
                (vec_blob, limit),
            )
            rows = await cursor.fetchall()
            if rows:
                for row in rows:
                    # sqlite-vec returns L2 distance; convert to similarity score
                    dist = float(row["distance"])
                    score = 1.0 / (1.0 + dist)
                    results.append(
                        {
                            "file_id": row["file_id"],
                            "file_path": row["file_path"],
                            "score": score,
                        }
                    )
                return results
        except Exception as exc:  # noqa: BLE001
            logger.debug("sqlite-vec KNN query failed, falling back to cosine scan: %s", exc)

        # Fallback: load all embeddings and compute cosine similarity in Python
        results = await self._cosine_scan(conn, query_vec, limit)
        return results

    @staticmethod
    async def _cosine_scan(conn, query_vec: np.ndarray, limit: int) -> list[dict]:
        """Brute-force cosine similarity fallback.

        Args:
            conn:      Active aiosqlite connection.
            query_vec: Query embedding vector.
            limit:     Maximum results.

        Returns:
            Ranked list of result dicts.
        """
        from codememory.constants import EMBEDDING_DIMENSIONS  # noqa: PLC0415

        cursor = await conn.execute(
            "SELECT fe.file_id, f.path AS file_path, fe.embedding FROM file_embeddings fe JOIN files f ON fe.file_id = f.id"
        )
        rows = await cursor.fetchall()

        scored: list[tuple[float, int, str]] = []
        q_norm = np.linalg.norm(query_vec)
        if q_norm == 0:
            return []

        for row in rows:
            try:
                vec = np.frombuffer(row["embedding"], dtype=np.float32)
                if vec.shape[0] != EMBEDDING_DIMENSIONS:
                    continue
                v_norm = np.linalg.norm(vec)
                if v_norm == 0:
                    continue
                score = float(np.dot(query_vec, vec) / (q_norm * v_norm))
                scored.append((score, row["file_id"], row["file_path"]))
            except Exception:  # noqa: BLE001
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"file_id": fid, "file_path": fp, "score": sc}
            for sc, fid, fp in scored[:limit]
        ]
