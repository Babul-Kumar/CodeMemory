"""MCP tool functions exposed by the CodeMemory server.

All functions return JSON-encoded strings or Markdown texts so they work both in HTTP mode
and in MCP stdio mode (Cursor / Cline / Claude Desktop).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Module-level reference to shared state ────────────────────────────────────
_engine: Any = None
_db: Any = None
_summarizer: Any = None
_repo_path: Any = None

def _set_state(engine: Any, db: Any, summarizer: Any, repo_path: Any = None) -> None:
    """Inject shared state into this module (called by app factory)."""
    global _engine, _db, _summarizer, _repo_path
    _engine = engine
    _db = db
    _summarizer = summarizer
    if repo_path:
        _repo_path = Path(repo_path)
    elif db and hasattr(db, "db_path"):
        # Fallback to infer repo path from DB location
        _repo_path = Path(db.db_path).parent.parent

def _get_intel_db():
    """Return a sqlite3 connection to intelligence.db if it exists."""
    if not _repo_path:
        return None
    db_path = _repo_path / ".ai" / "intelligence.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    return None

def _read_ai_file(filename: str) -> str:
    """Read a flat file from the .ai directory."""
    if not _repo_path:
        return json.dumps({"error": "Repository path not set"})
    file_path = _repo_path / ".ai" / filename
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return json.dumps({"error": f"File {filename} does not exist in .ai/. Please run 'codememory report' to generate it."})

# ── 1. Project Overview, Health & Risks ───────────────────────────────────────

async def get_project_summary() -> str:
    """Return the human-readable project summary Markdown."""
    return _read_ai_file("project_summary.md")

async def get_ai_context() -> str:
    """Return the ultra-compressed AI Context Sheet Markdown (<3000 tokens)."""
    return _read_ai_file("ai_context.md")

async def get_architecture_overview() -> str:
    """Return the system design, layers, boundaries, and key flows JSON."""
    return _read_ai_file("architecture_map.json")

async def get_repository_health() -> str:
    """Return health scores across Architecture, Maintainability, Quality, and Operations."""
    return _read_ai_file("health_score.json")

async def get_deployment_readiness() -> str:
    """Return the detailed deployment readiness report Markdown and score."""
    return _read_ai_file("deployment_report.md")

async def get_risk_report() -> str:
    """Return a comprehensive assessment of architecture, operational, and testing risks."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    risks = []
    
    # 1. Circular dependencies
    cursor = conn.execute("SELECT from_component, to_component FROM relationships WHERE rel_type = 'imports'")
    rels = cursor.fetchall()
    import networkx as nx
    dg = nx.DiGraph()
    for r in rels:
        dg.add_edge(r["from_component"], r["to_component"])
    try:
        cycles = list(nx.simple_cycles(dg))
        if cycles:
            risks.append({
                "category": "architecture",
                "severity": "Medium",
                "risk": f"Detected {len(cycles)} circular import cycles.",
                "details": [str(c) for c in cycles[:5]]
            })
    except Exception:
        pass
        
    # 2. Missing Ops
    cursor = conn.execute("SELECT name, details FROM features WHERE status = 'Missing'")
    missing = cursor.fetchall()
    for m in missing:
        risks.append({
            "category": "operational",
            "severity": "High",
            "risk": f"Missing critical deployment feature: {m['name']}",
            "details": m["details"]
        })
        
    # 3. TODO high density
    cursor = conn.execute("SELECT path, name, docstring FROM components WHERE docstring LIKE '%todo%' OR docstring LIKE '%fixme%'")
    todos = cursor.fetchall()
    if len(todos) > 5:
        risks.append({
            "category": "maintainability",
            "severity": "Low",
            "risk": f"High density of TODOs/FIXMEs ({len(todos)} found).",
            "details": [f"{t['path']}: {t['name']}" for t in todos[:5]]
        })
        
    conn.close()
    return json.dumps(risks, indent=2)

# ── 2. Directory & Component Queries ──────────────────────────────────────────

