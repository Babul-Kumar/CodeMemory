# Changelog

All notable changes to CodeMemory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-06-12

### Added

#### Core
- `codememory/models.py` — Pydantic/dataclass models: `FileInfo`, `SymbolInfo`, `ScanResult`, `RetrievalResult`, `ProjectSummary`
- `codememory/config.py` — `CodeMemoryConfig`, `get_repo_data_dir`, `get_repo_hash`, `load_config`
- `codememory/constants.py` — Global constants: `GLOBAL_DATA_DIR`, `DB_FILENAME`, `GRAPH_FILENAME`, `DEFAULT_EMBEDDING_MODEL`, `CODE_EXTENSIONS`

#### Storage (Phase 2)
- `codememory/storage/database.py` — Async SQLite wrapper with FTS5 and semantic search support
- `codememory/storage/repository.py` — `CodeRepository` for file/symbol CRUD operations

#### Graph (Phase 3)
- `codememory/graph/builder.py` — `GraphBuilder` using NetworkX for dependency / call graphs
- `codememory/graph/serializer.py` — `GraphSerializer` for persisting graphs to/from the database

#### Scanner (Phase 4)
- `codememory/scanner/` — `RepositoryScanner` with `.gitignore` support, multi-language detection, and AST-based Python extractor

#### Embeddings (Phase 5)
- `codememory/embeddings/encoder.py` — `EmbeddingEncoder` wrapping sentence-transformers
- `codememory/embeddings/indexer.py` — `EmbeddingIndexer` for FAISS index construction
- `codememory/embeddings/searcher.py` — `EmbeddingSearcher` for nearest-neighbour retrieval

#### Watcher / Incremental Updates (Phase 6)
- `codememory/watcher/change_detector.py` — SHA-256 based file change detection
- `codememory/watcher/file_watcher.py` — Watchdog-based `CodeFileWatcher` with 500 ms debouncing and asyncio integration
- `codememory/watcher/incremental_scanner.py` — `IncrementalScanner` for single-file re-indexing

#### Retrieval Engine (Phase 7)
- `codememory/retrieval/query_parser.py` — `QueryParser` extracting file hints, symbol hints, keywords, and intent
- `codememory/retrieval/ranker.py` — `ResultRanker` implementing Reciprocal Rank Fusion (RRF, k=60) and graph-aware re-ranking
- `codememory/retrieval/engine.py` — `RetrievalEngine` orchestrating FTS + semantic search + RRF + graph re-rank

#### MCP Server + REST API (Phase 8)
- `codememory/server/routes.py` — FastAPI router: `/health`, `/project/summary`, `/project/architecture`, `/search`, `/files/{path}`, `/symbols/{name}`, `/changes`, `/graph/neighbors/{path}`
- `codememory/server/tools.py` — MCP tool functions: `get_project_summary`, `get_architecture`, `get_relevant_files`, `get_module_summary`, `search_memory`, `get_recent_changes`
- `codememory/server/app.py` — `create_app()` factory + `get_mcp_server()` for stdio mode

#### CLI (Phase 9)
- `codememory/cli.py` — Typer CLI with Rich output: `init`, `scan`, `watch`, `serve`, `query`, `status`, `reset`

#### Tests (Phase 10)
- `tests/conftest.py` — Shared fixtures: `temp_repo` (fake Python project), `db` (in-memory SQLite)
- `tests/test_scanner.py` — Scanner tests: gitignore, language detection, Python extractor
- `tests/test_storage.py` — Storage tests: upsert, FTS search, change detection
- `tests/test_retrieval.py` — Retrieval tests: RRF fusion, QueryParser extraction/intent
- `tests/test_server.py` — Server tests: all REST endpoints with mocked engine

#### Documentation
- `README.md` — Comprehensive documentation with installation, quick start, MCP configs, CLI reference
- `CHANGELOG.md` — This file
- `.gitignore` — Standard Python gitignore

[0.1.0]: https://github.com/yourusername/codememory/releases/tag/v0.1.0
