# Module Map & AI Context

This document maps the repository's core modules, responsibilities, and how they contribute to CodeMemory's intelligence platform.

## 1. Configuration & CLI
* `codememory/cli.py`: Typer CLI entry point with Rich styling. Defines commands for database initialization, scans, file watching, queries, and server configuration.
* `codememory/config.py`: Resolves per-repository hash IDs, data storage paths, and handles `.env`/`config.toml` configurations.
* `codememory/constants.py`: Holds global constants like dimensions (384), standard file extensions, and default model identifiers.

## 2. Database & Storage Layer
* `codememory/storage/database.py`: Manages the database connection lifecycle, executing raw schema configurations and delegating FTS/semantic searches.
* `codememory/storage/repository.py`: CRUD operations for files, symbols, relationships, and schema state metrics.
* `codememory/storage/migrations.py`: Schema versioning manager executing incremental SQL migration scripts automatically.
* `codememory/storage/schema.sql`: Standard relational table layout for file indices, symbols, relationships, features, and migrations.

## 3. Parser & Extractor Layer
* `codememory/scanner/file_walker.py`: Recursively crawls files in a workspace directory, parsing and honoring `.gitignore` rules.
* `codememory/scanner/tree_sitter_parser.py`: Loads grammar modules dynamically and builds parsing ASTs for code files.
* `codememory/scanner/language_detector.py`: Detects source languages based on file extensions.
* `codememory/scanner/extractors/`: AST query symbol extractors:
  * `python_extractor.py`
  * `javascript_extractor.py`
  * `typescript_extractor.py`
  * `go_extractor.py`
  * `rust_extractor.py`
  * `java_extractor.py`
  * `generic_extractor.py` (regex fallback)

## 4. Knowledge Graph & Embeddings
* `codememory/graph/builder.py`: Constructs a NetworkX directed graph containing code dependencies.
* `codememory/graph/relationships.py`: Detects imports and call connections between symbols.
* `codememory/graph/serializer.py`: Serializes and deserializes the knowledge graph as JSON.
* `codememory/embeddings/encoder.py`: FastEmbed model wrapper.
* `codememory/embeddings/indexer.py`: Generates database vector embeddings and indices.
* `codememory/embeddings/searcher.py`: Performs nearest-neighbor similarity searches using local vector data.

## 5. Retrieval & Reranking Engine
* `codememory/retrieval/engine.py`: Hybrid search engine combining semantic similarity, FTS, and graph relationships.
* `codememory/retrieval/query_parser.py`: Extracts path hints, symbols, keywords, and intents from natural language queries.
* `codememory/retrieval/ranker.py`: Implements hybrid Reciprocal Rank Fusion (RRF) with graph re-ranking and continuous scoring.

## 6. Codebase Watcher
* `codememory/watcher/file_watcher.py`: Watchdog-based observer tracking file creation, modification, and deletion.
* `codememory/watcher/incremental_scanner.py`: Re-indexes modified files incrementally without triggering full scans.
* `codememory/watcher/change_detector.py`: Verifies file alterations using SHA-256 hashes.

## 7. Intelligence & Analytics
* `codememory/intelligence/architecture.py`: Identifies architectural layers (e.g., routing, models, tests).
* `codememory/intelligence/patterns.py`: Detects design patterns (MVC, Singleton, Factory, Repository, Observer, Middleware).
* `codememory/intelligence/summarizer.py`: Creates summary descriptions for file responsibilities.
* `codememory/intelligence/report_generator.py`: Generates the codebase intelligence layer.