async def get_module_summary(module: str) -> str:
    """Return details and file list for a specific module or directory."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute(
        "SELECT name, kind, docstring, status FROM components WHERE path LIKE ? AND kind = 'file'",
        (f"%{module}%",)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return json.dumps({"error": f"No files or modules found matching '{module}'"})
        
    result = {
        "module": module,
        "file_count": len(rows),
        "files": [dict(r) for r in rows]
    }
    return json.dumps(result, indent=2)

async def explain_component(component: str) -> str:
    """Explain the purpose, dependencies, responsibilities, and related modules of a component."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute(
        "SELECT * FROM components WHERE name LIKE ?",
        (f"%{component}%",)
    )
    comps = [dict(r) for r in cursor.fetchall()]
    
    if not comps:
        conn.close()
        return json.dumps({"error": f"Component '{component}' not found"})
        
    main_comp = comps[0]
    comp_id = f"symbol:{main_comp['path']}:{main_comp['name']}" if main_comp['kind'] != 'file' else f"file:{main_comp['path']}"
    
    # Get dependencies
    cursor = conn.execute(
        "SELECT to_component, rel_type FROM relationships WHERE from_component = ?",
        (comp_id,)
    )
    deps = [dict(r) for r in cursor.fetchall()]
    
    # Get dependents
    cursor = conn.execute(
        "SELECT from_component, rel_type FROM relationships WHERE to_component = ?",
        (comp_id,)
    )
    rev_deps = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    result = {
        "component": main_comp,
        "dependencies": deps,
        "dependents": rev_deps
    }
    return json.dumps(result, indent=2)

async def get_important_files() -> str:
    """Return files ranked by connectivity and dependency degree."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute("SELECT from_component, to_component FROM relationships")
    rels = cursor.fetchall()
    
    degrees: dict[str, int] = {}
    for r in rels:
        f_file = r["from_component"].split(":")[1] if ":" in r["from_component"] else r["from_component"]
        t_file = r["to_component"].split(":")[1] if ":" in r["to_component"] else r["to_component"]
        degrees[f_file] = degrees.get(f_file, 0) + 1
        degrees[t_file] = degrees.get(t_file, 0) + 1
        
    sorted_files = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
    conn.close()
    
    return json.dumps([{"file": f, "connections": d} for f, d in sorted_files[:15]], indent=2)

async def get_system_hotspots() -> str:
    """Return files with high dependency degree, most imports, and highest change frequency."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute(
        "SELECT path, name, docstring FROM components WHERE kind = 'file'"
    )
    files = [dict(r) for r in cursor.fetchall()]
    
    # Rank by incoming relationships (in-degree)
    cursor = conn.execute(
        "SELECT to_component, COUNT(*) as cnt FROM relationships GROUP BY to_component"
    )
    in_degrees = {r["to_component"]: r["cnt"] for r in cursor.fetchall()}
    
    hotspots = []
    for f in files:
        file_id = f"file:{f['path']}"
        score = in_degrees.get(file_id, 0)
        hotspots.append({
            "path": f["path"],
            "name": f["name"],
            "incoming_edges": score,
            "complexity_score": score * 10 + len(f["docstring"] or "") // 100
        })
        
    hotspots.sort(key=lambda x: x["complexity_score"], reverse=True)
    conn.close()
    return json.dumps(hotspots[:10], indent=2)

async def get_related_components(component: str) -> str:
    """Return dependencies, dependents, and neighboring graph nodes for impact analysis."""
    return await explain_component(component)

# ── 3. Dependency, Testing & Impact Analysis ─────────────────────────────────

async def get_dependency_graph() -> str:
    """Return file-to-file and module-to-module dependencies."""
    return _read_ai_file("dependency_graph.json")

