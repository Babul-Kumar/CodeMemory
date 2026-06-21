# Architecture Decision Records (ADR)

## Added file: .env.production
- **Date**: 2026-06-21 11:26:58
- **Details**: File .env.production was added to the repository.
- **Affected Files**: `[".env.production"]`

## Added file: Dockerfile
- **Date**: 2026-06-21 11:26:58
- **Details**: File Dockerfile was added to the repository.
- **Affected Files**: `["Dockerfile"]`

## Added file: codememory/intelligence/report_generator.py
- **Date**: 2026-06-21 11:26:58
- **Details**: File codememory/intelligence/report_generator.py was added to the repository.
- **Affected Files**: `["codememory/intelligence/report_generator.py"]`

## Added file: codememory/storage/migrations.py
- **Date**: 2026-06-21 11:26:58
- **Details**: File codememory/storage/migrations.py was added to the repository.
- **Affected Files**: `["codememory/storage/migrations.py"]`

## Added file: docker-compose.yml
- **Date**: 2026-06-21 11:26:58
- **Details**: File docker-compose.yml was added to the repository.
- **Affected Files**: `["docker-compose.yml"]`

## Added file: tests/test_intelligence.py
- **Date**: 2026-06-21 11:26:58
- **Details**: File tests/test_intelligence.py was added to the repository.
- **Affected Files**: `["tests/test_intelligence.py"]`

## Added file: tests/test_watcher.py
- **Date**: 2026-06-21 11:26:58
- **Details**: File tests/test_watcher.py was added to the repository.
- **Affected Files**: `["tests/test_watcher.py"]`

## New Class: CodebaseIntelligenceCompiler
- **Date**: 2026-06-21 11:26:58
- **Details**: Class CodebaseIntelligenceCompiler was added to the codebase.
- **Affected Files**: `[]`

## New Class: DummyEncoder
- **Date**: 2026-06-21 11:26:58
- **Details**: Class DummyEncoder was added to the codebase.
- **Affected Files**: `[]`

## New Class: MockEncoder
- **Date**: 2026-06-21 11:26:58
- **Details**: Class MockEncoder was added to the codebase.
- **Affected Files**: `[]`

## Leftover Work: feature_status Used for Overall Completion
- **Date**: 2026-06-19 12:07:12
- **Details**: Overall Completion % in leftover.md is derived from feature_status table (Implemented=1.0, Partial=0.5, Stubbed=0.2 weighted average) rather than from leftover_task row counts. This provides meaningful completion tracking even when no leftover tasks have been manually marked Completed.
- **Affected Files**: `["codememory/intelligence/report_generator.py", ".ai/leftover.md"]`

## Incremental Intelligence Updates on File Change
- **Date**: 2026-06-19 12:07:12
- **Details**: On file create/modify/delete events from the watchdog loop, incremental_scanner.py calls CodebaseIntelligenceCompiler.update_file_incremental() which rebuilds only the affected file components and re-exports all view files. This keeps intelligence artifacts always up-to-date without a full rescan.
- **Affected Files**: `["codememory/watcher/incremental_scanner.py", "codememory/intelligence/report_generator.py"]`

## MCP Tool Interface: 21 Async Tools via FastMCP
- **Date**: 2026-06-19 12:07:12
- **Details**: Registered 21 async tool functions in server/tools.py, exposed via FastMCP stdio protocol. All tools accept simple string parameters and return JSON or Markdown strings for compatibility with Cursor, Cline, and Claude Desktop. State injected via _set_state() at app startup.
- **Affected Files**: `["codememory/server/tools.py", "codememory/server/app.py"]`

## Hash-based Embeddings as Placeholder (Not Real Semantic)
- **Date**: 2026-06-19 12:07:12
- **Details**: The embeddings_index.json uses SHA-256 hash-derived vectors rather than real FastEmbed model inference. This was a deliberate v1 choice to keep codememory report fast and dependency-free. Real semantic search uses the existing fastembed-powered retrieval engine via the REST API. Future: integrate real embedding model into report_generator.py.
- **Affected Files**: `["codememory/intelligence/report_generator.py", ".ai/embeddings_index.json"]`

## Intelligence Storage: SQLite over JSON-only
- **Date**: 2026-06-19 12:07:12
- **Details**: Decision: Store intelligence layer in .ai/intelligence.db (SQLite) rather than relying solely on JSON files. Rationale: Supports querying, incremental updates, agent memory, and concurrent access. Flat JSON files exported as views for human readability.
- **Affected Files**: `["codememory/intelligence/report_generator.py", ".ai/intelligence.db"]`
