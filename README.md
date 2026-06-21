# CodeMemory

A persistent repository intelligence platform for AI coding agents.

CodeMemory stores and serves repository knowledge so AI agents can work from memory instead of re-reading the same source files on every session.

## Overview

CodeMemory transforms a codebase into a durable intelligence layer that includes a knowledge graph, semantic embeddings, architecture analysis, and agent-ready context artifacts. This reduces token waste, accelerates reasoning, and improves agent reliability when working with large repositories.

## Why CodeMemory?

Modern AI coding tools often re-scan repository contents for every interaction. That process is expensive and inefficient because it repeats the same file reading, dependency discovery, and architecture reconstruction.

CodeMemory solves that problem by maintaining:

* persistent repository structure
* dependency and symbol relationships
* architecture insights and design patterns
* semantic search embeddings
* context packs for focused tasks
* incremental updates for changed files

This enables AI agents to query repository intelligence directly instead of rebuilding understanding from scratch.

## Key Differentiators

* Persistent repository intelligence layer
* Local semantic embeddings with FastEmbed
* Knowledge graph of code and dependencies
* Automatic architecture and pattern analysis
* Incremental file scanning and re-indexing
* Native MCP integration for AI agents

## Core Capabilities

* Persistent repo intelligence with a semantic knowledge layer
* Local FastEmbed embeddings for efficient semantic search
* Graph-based dependency and symbol relationship modeling
* Automated architecture and pattern analysis
* Incremental scanning for rapid updates
* MCP-native server for AI agent integration

## Architecture

CodeMemory is organized into distinct functional layers:

* `codememory/scanner/` — repository traversal, language detection, AST parsing, and symbol extraction
* `codememory/graph/` — graph construction, relationship detection, and serialization
* `codememory/embeddings/` — embedding generation, indexing, and similarity search
* `codememory/retrieval/` — query parsing, hybrid search, and ranking
* `codememory/intelligence/` — architecture analysis, pattern detection, and intelligence report generation
* `codememory/server/` — MCP service and API exposure
* `codememory/watcher/` — file change detection and incremental updates

For a complete module catalog, see `docs/module_map.md`.

## Quick Start

1. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
2. Initialize the repository database:
   ```bash
   codememory init
   ```
3. Scan the repository:
   ```bash
   codememory scan
   ```
4. Start the MCP server:
   ```bash
   codememory serve /absolute/path/to/your/repo --stdio
   ```

## Example Workflows

### Repository Understanding

Request an architecture overview from your AI agent:

```text
Explain this repository architecture.
```

The agent can use:

```text
get_architecture_overview()
```

and receive:

* system layers
* major components
* dependency structure
* entry points
* architectural patterns

### Feature Development

Request a context pack for a feature:

```text
Implement OAuth authentication.
```

The agent can use:

```text
get_context_pack("oauth authentication")
```

and receive:

* relevant source files
* dependency context
* existing implementation details
* architecture notes
* related components

### Safe Refactoring

Request change impact analysis before editing:

```text
Refactor UserService.
```

The agent can use:

```text
get_change_impact("user_service.py")
```

and receive:

* affected modules
* dependent services
* related APIs
* impacted tests

### Project Health

Request project guidance:

```text
What should I work on next?
```

The agent can use:

```text
get_next_tasks()
get_repository_health()
```

and receive:

* outstanding work items
* technical debt areas
* deployment blockers
* testing coverage gaps

## MCP Tools

CodeMemory exposes MCP tools for repository awareness and task automation, including:

* `get_project_summary`
* `get_ai_context`
* `get_architecture_overview`
* `search_codebase`
* `get_change_impact`
* `get_project_history`
* `get_next_tasks`
* `get_repository_health`

## Supported AI Agents

CodeMemory is compatible with any MCP-compliant agent, including:

* Cursor
* Claude Desktop
* Cline
* Roo Code
* Codex CLI
* Antigravity

## Documentation

* `docs/architecture.md` — architecture overview
* `docs/module_map.md` — module map and AI context
* `docs/adr.md` — architecture decision records
* `docs/changelog.md` — changelog and release notes

## License

MIT

Maintained by Babul Kumar
