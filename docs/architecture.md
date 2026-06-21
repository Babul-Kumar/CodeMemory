# Architecture Overview

CodeMemory is built as a persistent repository intelligence platform for AI coding agents. Its architecture connects source code, semantic embeddings, dependency graphs, and agent interfaces in a single, queryable knowledge layer.

## Core architecture

* **Repository Scanner** — crawls source files, detects languages, and extracts symbols using ASTs and fallback extractors.
* **Knowledge Graph** — maps files, symbols, imports, calls, and relationships into a directed graph.
* **Semantic Index** — computes vector embeddings for text, code, and symbols, then stores them for fast similarity search.
* **Architecture Intelligence** — classifies layers, detects design patterns, and generates higher-level repo summaries.
* **Agent Interface** — exposes the intelligence layer through MCP with search, analysis, memory, and health tools.
* **Incremental watcher** — updates only changed files on disk so the intelligence layer stays fresh without rescanning the whole repo.

## System boundaries

* `codememory/scanner/` handles repository parsing and content extraction.
* `codememory/graph/` handles relationship detection and graph serialization.
* `codememory/embeddings/` handles embedding generation and nearest-neighbor search.
* `codememory/retrieval/` handles hybrid search, query parsing, and ranking.
* `codememory/intelligence/` produces architecture reports and context packs for agents.
* `codememory/server/` exposes the MCP/REST endpoint.
* `codememory/watcher/` handles file change detection and incremental updates.

## Read more

For the full module catalog and AI context mapping, see `docs/module_map.md`.
