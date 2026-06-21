"""Text embedding encoder using FastEmbed (ONNX, no PyTorch)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from rich.console import Console

from codememory.constants import DEFAULT_EMBEDDING_MODEL, EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from codememory.models import ScanResult

logger = logging.getLogger(__name__)
console = Console()

# Singleton model cache
_model_cache: dict[str, object] = {}


class EmbeddingEncoder:
    """Wraps FastEmbed's TextEmbedding with lazy loading and caching.

    The ONNX model is downloaded on first use and cached in
    ``~/.cache/fastembed/``.  Subsequent calls reuse the in-memory singleton.
    """

    async def load(self) -> None:
        """Pre-load the embedding model (async compatibility shim).

        Calls :meth:`_get_model` in a thread executor to avoid blocking
        the event loop during the initial model download.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._get_model)

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        """Initialise the encoder.

        Args:
            model_name: FastEmbed model identifier.
        """
        self.model_name = model_name
        self._model = None  # lazy

    def _get_model(self):
        """Return the loaded FastEmbed model, downloading it if necessary."""
        if self.model_name in _model_cache:
            self._model = _model_cache[self.model_name]
            return self._model

        if self._model is None:
            try:
                from fastembed import TextEmbedding

                console.print(
                    f"[bold cyan]⬇  Downloading embedding model "
                    f"[yellow]{self.model_name}[/yellow] (first run only)…"
                )
                self._model = TextEmbedding(model_name=self.model_name)
                _model_cache[self.model_name] = self._model
                console.print("[green]✓  Embedding model ready.[/green]")
            except ImportError:
                logger.error(
                    "fastembed is not installed. Install with: pip install fastembed"
                )
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to load embedding model '%s': %s", self.model_name, exc)
                raise
        return self._model

    def encode(self, texts: list[str]) -> list[np.ndarray]:
        """Embed a batch of text strings.

        Args:
            texts: List of strings to encode.

        Returns:
            List of float32 numpy arrays of shape ``(EMBEDDING_DIMENSIONS,)``.
        """
        if not texts:
            return []
        model = self._get_model()
        try:
            embeddings = list(model.embed(texts))
            return [np.array(e, dtype=np.float32) for e in embeddings]
        except Exception as exc:  # noqa: BLE001
            logger.error("Embedding encode error: %s", exc)
            return [np.zeros(EMBEDDING_DIMENSIONS, dtype=np.float32)] * len(texts)

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a single query string for similarity search.

        Args:
            query: The search query.

        Returns:
            Float32 numpy array of shape ``(EMBEDDING_DIMENSIONS,)``.
        """
        results = self.encode([query])
        return results[0] if results else np.zeros(EMBEDDING_DIMENSIONS, dtype=np.float32)

    @staticmethod
    def encode_file(scan_result: "ScanResult") -> str:
        """Produce a rich text representation of a file for embedding.

        Combines: file path, language, class names, function/method names,
        import names, and docstrings into a single concatenated string.

        Args:
            scan_result: The extraction result for a file.

        Returns:
            A multi-line string ready for encoding.
        """
        fi = scan_result.file_info
        parts: list[str] = []

        # File identity
        parts.append(f"file: {fi.path}")
        if fi.language:
            parts.append(f"language: {fi.language}")

        # Class names
        classes = [s.name for s in scan_result.symbols if s.kind == "class"]
        if classes:
            parts.append("classes: " + ", ".join(classes))

        # Function and method names
        funcs = [s.name for s in scan_result.symbols if s.kind in ("function", "method")]
        if funcs:
            parts.append("functions: " + ", ".join(funcs))

        # Imports
        if scan_result.imports:
            parts.append("imports: " + ", ".join(scan_result.imports[:30]))

        # Docstrings (truncated)
        docs = [
            s.docstring[:200]
            for s in scan_result.symbols
            if s.docstring and s.kind in ("class", "function", "method")
        ]
        if docs:
            parts.append("docs: " + " | ".join(docs[:5]))

        # File summary if available
        if fi.summary:
            parts.append(fi.summary)

        return "\n".join(parts)
