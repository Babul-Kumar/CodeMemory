"""Constants for the CodeMemory package."""
from __future__ import annotations

from pathlib import Path

APP_NAME = "codememory"
APP_VERSION = "0.1.0"

# Global storage: all data lives outside scanned repos
GLOBAL_DATA_DIR: Path = Path.home() / ".codememory"

# Embedding configuration
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384

# Storage filenames
DB_FILENAME = "codememory.db"
GRAPH_FILENAME = "graph.json"
CONFIG_FILENAME = "config.toml"

# Maps file extension -> language name (tree-sitter language identifier)
SUPPORTED_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".md": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}

# Supported code file extensions as a set
CODE_EXTENSIONS: set[str] = set(SUPPORTED_LANGUAGES.keys())


# Binary file extensions that should never be read as text
BINARY_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".tiff", ".webp",
    ".svg",  # technically XML but treated as binary asset here
    ".mp3", ".mp4", ".wav", ".ogg", ".flac", ".avi", ".mov", ".mkv", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".lib", ".a", ".o",
    ".pyc", ".pyo", ".pyd",
    ".class", ".jar", ".war",
    ".wasm", ".bin", ".dat",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".sqlite3",
    ".lock",  # usually text but can be large; handled per-case
    ".map",   # source maps – large, not useful for analysis
}

# Directories that should always be skipped during scanning
IGNORED_DIRS: set[str] = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",       # Rust / Java / Maven
    "out",          # Java / Kotlin
    ".next",        # Next.js
    ".nuxt",        # Nuxt.js
    ".output",
    ".cache",
    "coverage",
    ".nyc_output",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "site-packages",
    ".tox",
    "eggs",
    ".eggs",
    "*.egg-info",
    "__mocks__",
    ".gradle",
    ".idea",
    ".vscode",
    ".DS_Store",
}
