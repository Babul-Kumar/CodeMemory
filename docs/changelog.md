# Changelog

## [1.0.0] - 2026-06-21
### Highlights
* Added local FastEmbed semantic embeddings using `BAAI/bge-small-en-v1.5`.
* Introduced a native database migration manager with schema version tracking.
* Added production-ready environment configuration via `.env.production` and automatic `dotenv` loading.
* Added an MCP health check tool reporting system metrics, connectivity state, and repository metadata.
* Added optimized multi-stage `Dockerfile` and corresponding `docker-compose.yml` configuration.
* Added GitHub Actions workflows for automated testing and CI enforcement.
* Added Architecture Decision Record (ADR) logging during intelligence report generation.
* Added hybrid retrieval ranking with raw cosine similarity and FTS score integration.

## [0.1.0] - 2026-06-12
### Initial Release
* Implemented core Pydantic data models.
* Implemented an asynchronous SQLite database wrapper with FTS5 search support.
* Implemented a repository graph builder using NetworkX.
* Implemented AST-based symbol extractors for Python, JavaScript/TypeScript, Go, Rust, and Java.
* Implemented a filesystem watcher for incremental repository re-indexing.
* Implemented a Reciprocal Rank Fusion (RRF) search engine.
* Implemented a FastMCP stdio server and Typer CLI command set.

## Test Summary
All 109 unit tests pass across eight test files:

* `tests/test_extractors.py` — AST extractors for Rust, Go, JavaScript, TypeScript, and Java.
* `tests/test_architecture_patterns.py` — architecture analysis and pattern detection.
* `tests/test_intelligence.py` — intelligence compilation, ADR logging, and incremental updates.
* `tests/test_retrieval.py` — hybrid search, ranking, and query parsing.
* `tests/test_scanner.py` — repository scanning, language detection, and extraction.
* `tests/test_server.py` — service endpoint verification.
* `tests/test_storage.py` — SQLite CRUD operations, FTS5 search, and schema handling.
* `tests/test_watcher.py` — file watcher and incremental re-indexing.
