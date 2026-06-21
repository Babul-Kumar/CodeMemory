# Changelog

## [1.0.0] - 2026-06-21
### Added
* True local FastEmbed semantic embeddings (`BAAI/bge-small-en-v1.5`).
* Custom native database migrations manager with schema version tracking.
* Production `.env.production` override template and `dotenv` config loading.
* Health Check MCP tool reporting overall system stats, connection states, and repo hashes.
* Slim multi-stage `Dockerfile` and `docker-compose.yml` configs.
* GitHub Actions CI/CD workflows for automated pytests.
* Automatic Architecture Decision Recording (ADR) logging new directories, files, and classes during report compilation.
* Hybrid ranker RRF scoring utilizing raw cosine similarity/FTS scores.

## [0.1.0] - 2026-06-12
### Added
* Core Pydantic data models.
* Async SQLite DB wrapper with FTS5 search.
* Graph builder mapping codebase dependencies using NetworkX.
* AST symbol extractors for Python, Javascript/Typescript, Go, Rust, and Java.
* Watchdog filesystem monitor for incremental file re-indexing.
* Reciprocal Rank Fusion (RRF) search engine.
* FastMCP stdio server and Typer CLI commands.

## Test Coverage
All 109 unit tests pass across 8 test files:

| Test File | Coverage |
|---|---|
| `tests/test_extractors.py` | Rust, Go, JavaScript, TypeScript, Java AST extractors |
| `tests/test_architecture_patterns.py` | `ArchitectureAnalyzer` + `PatternDetector` |
| `tests/test_intelligence.py` | Intelligence compiler, ADR recording, incremental updates |
| `tests/test_retrieval.py` | Hybrid search, RRF ranker, query parser, semantic search |
| `tests/test_scanner.py` | File walker, language detection, Python extractor |
| `tests/test_server.py` | All REST endpoints |
| `tests/test_storage.py` | SQLite CRUD, FTS5, change detection |
| `tests/test_watcher.py` | File watcher, incremental re-indexer |
