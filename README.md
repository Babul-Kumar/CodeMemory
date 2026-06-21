# CodeMemory

Persistent Repository Intelligence for AI Coding Agents.

Stop making AI re-read your codebase. Give it memory instead.

---

## 🚀 Why CodeMemory?

CodeMemory is a repository intelligence platform that allows AI coding agents to understand large codebases without repeatedly scanning thousands of files.

It transforms source code into a persistent knowledge graph, semantic index, architecture map, engineering memory, and MCP interface that any AI agent can query.

### Why not just use RAG?

Traditional AI coding tools repeatedly scan repositories. Every session they:

* read files
* build context
* reconstruct architecture
* relearn dependencies

This wastes tokens and time.

CodeMemory creates a persistent intelligence layer that stores:

* repository structure
* dependency relationships
* architecture insights
* engineering decisions
* context packs
* semantic embeddings

AI agents query intelligence instead of repeatedly reading code.

---

## 🎯 The Problem

Modern AI coding agents repeatedly spend tokens understanding the same repository. Every new session requires:

* reading files
* reconstructing architecture
* discovering dependencies
* rebuilding context

This wastes time, compute, and context window.

CodeMemory solves this by creating a persistent intelligence layer that AI agents can query instead of repeatedly scanning the codebase.

---

## 📈 Performance Highlights

* **94.8%** Context Compression
* **100%** Deployment Readiness
* **100%** v1 Completion
* **109** Passing Tests
* **21+** MCP Tools
* **<16ms** Average MCP Response
* **<5s** Incremental Updates

---

## 🧠 Visual Architecture

```
Repository    │
            ▼ CodeMemory ──┬── Knowledge Graph
                              ├── Semantic Search
                              ├── Architecture Analysis
                              ├── Context Packs
                              ├── Agent Memory
                              └── Intelligence Layer
                                │
                                ▼ MCP Server
                                │
                                ▼ Cursor • Claude • Cline • Roo • Codex
```

---

## ⭐ What Makes It Different?

| Feature | CodeMemory | Typical RAG |
|---|:---:|:---:|
| Semantic Search | ✅ | ✅ |
| Knowledge Graph | ✅ | ❌ |
| Architecture Analysis | ✅ | ❌ |
| Change Impact Analysis | ✅ | ❌ |
| Context Packs | ✅ | ❌ |
| Agent Memory | ✅ | ❌ |
| Incremental Updates | ✅ | ❌ |
| MCP Native | ✅ | ❌ |

---

## 🛠️ MCP Tools

| Category | Tools |
|---|---|
| Project Intelligence | `get_project_summary`, `get_ai_context` |
| Architecture | `get_architecture_overview` |
| Search | `search_codebase` |
| Analysis | `get_change_impact` |
| Memory | `get_project_history` |
| Planning | `get_next_tasks` |
| Health | `get_repository_health` |

---

## 🚀 Quick Start

1. Install:
   ```bash
   pip install -e ".[dev]"
   ```
2. Initialize:
   ```bash
   codememory init
   ```
3. Scan the repo:
   ```bash
   codememory scan
   ```
4. Serve MCP:
   ```bash
   codememory serve /absolute/path/to/your/repo --stdio
   ```

---

## 🔧 Core Capabilities

* Persistent repo intelligence with a semantic knowledge layer
* Local FastEmbed embeddings for fast semantic search
* Graph-based dependency and symbol relationships
* Automated architecture and pattern analysis
* Incremental scanning for fast updates
* MCP-native server for AI agent integration

---

## 📚 Documentation

* `docs/architecture.md` — architecture overview
* `docs/module_map.md` — module map and AI context
* `docs/adr.md` — architecture decision records
* `docs/changelog.md` — changelog and release notes

---

## 📄 License

MIT

---

*Maintained by Babul Kumar*
