# Module Map & AI Context

This document explains the repository's primary modules, their responsibilities, and how they contribute to CodeMemory's intelligence platform.

## 1. Configuration and CLI
* `codememory/cli.py`: Defines the Typer command-line interface and orchestrates commands for database initialization, repository scanning, file watching, queries, and server operation.
* `codememory/config.py`: Resolves repository identifiers, data storage locations, and loads configuration from environment variables, `.env` files, and `config.toml`.
* `codememory/constants.py`: Defines global constants such as embedding dimensions, supported file extensions, and default model identifiers.

## 2. Database and Storage
* `codememory/storage/database.py`: Manages SQLite connections, executes schema statements, and supports full-text and semantic search operations.
* `codememory/storage/repository.py`: Provides CRUD operations for files, symbols, relationships, and schema metadata.
* `codememory/storage/migrations.py`: Implements schema versioning and applies incremental SQL migrations automatically.
* `codememory/storage/schema.sql`: Defines the relational schema for file indices, symbols, relationships, vector features, and migration state.

## 3. Parser and Extraction
* `codememory/scanner/file_walker.py`: Recursively discovers repository files while respecting ignore rules.
* `codememory/scanner/tree_sitter_parser.py`: Loads language grammars dynamically and builds parse trees for source files.
* `codememory/scanner/language_detector.py`: Detects source language types based on file extensions.
* `codememory/scanner/extractors/`: Contains language-specific symbol extractors and fallback extraction logic.
  * `python_extractor.py`
  * `javascript_extractor.py`
  * `typescript_extractor.py`
  * `go_extractor.py`
  * `rust_extractor.py`
  * `java_extractor.py`
  * `generic_extractor.py` — fallback extraction using regex patterns

## 4. Knowledge Graph and Embeddings
* `codememory/graph/builder.py`: Builds a directed dependency graph that represents file and symbol relationships.
* `codememory/graph/relationships.py`: Detects import links, call relationships, and other connections between symbols.
* `codememory/graph/serializer.py`: Serializes and deserializes the knowledge graph to and from JSON.
* `codememory/embeddings/encoder.py`: Wraps the FastEmbed embedding model for local semantic vector generation.
* `codememory/embeddings/indexer.py`: Computes and stores vector embeddings in the database.
* `codememory/embeddings/searcher.py`: Executes nearest-neighbor similarity searches using local vectors.

## 5. Retrieval and Ranking
* `codememory/retrieval/engine.py`: Implements a hybrid search engine combining semantic similarity, full-text search, and graph-based signals.
* `codememory/retrieval/query_parser.py`: Parses natural language queries to extract symbols, paths, intents, and keywords.
* `codememory/retrieval/ranker.py`: Applies Reciprocal Rank Fusion (RRF) and graph re-ranking to produce stable, relevance-optimized results.

## 6. Repository Watcher
* `codememory/watcher/file_watcher.py`: Observes filesystem changes and triggers repository updates for file creation, modification, and deletion.
* `codememory/watcher/incremental_scanner.py`: Re-indexes modified files incrementally without requiring a full repository scan.
* `codememory/watcher/change_detector.py`: Uses SHA-256 hashing to detect file changes reliably.

## 7. Intelligence and Analytics
* `codememory/intelligence/architecture.py`: Identifies architectural layers within the repository, such as routing, models, and tests.
* `codememory/intelligence/patterns.py`: Detects common design patterns including MVC, Singleton, Factory, Repository, Observer, and Middleware.
* `codememory/intelligence/summarizer.py`: Generates concise descriptions of file roles and responsibilities.
* `codememory/intelligence/report_generator.py`: Produces intelligence reports and context artifacts for downstream agents.
