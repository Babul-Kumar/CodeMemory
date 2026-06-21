# Architecture Decision Records (ADR)

## 1. SQLite Over Plain JSON Files
* **Date**: 2026-06-19
* **Details**: The intelligence platform layer is persisted inside `.ai/intelligence.db` rather than flat JSON files. This ensures efficient concurrent queries, atomic writes, and supports incremental updates for long-term agent memory. Human-readable JSON views are exported for convenience.
* **Affected Files**: `codememory/intelligence/report_generator.py`, `.ai/intelligence.db`

## 2. FastEmbed Semantic Embeddings
* **Date**: 2026-06-21
* **Details**: Vector embeddings are computed locally using FastEmbed (`BAAI/bge-small-en-v1.5`) rather than hash placeholders. In memory-constrained environments, the system falls back to hash-based vector placeholders.
* **Affected Files**: `codememory/embeddings/encoder.py`, `codememory/intelligence/report_generator.py`

## 3. File Watcher & Incremental Re-indexing
* **Date**: 2026-06-19
* **Details**: To keep intelligence data updated, the filesystem watchdog monitors changes and executes `update_file_incremental()` on single modified files, avoiding the overhead of full scans.
* **Affected Files**: `codememory/watcher/incremental_scanner.py`, `codememory/intelligence/report_generator.py`

## 4. Production Environment Configuration
* **Date**: 2026-06-19
* **Details**: Configuration settings (e.g., `CODEMEMORY_MAX_WORKERS`) can be overridden directly using environment variables prefixed with `CODEMEMORY_`, easing containerized deployments.
* **Affected Files**: `codememory/config.py`

## 5. Continuous Scoring in RRF Search
* **Date**: 2026-06-21
* **Details**: Integrated raw semantic similarity scores scaled by `0.1` into the Reciprocal Rank Fusion (RRF) algorithm to stabilize search rankings and prevent order-flipping anomalies.
* **Affected Files**: `codememory/retrieval/ranker.py`