async def get_change_impact(file: str) -> str:
    """Perform impact analysis showing affected modules, tests, APIs, and context packs if a file changes."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute("SELECT from_component, to_component, rel_type FROM relationships")
    rels = cursor.fetchall()
    
    # Build backward dependency map
    rev_deps: dict[str, list[str]] = {}
    for r in rels:
        f_file = r["from_component"].split(":")[1] if ":" in r["from_component"] else r["from_component"]
        t_file = r["to_component"].split(":")[1] if ":" in r["to_component"] else r["to_component"]
        if f_file != t_file:
            rev_deps.setdefault(t_file, []).append(f_file)
            
    # Traversal to find all affected files recursively
    affected = set()
    queue = [file]
    visited = set()
    
    while queue:
        curr = queue.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
        
        # Find matches containing the name
        for k, v in rev_deps.items():
            if curr in k or k in curr:
                for parent in v:
                    if parent not in affected:
                        affected.add(parent)
                        queue.append(parent)
                        
    conn.close()
    
    # Categorize impact
    tests_affected = [a for a in affected if "test" in a.lower()]
    modules_affected = list({Path(a).parent.name for a in affected})
    
    result = {
        "file_changed": file,
        "affected_count": len(affected),
        "affected_files": list(affected),
        "affected_tests": tests_affected,
        "affected_modules": modules_affected
    }
    return json.dumps(result, indent=2)

async def get_test_gaps() -> str:
    """Return untested modules, low coverage areas, and critical paths lacking tests."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute("SELECT path FROM components WHERE kind = 'file'")
    all_files = {r["path"] for r in cursor.fetchall()}
    
    # Get relationships
    cursor = conn.execute("SELECT from_component, to_component FROM relationships")
    rels = cursor.fetchall()
    
    test_files = {f for f in all_files if "tests/" in f or "test_" in f}
    src_files = all_files - test_files
    
    # Check which files have references from test files
    tested_files = set()
    for r in rels:
        f_file = r["from_component"].split(":")[1] if ":" in r["from_component"] else r["from_component"]
        t_file = r["to_component"].split(":")[1] if ":" in r["to_component"] else r["to_component"]
        if f_file in test_files:
            tested_files.add(t_file)
            
    untested = src_files - tested_files
    conn.close()
    
    result = {
        "untested_files_count": len(untested),
        "untested_files": list(untested),
        "coverage_estimate_percentage": round((len(tested_files) / len(src_files) * 100), 1) if src_files else 100.0
    }
    return json.dumps(result, indent=2)

# ── 4. Action Plan, Tasks & Memory ────────────────────────────────────────────

async def get_feature_status() -> str:
    """Return implemented, partial, stubbed, and missing features."""
    return _read_ai_file("feature_status.json")

async def get_next_tasks() -> str:
    """Return the prioritized next tasks based on TODOs, gaps, and deployment blockers."""
    return _read_ai_file("task_index.json")

