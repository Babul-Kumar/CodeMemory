# CodeMemory

**Universal memory and context layer for AI coding agents.**

CodeMemory indexes any code repository into a queryable knowledge store that AI agents can use to understand large codebases instantly — without re-reading every file each session.

## Features

- 🔍 **Repository Scanner** — Tree-sitter parsing for Python, JS/TS, Go, Rust, Java with fallback regex extraction
- 🧠 **Knowledge Graph** — NetworkX DiGraph of file/symbol relationships, persisted as JSON
- 🗄️ **SQLite Store** — WAL-mode SQLite with FTS5 keyword search and sqlite-vec vector embeddings
- 📐 **Embedding Engine** — BAAI/bge-small-en-v1.5 via FastEmbed (ONNX, no PyTorch)
- 🏗️ **Architecture Intelligence** — Layer detection, entry point discovery, design pattern detection
- 💾 **Global Storage** — All data lives in `~/.codememory/<repo-hash>/` (never pollutes repos)

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Index a repository
codememory index /path/to/repo

# Search with semantic + keyword hybrid
codememory search "authentication middleware" --repo /path/to/repo

# Show statistics
codememory stats --repo /path/to/repo
```

## Architecture

```
codememory/
├── constants.py          # Global constants
├── config.py             # Pydantic config + repo hash utils
├── models.py             # Shared Pydantic v2 data models
├── cli.py                # Typer CLI entry point
├── scanner/              # Phase 2: File walking + tree-sitter parsing
│   ├── file_walker.py
│   ├── language_detector.py
│   ├── tree_sitter_parser.py
│   └── extractors/       # Per-language symbol extractors
├── storage/              # Phase 3: SQLite CRUD
│   ├── schema.sql
│   ├── database.py
│   └── repository.py
├── graph/                # Phase 3: Knowledge graph
│   ├── builder.py
│   ├── relationships.py
│   └── serializer.py
├── embeddings/           # Phase 4: Vector search
│   ├── encoder.py
│   ├── indexer.py
│   └── searcher.py
└── intelligence/         # Phase 5: Architecture analysis
    ├── summarizer.py
    ├── architecture.py
    └── patterns.py
```

## Storage Layout

```
~/.codememory/
└── <16-char-sha256-of-repo-path>/
    ├── codememory.db   # SQLite database (files, symbols, FTS5, vec0)
    ├── graph.json      # Serialized NetworkX graph
    └── config.toml     # Per-repo configuration
```

## License

MIT
