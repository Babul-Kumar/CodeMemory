"""Pydantic-based configuration management for CodeMemory."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import BaseModel, Field

from codememory.constants import (
    CONFIG_FILENAME,
    DEFAULT_EMBEDDING_MODEL,
    GLOBAL_DATA_DIR,
)

logger = logging.getLogger(__name__)


class CodeMemoryConfig(BaseModel):
    """Configuration model for a CodeMemory project instance."""

    max_file_size_bytes: int = Field(
        default=500_000,
        description="Maximum file size in bytes to include during scanning.",
    )
    max_workers: int = Field(
        default=4,
        description="Number of parallel workers used during repository scanning.",
    )
    embedding_model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        description="FastEmbed model identifier used for vector embeddings.",
    )
    ignored_patterns: list[str] = Field(
        default_factory=list,
        description="Additional glob patterns to ignore during scanning.",
    )
    include_patterns: list[str] = Field(
        default_factory=list,
        description="If non-empty, only files matching these patterns are included.",
    )


def get_repo_hash(repo_path: Path) -> str:
    """Return a 16-character SHA-256 hex digest of the absolute repo path.

    This hash is used to create a unique, deterministic directory under
    ``~/.codememory/`` for each repository.

    Args:
        repo_path: Absolute (or relative) path to the repository root.

    Returns:
        A 16-character lowercase hex string.
    """
    absolute = str(repo_path.resolve())
    digest = hashlib.sha256(absolute.encode()).hexdigest()
    return digest[:16]


def get_repo_data_dir(repo_path: Path) -> Path:
    """Return the global data directory for a specific repository.

    The directory follows the pattern ``~/.codememory/<repo_hash>/``.

    Args:
        repo_path: Path to the repository root.

    Returns:
        A :class:`pathlib.Path` pointing to the repo-specific data directory.
    """
    return GLOBAL_DATA_DIR / get_repo_hash(repo_path)


def load_config(repo_path: Path) -> CodeMemoryConfig:
    """Load configuration from disk, falling back to defaults if absent.

    Reads ``~/.codememory/<repo_hash>/config.toml``.  If the file does not
    exist or cannot be parsed, a default :class:`CodeMemoryConfig` is returned.
    Also supports environment variables and `.env` file overrides.

    Args:
        repo_path: Path to the repository root.

    Returns:
        A populated :class:`CodeMemoryConfig` instance.
    """
    # Load dotenv if available
    try:
        import dotenv
        dotenv.load_dotenv(repo_path / ".env")
    except Exception:
        pass

    config_path = get_repo_data_dir(repo_path) / CONFIG_FILENAME
    data: dict[str, Any] = {}
    
    if config_path.exists():
        try:
            import tomllib  # stdlib in 3.11+

            with config_path.open("rb") as fh:
                data = tomllib.load(fh)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load config from %s: %s. Using defaults.", config_path, exc
            )

    # Apply environment overrides
    import os
    
    max_file_size = os.environ.get("CODEMEMORY_MAX_FILE_SIZE_BYTES")
    if max_file_size:
        try:
            data["max_file_size_bytes"] = int(max_file_size)
        except ValueError:
            pass
            
    max_workers = os.environ.get("CODEMEMORY_MAX_WORKERS")
    if max_workers:
        try:
            data["max_workers"] = int(max_workers)
        except ValueError:
            pass
            
    emb_model = os.environ.get("CODEMEMORY_EMBEDDING_MODEL")
    if emb_model:
        data["embedding_model"] = emb_model
        
    ignored = os.environ.get("CODEMEMORY_IGNORED_PATTERNS")
    if ignored:
        data["ignored_patterns"] = [p.strip() for p in ignored.split(",") if p.strip()]
        
    included = os.environ.get("CODEMEMORY_INCLUDE_PATTERNS")
    if included:
        data["include_patterns"] = [p.strip() for p in included.split(",") if p.strip()]

    return CodeMemoryConfig(**data)


def save_config(repo_path: Path, config: CodeMemoryConfig) -> None:
    """Persist configuration to ``~/.codememory/<repo_hash>/config.toml``.

    Creates the data directory if it does not exist.

    Args:
        repo_path: Path to the repository root.
        config:    The configuration instance to persist.
    """
    data_dir = get_repo_data_dir(repo_path)
    data_dir.mkdir(parents=True, exist_ok=True)
    config_path = data_dir / CONFIG_FILENAME

    try:
        payload = config.model_dump()
        with config_path.open("wb") as fh:
            tomli_w.dump(payload, fh)
        logger.debug("Config saved to %s.", config_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save config to %s: %s", config_path, exc)
        raise