async def get_unfinished_work() -> str:
    """Combine TODOs, FIXMEs, stubbed functions, and partial features into a prioritized list."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute(
        "SELECT path, name, kind, docstring, status FROM components WHERE status IN ('Partial', 'Stubbed')"
    )
    gaps = [dict(r) for r in cursor.fetchall()]
    
    cursor = conn.execute(
        "SELECT path, name, docstring FROM components WHERE docstring LIKE '%todo%' OR docstring LIKE '%fixme%'"
    )
    todos = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    result = {
        "stubbed_or_partial_components": gaps,
        "todos_and_fixmes": todos
    }
    return json.dumps(result, indent=2)

async def get_context_pack(task: str) -> str:
    """Return (and cache) context packs containing files, summaries, dependencies needed for a task."""
    if not _repo_path:
        return json.dumps({"error": "Repository path not set"})
        
    task_clean = "".join(c for c in task if c.isalnum() or c in (" ", "_", "-")).strip().lower().replace(" ", "_")
    pack_path = _repo_path / ".ai" / "context_packs" / f"{task_clean}.json"
    
    if pack_path.exists():
        return pack_path.read_text(encoding="utf-8")
        
    # Generate dynamic context pack
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    # Simple keyword search on components
    cursor = conn.execute(
        "SELECT DISTINCT path, docstring FROM components WHERE path LIKE ? OR name LIKE ? OR docstring LIKE ?",
        (f"%{task}%", f"%{task}%", f"%{task}%")
    )
    matches = cursor.fetchall()
    
    important_files = list({r["path"] for r in matches})[:5]
    
    # Get dependencies
    dependencies = []
    for f in important_files:
        cursor = conn.execute(
            "SELECT DISTINCT to_component FROM relationships WHERE from_component = ? OR from_component = ?",
            (f"file:{f}", f)
        )
        for row in cursor.fetchall():
            dep = row["to_component"].split(":")[1] if ":" in row["to_component"] else row["to_component"]
            if dep not in important_files and dep not in dependencies:
                dependencies.append(dep)
                
    conn.close()
    
    pack = {
        "goal": f"Gather context for task: {task}",
        "important_files": important_files,
        "dependencies": dependencies,
        "architecture_notes": "Generated dynamically based on search terms.",
        "related_components": [],
        "known_constraints": "Review the project summary for overall guidelines."
    }
    
    # Cache it
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pack_path, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, indent=2)
        
    return json.dumps(pack, indent=2)

async def get_project_history() -> str:
    """Return architecture decisions and task history."""
    if not _repo_path:
        return json.dumps({"error": "Repository path not set"})
        
    adr_path = _repo_path / ".ai" / "agent_memory" / "architecture_decisions.md"
    if adr_path.exists():
        return adr_path.read_text(encoding="utf-8")
    return _read_ai_file("agent_memory/decisions.json")

# ── 5. Semantic Search Across Codebase ────────────────────────────────────────

async def search_codebase(query: str) -> str:
    """Semantic search across modules using embeddings_index.json."""
    if not _repo_path:
        return json.dumps({"error": "Repository path not set"})
        
    index_path = _repo_path / ".ai" / "embeddings_index.json"
    if not index_path.exists():
        return json.dumps({"error": "Embeddings index does not exist. Run 'codememory report' to generate it."})
        
    with open(index_path, "r", encoding="utf-8") as fh:
        embeddings = json.load(fh)
        
    # Generate search query hash vector
    import hashlib
    h = hashlib.sha256(query.encode()).digest()
    q_vec = [float((h[j % len(h)] - 128) / 128.0) for j in range(384)]
    norm = math.sqrt(sum(v*v for v in q_vec))
    if norm > 0:
        q_vec = [v/norm for v in q_vec]
        
    # Calculate cosine similarity
    results = []
    for entry in embeddings:
        e_vec = entry.get("embedding", [])
        if not e_vec:
            continue
        # dot product
        score = sum(q_vec[j] * e_vec[j] for j in range(384))
        results.append({
            "file_path": entry["file_path"],
            "summary": entry["summary"],
            "classes": entry["classes"],
            "functions": entry["functions"],
            "similarity_score": round(score, 3)
        })
        
    # Sort by similarity
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return json.dumps(results[:10], indent=2)

async def get_leftover_work() -> str:
    """Return remaining tasks, completed tasks, and completion percentage."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps({"error": "Intelligence DB not initialized"})
        
    cursor = conn.execute("SELECT * FROM leftover_tasks WHERE status = 'Remaining'")
    remaining = [dict(r) for r in cursor.fetchall()]
    
    cursor = conn.execute("SELECT * FROM leftover_tasks WHERE status = 'Completed' ORDER BY completed_at DESC")
    completed = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    rem_cnt = len(remaining)
    comp_cnt = len(completed)
    total = rem_cnt + comp_cnt
    comp_percentage = int((comp_cnt / total * 100)) if total > 0 else 100
    
    result = {
        "remaining_tasks": remaining,
        "completed_tasks": completed,
        "completion_percentage": comp_percentage
    }
    return json.dumps(result, indent=2)

# ── Compatibility Aliases ─────────────────────────────────────────────────────

async def search_memory(query: str, entity_types: list[str] | None = None) -> str:
    """Compat alias for search_codebase or full search."""
    return await search_codebase(query)

async def get_recent_changes() -> str:
    """Compat alias for changed files."""
    conn = _get_intel_db()
    if not conn:
        return json.dumps([])
    cursor = conn.execute("SELECT path, name, docstring FROM components WHERE kind = 'file' LIMIT 10")
    res = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return json.dumps(res, indent=2)

async def get_architecture() -> str:
    """Compat alias for get_architecture_overview."""
    return await get_architecture_overview()

async def get_health_status() -> str:
    """Return the service health status, repository path, database connection status, and basic statistics."""
    if not _db:
        return json.dumps({
            "status": "error",
            "message": "Database state is not initialized."
        }, indent=2)
        
    db_status = "connected"
    stats = {}
    try:
        stats = await _db.get_stats()
    except Exception as exc:
        db_status = f"error: {exc}"
        
    intel_status = "not initialized"
    intel_db_path = _repo_path / ".ai" / "intelligence.db" if _repo_path else None
    if intel_db_path and intel_db_path.exists():
        intel_status = "ready"
        
    return json.dumps({
        "status": "ok",
        "repo_path": str(_repo_path) if _repo_path else None,
        "database": db_status,
        "intelligence": intel_status,
        "stats": stats
    }, indent=2)
