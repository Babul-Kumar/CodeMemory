# Architecture Decision Records (ADR)

The following entries document major architectural decisions for CodeMemory. Each record includes the decision rationale, the date it was made, and the modules affected by the change.

## 1. SQLite Instead of Flat JSON
* **Date**: 2026-06-19
* **Decision**: Persist the intelligence platform state in `.ai/intelligence.db` instead of using flat JSON files.
* **Rationale**: SQLite provides efficient concurrent reads, atomic writes, and reliable incremental updates, which are essential for long-lived agent memory and ongoing repository analysis. JSON views are still produced for convenience and human review.
* **Impacted Modules**: `codememory/intelligence/report_generator.py`, `.ai/intelligence.db`

## 2. Local FastEmbed Semantic Embeddings
* **Date**: 2026-06-21
* **Decision**: Generate vector embeddings locally using FastEmbed (`BAAI/bge-small-en-v1.5`) instead of placeholder hashes.
* **Rationale**: Local semantic embeddings improve retrieval relevance and reduce dependence on external services. A fallback mechanism supports hash-based vectors when execution memory is constrained.
* **Impacted Modules**: `codememory/embeddings/encoder.py`, `codememory/intelligence/report_generator.py`

## 3. Incremental File Watcher Updates
* **Date**: 2026-06-19
* **Decision**: Use a filesystem watcher to detect changes and update only the modified files instead of rescanning the entire repository.
* **Rationale**: Incremental re-indexing minimizes processing overhead and keeps the intelligence layer up to date with file-level edits.
* **Impacted Modules**: `codememory/watcher/incremental_scanner.py`, `codememory/intelligence/report_generator.py`

## 4. Environment-Driven Production Configuration
* **Date**: 2026-06-19
* **Decision**: Allow production configuration overrides through `CODEMEMORY_`-prefixed environment variables.
* **Rationale**: Environment-based configuration simplifies deployment in containerized and cloud-native environments while preserving a consistent runtime configuration model.
* **Impacted Modules**: `codememory/config.py`

## 5. Continuous Scoring in RRF Search
* **Date**: 2026-06-21
* **Decision**: Incorporate raw semantic similarity scores, scaled by `0.1`, into Reciprocal Rank Fusion (RRF) ranking.
* **Rationale**: Adding continuous scoring improves ranking stability and prevents unexpected result order changes while preserving the benefits of hybrid retrieval.
* **Impacted Modules**: `codememory/retrieval/ranker.py`
