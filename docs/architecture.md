# Architecture Overview

CodeMemory is a repository intelligence platform designed to connect source code, semantic embeddings, dependency analysis, and agent-driven tools into a unified, queryable knowledge layer.

## Core Components

* **Repository Scanner** — recursively traverses source files, detects language types, and extracts symbols through AST parsing and fallback extractors.
* **Knowledge Graph** — represents files, symbols, imports, call relationships, and dependency paths in a directed graph structure.
* **Semantic Index** — generates embeddings for code, documentation, and symbols, then stores them for efficient similarity search.
* **Intelligence Engine** — analyzes architecture, detects design patterns, and creates repository summaries and context packages.
* **Agent Interface** — exposes capabilities through a service layer, enabling search, analysis, memory, and health monitoring.
* **Incremental Watcher** — tracks file changes and updates the intelligence layer on a per-file basis to avoid expensive full repository rescans.

## System Boundaries

* `codememory/scanner/` handles repository traversal, language detection, parsing, and extractor orchestration.
* `codememory/graph/` constructs and serializes the repository relationship graph.
* `codememory/embeddings/` manages embedding generation, vector storage, and similarity search.
* `codememory/retrieval/` handles query parsing, hybrid search, and ranking logic.
* `codememory/intelligence/` generates architectural reports, summaries, and intelligence artifacts for agents.
* `codememory/server/` exposes the public service API and agent integration endpoints.
* `codememory/watcher/` monitors filesystem events and performs incremental repository updates.

## Additional Resources

For a complete module catalog and AI context map, refer to `docs/module_map.md`.
