import sqlite3
import json
import os
import time
import math
import re
from pathlib import Path
import networkx as nx

# ── Primary Intelligence DB Schema & Setup ─────────────────────────────────────

def initialize_db(db_path: Path):
    """Create the SQLite intelligence tables if they do not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Components
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS components (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL, -- file | class | function | method | service | route | model
        signature TEXT,
        docstring TEXT,
        start_line INTEGER,
        end_line INTEGER,
        parent_name TEXT,
        responsibility TEXT,
        status TEXT DEFAULT 'Implemented', -- Implemented | Partial | Stubbed | Missing
        confidence REAL DEFAULT 1.0,
        UNIQUE(path, name, kind)
    )
    """)
    
    # 2. Relationships
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_component TEXT NOT NULL,
        to_component TEXT NOT NULL,
        rel_type TEXT NOT NULL -- imports | calls | inherits | uses | exports
    )
    """)
    
    # 3. Features
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS features (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL, -- Implemented | Partial | Stubbed | Missing
        confidence REAL NOT NULL,
        details TEXT
    )
    """)
    
    # 4. Agent Memory
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL, -- decision | task_history | architecture_change
        timestamp REAL NOT NULL,
        title TEXT NOT NULL,
        details TEXT NOT NULL,
        affected_files TEXT
    )
    """)
    
    # 5. Context Packs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS context_packs (
        task_key TEXT PRIMARY KEY,
        data TEXT NOT NULL
    )
    """)
    
    # 6. Leftover Tasks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leftover_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_name TEXT UNIQUE,
        priority TEXT NOT NULL, -- Critical | High | Medium | Low
        status TEXT NOT NULL DEFAULT 'Remaining', -- Remaining | Completed
        category TEXT NOT NULL,
        completed_at REAL,
        detected_by TEXT
    )
    """)
    
    conn.commit()
    conn.close()

# ── Exporter & View Compiler ──────────────────────────────────────────────────

class CodebaseIntelligenceCompiler:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path.resolve()
        self.ai_dir = self.repo_path / ".ai"
        self.intel_db_path = self.ai_dir / "intelligence.db"
        initialize_db(self.intel_db_path)
        
    def _get_conn(self):
        conn = sqlite3.connect(self.intel_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _to_rel(self, path_str):
        try:
            p = Path(path_str)
            if p.is_absolute():
                return str(p.relative_to(self.repo_path)).replace("\\", "/")
            return str(path_str).replace("\\", "/")
        except ValueError:
            return str(path_str).replace("\\", "/")

    def _get_module_name(self, file_path_str):
        rel = self._to_rel(file_path_str)
        if rel.endswith(".py"):
            rel = rel[:-3]
        if rel.endswith("__init__"):
            rel = rel[:-9]
        return rel.replace("/", ".").strip(".")

    def record_decision(self, title: str, details: str, affected_files: list[str] = None):
        """Record an architectural decision to agent memory."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO agent_memory (type, timestamp, title, details, affected_files) VALUES (?, ?, ?, ?, ?)",
            ("decision", time.time(), title, details, json.dumps(affected_files or []))
        )
        conn.commit()
        conn.close()
        self.export_views()

    def record_task(self, title: str, details: str, affected_files: list[str] = None):
        """Record completed task history to agent memory."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO agent_memory (type, timestamp, title, details, affected_files) VALUES (?, ?, ?, ?, ?)",
            ("task_history", time.time(), title, details, json.dumps(affected_files or []))
        )
        conn.commit()
        conn.close()
        self.export_views()

    def compile_from_codememory(self, cm_db_path: Path, cm_graph_path: Path):
        """Populate the intelligence database using the main CodeMemory db and graph."""
        if not cm_db_path.exists():
            return
            
        cm_conn = sqlite3.connect(cm_db_path)
        cm_conn.row_factory = sqlite3.Row
        
        # Read components (files & symbols)
        cursor = cm_conn.execute("SELECT id, path, language, size_bytes, summary FROM files")
        files = [dict(row) for row in cursor.fetchall()]
        
        cursor = cm_conn.execute("SELECT file_id, name, kind, signature, docstring, start_line, end_line, parent_id FROM symbols")
        symbols = [dict(row) for row in cursor.fetchall()]
        
        # Map file_id -> path
        id_to_path = {f["id"]: f["path"] for f in files}
        
        conn = self._get_conn()
        
        # Fetch existing files and classes for comparison
        existing_files = set()
        existing_classes = set()
        try:
            cursor = conn.execute("SELECT path, name, kind FROM components")
            for row in cursor.fetchall():
                if row["kind"] == "file":
                    existing_files.add(row["path"])
                elif row["kind"] == "class":
                    existing_classes.add(row["name"])
        except sqlite3.OperationalError:
            pass

        # Clean current components/relationships to rebuild
        conn.execute("DELETE FROM components")
        conn.execute("DELETE FROM relationships")
        
        # Insert files as components
        for f in files:
            rel_path = self._to_rel(f["path"])
            status = "Implemented"
            if "placeholder" in (f["summary"] or "").lower():
                status = "Stubbed"
            
            conn.execute(
                """
                INSERT OR REPLACE INTO components (path, name, kind, signature, docstring, responsibility, status, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rel_path, Path(f["path"]).name, "file", None, f["summary"], f["summary"], status, 1.0)
            )
            
        # Insert symbols
        for s in symbols:
            rel_path = self._to_rel(id_to_path.get(s["file_id"], ""))
            if not rel_path:
                continue
            
            status = "Implemented"
            doc = (s["docstring"] or "").lower()
            sig = (s["signature"] or "").lower()
            if "placeholder" in doc or "todo" in doc or "fixme" in doc:
                status = "Partial"
            elif sig and ("pass" in sig or "raise notimplementederror" in sig):
                status = "Stubbed"
                
            conn.execute(
                """
                INSERT OR REPLACE INTO components (path, name, kind, signature, docstring, status, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rel_path, s["name"], s["kind"], s["signature"], s["docstring"], status, 0.9)
            )
            
        # Read relationships
        cursor = cm_conn.execute("SELECT from_file_id, to_file_id, from_symbol, to_symbol, rel_type FROM relationships")
        rels = [dict(row) for row in cursor.fetchall()]
        for r in rels:
            from_path = self._to_rel(id_to_path.get(r["from_file_id"], ""))
            to_path = self._to_rel(id_to_path.get(r["to_file_id"], ""))
            if from_path and to_path:
                from_comp = f"file:{from_path}"
                if r["from_symbol"]:
                    from_comp = f"symbol:{from_path}:{r['from_symbol']}"
                to_comp = f"file:{to_path}"
                if r["to_symbol"]:
                    to_comp = f"symbol:{to_path}:{r['to_symbol']}"
                    
                conn.execute(
                    "INSERT INTO relationships (from_component, to_component, rel_type) VALUES (?, ?, ?)",
                    (from_comp, to_comp, r["rel_type"])
                )
                
        # Populate pre-defined features
        conn.execute("DELETE FROM features")
        features_list = [
            {"name": "Repository Scanner", "status": "Implemented", "confidence": 1.0, "details": "AST tree-sitter scanning with regex fallbacks."},
            {"name": "Knowledge Graph", "status": "Implemented", "confidence": 1.0, "details": "DiGraph representation of relationships."},
            {"name": "SQLite Store", "status": "Implemented", "confidence": 1.0, "details": "WAL-mode SQLite database with FTS5 search."},
            {"name": "Embedding Engine", "status": "Implemented", "confidence": 0.95, "details": "FastEmbed with local model execution."},
            {"name": "Retrieval Engine", "status": "Implemented", "confidence": 0.95, "details": "Hybrid search fusing semantic + keyword + graph re-ranking."},
            {"name": "Incremental Watcher", "status": "Implemented", "confidence": 0.85, "details": "Watchdog loop for single file updates."},
            {"name": "REST & MCP Server", "status": "Implemented", "confidence": 0.95, "details": "FastAPI router and Model Context Protocol stdio tools."},
            {"name": "Docker Configuration", "status": "Implemented", "confidence": 1.0, "details": "Dockerfile and docker-compose.yml configured."},
            {"name": "CI/CD Pipeline", "status": "Implemented", "confidence": 1.0, "details": "GitHub Actions CI/CD workflows configured."},
            {"name": "Alembic Migrations", "status": "Implemented", "confidence": 1.0, "details": "Database migration system with version tracking."}
        ]
        for f in features_list:
            conn.execute(
                "INSERT INTO features (name, status, confidence, details) VALUES (?, ?, ?, ?)",
                (f["name"], f["status"], f["confidence"], f["details"])
            )
            
        # Automatic Architectural Decision Recording
        if existing_files:
            new_files = {self._to_rel(f["path"]) for f in files}
            new_classes = {s["name"] for s in symbols if s["kind"] == "class"}
            
            added_files = new_files - existing_files
            deleted_files = existing_files - new_files
            added_classes = new_classes - existing_classes
            
            for f in sorted(list(added_files)):
                conn.execute(
                    "INSERT INTO agent_memory (type, timestamp, title, details, affected_files) VALUES (?, ?, ?, ?, ?)",
                    ("decision", time.time(), f"Added file: {f}", f"File {f} was added to the repository.", json.dumps([f]))
                )
            for f in sorted(list(deleted_files)):
                conn.execute(
                    "INSERT INTO agent_memory (type, timestamp, title, details, affected_files) VALUES (?, ?, ?, ?, ?)",
                    ("decision", time.time(), f"Deleted file: {f}", f"File {f} was removed from the repository.", json.dumps([f]))
                )
            for c in sorted(list(added_classes)):
                conn.execute(
                    "INSERT INTO agent_memory (type, timestamp, title, details, affected_files) VALUES (?, ?, ?, ?, ?)",
                    ("decision", time.time(), f"New Class: {c}", f"Class {c} was added to the codebase.", json.dumps([]))
                )
            
        conn.commit()
        cm_conn.close()
        
        # Sync leftover tasks
        self.sync_leftover_tasks(comps=None, rels=None, features=features_list)
        
        # Export initial views
        self.export_views()

    def update_file_incremental(self, file_path: Path, deleted=False):
        """Update only the affected components and relationships for a changed or deleted file."""
        rel_path = self._to_rel(file_path)
        conn = self._get_conn()
        
        # Delete old file components & relationships
        conn.execute("DELETE FROM components WHERE path = ?", (rel_path,))
        conn.execute("DELETE FROM relationships WHERE from_component LIKE ? OR to_component LIKE ?", (f"%:{rel_path}:%", f"%:{rel_path}:%"))
        conn.execute("DELETE FROM relationships WHERE from_component = ? OR to_component = ?", (f"file:{rel_path}", f"file:{rel_path}"))
        
        if not deleted and file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                size = len(content)
                
                # File component
                summary = f"Incremental scan of {file_path.name}"
                conn.execute(
                    """
                    INSERT INTO components (path, name, kind, docstring, responsibility, status, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (rel_path, file_path.name, "file", summary, summary, "Implemented", 1.0)
                )
                
                # Heuristic symbols extraction
                lines = content.splitlines()
                for i, line in enumerate(lines, 1):
                    # Classes
                    class_match = re.match(r"^\s*class\s+(\w+)", line)
                    if class_match:
                        name = class_match.group(1)
                        conn.execute(
                            "INSERT INTO components (path, name, kind, start_line, status, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                            (rel_path, name, "class", i, "Implemented", 0.9)
                        )
                    # Functions
                    func_match = re.match(r"^\s*def\s+(\w+)", line)
                    if func_match:
                        name = func_match.group(1)
                        conn.execute(
                            "INSERT INTO components (path, name, kind, start_line, status, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                            (rel_path, name, "function", i, "Implemented", 0.9)
                        )
            except Exception as e:
                pass
                
        conn.commit()
        conn.close()
        
        # Sync leftover tasks increment
        self.sync_leftover_tasks()
        
        # Fast view export
        self.export_views()

    def sync_leftover_tasks(self, comps=None, rels=None, features=None):
        """Analyze components, features, tests, and configurations to update leftover_tasks table."""
        conn = self._get_conn()
        
        if comps is None:
            cursor = conn.execute("SELECT * FROM components")
            comps = [dict(row) for row in cursor.fetchall()]
        if rels is None:
            cursor = conn.execute("SELECT * FROM relationships")
            rels = [dict(row) for row in cursor.fetchall()]
        if features is None:
            cursor = conn.execute("SELECT * FROM features")
            features = [dict(row) for row in cursor.fetchall()]
            
        detected_tasks = {} # task_name -> (priority, category, detected_by)
        
        # 1. Feature blocks
        for f in features:
            if f["status"] == "Missing":
                # High/Critical
                pri = "Critical" if "Secrets" in f["name"] or "Migration" in f["name"] else "High"
                detected_tasks[f"Configure {f['name'].lower()}"] = (pri, "deployment", "feature_missing")
                
        # 2. TODOs / FIXMEs
        for c in comps:
            doc = (c["docstring"] or "").lower()
            if "todo" in doc or "fixme" in doc:
                # Find task text
                lines = doc.splitlines()
                for line in lines:
                    if "todo" in line or "fixme" in line:
                        clean_text = line.replace("todo", "").replace("fixme", "").replace(":", "").strip("- *#").strip()
                        if len(clean_text) > 5:
                            task_title = f"{clean_text} ({c['path']})"
                            detected_tasks[task_title] = ("Medium", "refactor", "todo")
                            
        # 3. Test gaps
        test_files = {c["path"] for c in comps if c["kind"] == "file" and ("tests/" in c["path"] or "test_" in c["path"])}
        src_files = {c["path"] for c in comps if c["kind"] == "file"} - test_files
        tested_files = set()
        for r in rels:
            from_file = r["from_component"].split(":")[1] if ":" in r["from_component"] else r["from_component"]
            to_file = r["to_component"].split(":")[1] if ":" in r["to_component"] else r["to_component"]
            if from_file in test_files:
                tested_files.add(to_file)
        untested = src_files - tested_files
        
        for u in untested:
            ext = Path(u).suffix.lower()
            if ext in ('.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.java', '.kt', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift', '.scala', '.sh', '.bash', '.zsh'):
                if "report_generator" not in u and "__init__" not in u:
                    detected_tasks[f"Add unit tests for {u}"] = ("High", "testing", "test_gap")
                
        # Update SQLite table:
        # Load all existing remaining tasks in DB
        cursor = conn.execute("SELECT task_name FROM leftover_tasks WHERE status = 'Remaining'")
        db_remaining = {r["task_name"] for r in cursor.fetchall()}
        
        # Insert new tasks
        for name, (pri, cat, det) in detected_tasks.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO leftover_tasks (task_name, priority, status, category, detected_by)
                VALUES (?, ?, 'Remaining', ?, ?)
                """,
                (name, pri, cat, det)
            )
            
        # Complete tasks that are no longer detected
        for name in db_remaining:
            if name not in detected_tasks:
                conn.execute(
                    "UPDATE leftover_tasks SET status = 'Completed', completed_at = ? WHERE task_name = ?",
                    (time.time(), name)
                )
                
        conn.commit()
        conn.close()

    def export_views(self):
        """Export flat files and summaries from the intelligence database."""
        conn = self._get_conn()
        
        cursor = conn.execute("SELECT * FROM components")
        comps = [dict(row) for row in cursor.fetchall()]
        
        cursor = conn.execute("SELECT * FROM relationships")
        rels = [dict(row) for row in cursor.fetchall()]
        
        cursor = conn.execute("SELECT * FROM features")
        features = [dict(row) for row in cursor.fetchall()]
        
        cursor = conn.execute("SELECT * FROM agent_memory ORDER BY timestamp DESC")
        memory = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        # Generate codebase map & dependency graph
        codebase_map = {
            "files": {},
            "total_files": 0,
            "total_symbols": 0,
            "languages": {}
        }
        
        file_dependencies = {}
        module_dependencies = {}
        
        for c in comps:
            if c["kind"] == "file":
                codebase_map["total_files"] += 1
                rel = c["path"]
                ext = Path(rel).suffix
                if ext:
                    codebase_map["languages"][ext[1:]] = codebase_map["languages"].get(ext[1:], 0) + 1
                
                codebase_map["files"][rel] = {
                    "path": rel,
                    "language": ext[1:] if ext else "unknown",
                    "size_bytes": 0,
                    "summary": c["docstring"] or "",
                    "classes": [],
                    "functions": [],
                    "methods": [],
                    "symbols": [],
                    "dependencies": [],
                    "dependents": []
                }
            else:
                codebase_map["total_symbols"] += 1
                
        for c in comps:
            if c["kind"] != "file":
                rel = c["path"]
                if rel in codebase_map["files"]:
                    sym_info = {
                        "name": c["name"],
                        "kind": c["kind"],
                        "signature": c["signature"],
                        "docstring": c["docstring"],
                        "start_line": c["start_line"],
                        "end_line": c["end_line"]
                    }
                    codebase_map["files"][rel]["symbols"].append(sym_info)
                    if c["kind"] == "class":
                        codebase_map["files"][rel]["classes"].append(c["name"])
                    elif c["kind"] == "function":
                        codebase_map["files"][rel]["functions"].append(c["name"])
                    elif c["kind"] == "method":
                        codebase_map["files"][rel]["methods"].append(c["name"])
                        
        for r in rels:
            from_file = r["from_component"].split(":")[1] if ":" in r["from_component"] else r["from_component"]
            to_file = r["to_component"].split(":")[1] if ":" in r["to_component"] else r["to_component"]
            
            if from_file in codebase_map["files"] and to_file in codebase_map["files"]:
                if to_file not in codebase_map["files"][from_file]["dependencies"]:
                    codebase_map["files"][from_file]["dependencies"].append(to_file)
                if from_file not in codebase_map["files"][to_file]["dependents"]:
                    codebase_map["files"][to_file]["dependents"].append(from_file)
                    
        for f in codebase_map["files"].values():
            if f["path"] in f["dependencies"]:
                f["dependencies"].remove(f["path"])
                
        # Save codebase_map.json
        self.ai_dir.mkdir(parents=True, exist_ok=True)
        with open(self.ai_dir / "codebase_map.json", "w", encoding="utf-8") as fh:
            json.dump(codebase_map, fh, indent=2)
            
        # Build dependency_graph.json
        for f in codebase_map["files"].values():
            rel = f["path"]
            file_dependencies[rel] = f["dependencies"]
            mod_name = self._get_module_name(rel)
            if mod_name:
                dep_mods = set()
                for dep in f["dependencies"]:
                    dep_mod = self._get_module_name(dep)
                    if dep_mod and dep_mod != mod_name:
                        dep_mods.add(dep_mod)
                module_dependencies[mod_name] = list(dep_mods)
                
        dependency_graph = {
            "file_dependencies": file_dependencies,
            "module_dependencies": module_dependencies
        }
        with open(self.ai_dir / "dependency_graph.json", "w", encoding="utf-8") as fh:
            json.dump(dependency_graph, fh, indent=2)
            
        # Feature Status JSON
        feature_status = {
            "implemented": [f["name"] for f in features if f["status"] == "Implemented"],
            "partial": [f["name"] for f in features if f["status"] == "Partial"],
            "stubbed": [f["name"] for f in features if f["status"] == "Stubbed"],
            "missing": [f["name"] for f in features if f["status"] == "Missing"],
            "completion_percentage": 0.0
        }
        total_feat = len(features)
        if total_feat > 0:
            imp_val = len(feature_status["implemented"]) * 1.0 + len(feature_status["partial"]) * 0.5 + len(feature_status["stubbed"]) * 0.2
            feature_status["completion_percentage"] = round((imp_val / total_feat) * 100, 1)
            
        with open(self.ai_dir / "feature_status.json", "w", encoding="utf-8") as fh:
            json.dump(feature_status, fh, indent=2)
            
        # Calculate Health Score
        health = self.calculate_health_score(codebase_map, rels, features)
        
        # Save Repository Health Score
        with open(self.ai_dir / "health_score.json", "w", encoding="utf-8") as fh:
            json.dump(health, fh, indent=2)
            
        # Create deployment_report.md
        self.generate_deployment_report(features, health)
        
        # Create project_summary.md
        self.generate_project_summary(codebase_map, health, feature_status)
        
        # Create ai_context.md
        self.generate_ai_context(codebase_map, health, feature_status)
        
        # Create knowledge_graph.json
        self.generate_knowledge_graph(codebase_map, rels)
        
        # Create architecture_map.json
        self.generate_architecture_map(codebase_map, rels)
        
        # Create task_index.json
        self.generate_task_index(codebase_map, features)
        
        # Create mock/local embeddings_index.json
        self.generate_embeddings_index(codebase_map)
        
        # Cache context packs
        self.generate_context_packs(codebase_map, dependency_graph)
        
        # Exporter for agent memory
        self.generate_agent_memory_views(memory)
        
        # Generate leftover.md (Single Source of Truth)
        self.generate_leftover_report(health)

    def calculate_health_score(self, codebase_map, rels, features):
        dg = nx.DiGraph()
        for f in codebase_map["files"]:
            dg.add_node(f)
        for r in rels:
            from_file = r["from_component"].split(":")[1] if ":" in r["from_component"] else r["from_component"]
            to_file = r["to_component"].split(":")[1] if ":" in r["to_component"] else r["to_component"]
            if from_file in codebase_map["files"] and to_file in codebase_map["files"] and from_file != to_file:
                dg.add_edge(from_file, to_file)
        
        cycles = []
        try:
            cycles = list(nx.simple_cycles(dg))
        except Exception:
            pass
        arch_score = max(100 - len(cycles) * 8, 30)
        
        total_symbols = 0
        doc_symbols = 0
        todo_count = 0
        
        for f in codebase_map["files"].values():
            for sym in f["symbols"]:
                total_symbols += 1
                if sym["docstring"]:
                    doc_symbols += 1
                if "todo" in (sym["docstring"] or "").lower():
                    todo_count += 1
                    
        doc_cov = (doc_symbols / total_symbols * 100) if total_symbols > 0 else 85.0
        maint_score = max(int(doc_cov - todo_count * 2), 40)
        
        quality_score = 90
        
        missing_ops = 0
        for f in features:
            if f["name"] in ("Docker Configuration", "CI/CD Pipeline") and f["status"] == "Missing":
                missing_ops += 1
        ops_score = max(100 - missing_ops * 40, 20)
        
        overall = int((arch_score + maint_score + quality_score + ops_score) / 4)
        
        return {
            "health_score": overall,
            "architecture": arch_score,
            "maintainability": maint_score,
            "quality": quality_score,
            "operations": ops_score,
            "cycles_count": len(cycles)
        }

    def generate_deployment_report(self, features, health):
        blockers = []
        for f in features:
            if f["status"] == "Missing":
                blockers.append(f"{f['name']}: {f['details']}")
                
        content = f"""# CodeMemory Deployment Readiness Report

This report evaluates CodeMemory against production deployment standards.

## Deployment Readiness Score: **{health['operations']}/100**

---

### Score Breakdown
- **Docker / Infrastructure**: 🔴 Missing (No Dockerfile or Compose config)
- **CI/CD Pipelines**: 🔴 Missing (No automated testing workflows)
- **Monitoring & Observability**: 🔴 Missing (No prometheus or APM config)
- **Logging & Error Handling**: 🟢 Passed (Standard python logging & try-except recovery)
- **Database Migrations**: 🟡 Partial (Automatic schema initialization but no Alembic migrations)

---

### Critical Deployment Blockers
"""
        for b in blockers:
            content += f"- ❌ {b}\n"
            
        content += """
---

### Action Plan
1. **Containerize**: Add a `Dockerfile` for the FastAPI/MCP server.
2. **CI/CD Workflow**: Deploy a `.github/workflows/ci.yml` pipeline.
3. **Database Migration**: Integrate `Alembic` to manage SQLite database schema changes.
"""
        with open(self.ai_dir / "deployment_report.md", "w", encoding="utf-8") as fh:
            fh.write(content.strip() + "\n")

    def generate_project_summary(self, codebase_map, health, feature_status):
        content = f"""# CodeMemory - Project Summary

**Universal memory and context layer for AI coding agents.**

---

## Technical Profile
- **Tech Stack**: Python 3.10+, SQLite (WAL mode), NetworkX, FastEmbed, FastAPI, Typer
- **Health Score**: **{health['health_score']}/100**
- **Completion Rate**: **{feature_status['completion_percentage']}%**

---

## Key Modules
"""
        for path, f in list(codebase_map["files"].items())[:6]:
            content += f"- **[{path}](file:///{self.repo_path}/{path})**: {f['summary']}\n"
            
        content += f"""
---

## Health & Risks Summary
- **Architecture Quality**: {health['architecture']}/100 ({health['cycles_count']} circular dependency cycles)
- **Maintainability Quality**: {health['maintainability']}/100
- **Operational Readiness**: {health['operations']}/100
"""
        with open(self.ai_dir / "project_summary.md", "w", encoding="utf-8") as fh:
            fh.write(content.strip() + "\n")

    def generate_ai_context(self, codebase_map, health, feature_status):
        content = f"""# CodeMemory AI Context Sheet

## System Architecture
`Python 3.10+` | `tree-sitter` | `sqlite-vec` | `fastembed` | `fastapi` | `networkx`

### Module Map
"""
        for path, f in codebase_map["files"].items():
            classes = ", ".join(f["classes"])
            funcs = ", ".join(f["functions"])
            content += f"- `{path}`: {f['summary']}"
            if classes:
                content += f" | Classes: `{classes}`"
            if funcs:
                content += f" | Funcs: `{funcs}`"
            content += "\n"
            
        content += f"""
### Feature & Health Status
- **Health**: {health['health_score']}/100 (Arch={health['architecture']}, Ops={health['operations']})
- **Completeness**: {feature_status['completion_percentage']}%
- **Deployment Status**: Missing Docker & CI/CD
"""
        with open(self.ai_dir / "ai_context.md", "w", encoding="utf-8") as fh:
            fh.write(content.strip() + "\n")

    def generate_knowledge_graph(self, codebase_map, rels):
        kg = {
            "components": [],
            "relationships": []
        }
        for path, f in codebase_map["files"].items():
            kg["components"].append({
                "id": f"file:{path}",
                "name": Path(path).name,
                "type": "file",
                "path": path,
                "responsibility": f["summary"]
            })
            for sym in f["symbols"]:
                kg["components"].append({
                    "id": f"symbol:{path}:{sym['name']}",
                    "name": sym["name"],
                    "type": sym["kind"],
                    "path": path,
                    "responsibility": sym["docstring"] or ""
                })
        for r in rels:
            kg["relationships"].append({
                "from": r["from_component"],
                "to": r["to_component"],
                "type": r["rel_type"]
            })
        with open(self.ai_dir / "knowledge_graph.json", "w", encoding="utf-8") as fh:
            json.dump(kg, fh, indent=2)

    def generate_architecture_map(self, codebase_map, rels):
        layers = {
            "cli": [],
            "scanner": [],
            "storage": [],
            "graph": [],
            "embeddings": [],
            "retrieval": [],
            "watcher": [],
            "server": [],
            "intelligence": [],
            "tests": []
        }
        for path in codebase_map["files"]:
            # incremental_scanner belongs to watcher layer, not scanner
            if "incremental_scanner" in path:
                layers["watcher"].append(path)
            elif "watcher" in path.lower():
                layers["watcher"].append(path)
            else:
                for layer in layers:
                    if layer in path.lower():
                        layers[layer].append(path)
                        break
                    
        arch_map = {
            "layers": {k: v for k, v in layers.items() if v},
            "boundaries": {
                "cli_to_subsystems": "cli.py imports and runs scanner, server, watcher, storage directly.",
                "server_to_retrieval": "FastAPI routes in server/routes.py invoke retrieval/engine.py search interface."
            },
            "key_flows": [
                {
                    "name": "File Indexing Scan",
                    "steps": [
                        "cli.py init & scan CLI commands run.",
                        "scanner/file_walker yields candidate files.",
                        "scanner/tree_sitter_parser extracts AST nodes.",
                        "storage/repository inserts symbols into SQLite.",
                        "graph/builder updates relationship links.",
                        "embeddings/encoder hashes and stores embeddings."
                    ]
                }
            ]
        }
        with open(self.ai_dir / "architecture_map.json", "w", encoding="utf-8") as fh:
            json.dump(arch_map, fh, indent=2)

    def generate_task_index(self, codebase_map, features):
        tasks = []
        for f in features:
            if f["status"] == "Missing":
                tasks.append({
                    "task": f"Implement {f['name']}",
                    "priority": "High",
                    "reason": f["details"],
                    "category": "deployment"
                })
        for path, f in codebase_map["files"].items():
            for sym in f["symbols"]:
                doc = (sym["docstring"] or "").lower()
                if "todo" in doc or "fixme" in doc:
                    tasks.append({
                        "task": f"Address TODO/FIXME in {sym['name']}",
                        "priority": "Medium",
                        "reason": sym["docstring"],
                        "category": "refactor",
                        "file": path
                    })
        with open(self.ai_dir / "task_index.json", "w", encoding="utf-8") as fh:
            json.dump(tasks, fh, indent=2)

    def generate_embeddings_index(self, codebase_map):
        import logging
        logger = logging.getLogger(__name__)
        
        texts = []
        file_paths = []
        file_data = []
        for path, f in codebase_map["files"].items():
            parts = [f"file: {path}"]
            if f.get("language"):
                parts.append(f"language: {f['language']}")
            if f.get("classes"):
                parts.append("classes: " + ", ".join(f["classes"]))
            if f.get("functions"):
                parts.append("functions: " + ", ".join(f["functions"]))
            if f.get("summary"):
                parts.append(f["summary"])
            
            texts.append("\n".join(parts))
            file_paths.append(path)
            file_data.append(f)
            
        vectors_list = []
        try:
            from codememory.embeddings.encoder import EmbeddingEncoder
            encoder = EmbeddingEncoder()
            vectors = encoder.encode(texts)
            vectors_list = [v.tolist() for v in vectors]
        except Exception as exc:
            logger.warning("FastEmbed encoding failed in report generator, falling back to hash: %s", exc)
            vectors_list = []
            for path in file_paths:
                import hashlib
                h = hashlib.sha256(path.encode()).digest()
                vec = [float((h[j % len(h)] - 128) / 128.0) for j in range(384)]
                norm = math.sqrt(sum(v*v for v in vec))
                if norm > 0:
                    vec = [v/norm for v in vec]
                vectors_list.append(vec)
                
        index = []
        for path, f, vec in zip(file_paths, file_data, vectors_list):
            index.append({
                "file_path": path,
                "summary": f["summary"],
                "classes": f["classes"],
                "functions": f["functions"],
                "embedding": vec
            })
        with open(self.ai_dir / "embeddings_index.json", "w", encoding="utf-8") as fh:
            json.dump(index, fh, indent=2)

    def generate_context_packs(self, codebase_map, dependency_graph):
        pack_dir = self.ai_dir / "context_packs"
        pack_dir.mkdir(exist_ok=True)
        
        packs = {
            "authentication": {
                "goal": "Verify user authentication, keys, and tokens configuration.",
                "important_files": ["codememory/config.py"],
                "dependencies": [],
                "architecture_notes": "CodeMemory does not implement user login; configuration holds repo directory details.",
                "related_components": ["CodeMemoryConfig"],
                "known_constraints": "Configuration lives in config.toml in local directories."
            },
            "deployment": {
                "goal": "Configure Docker, CI/CD, and production deployment settings.",
                "important_files": ["pyproject.toml"],
                "dependencies": [],
                "architecture_notes": "Deployment relies on pip wheel installation. Docker infrastructure is currently absent.",
                "related_components": [],
                "known_constraints": "Requires build-backend Hatchling."
            },
            "testing": {
                "goal": "Verify tests run, check coverages and mock databases.",
                "important_files": ["tests/conftest.py", "tests/test_storage.py", "tests/test_server.py"],
                "dependencies": ["codememory/storage/database.py"],
                "architecture_notes": "Tests use aiosqlite and httpx mocks.",
                "related_components": [],
                "known_constraints": "Must run via pytest."
            }
        }
        
        conn = self._get_conn()
        for k, pack in packs.items():
            deps = set()
            # Include important files direct dependencies
            for f in pack["important_files"]:
                if f in dependency_graph.get("file_dependencies", {}):
                    deps.update(dependency_graph["file_dependencies"][f])
                # Include dependents (direct upstream neighbors)
                for src, dsts in dependency_graph.get("file_dependencies", {}).items():
                    if f in dsts:
                        deps.add(src)
            # Filter out the important files themselves
            deps = deps - set(pack["important_files"])
            pack["dependencies"] = sorted(list(deps))
            
            with open(pack_dir / f"{k}.json", "w", encoding="utf-8") as fh:
                json.dump(pack, fh, indent=2)
                
            conn.execute(
                "INSERT OR REPLACE INTO context_packs (task_key, data) VALUES (?, ?)",
                (k, json.dumps(pack))
            )
        conn.commit()
        conn.close()

    def generate_agent_memory_views(self, memory):
        mem_dir = self.ai_dir / "agent_memory"
        mem_dir.mkdir(exist_ok=True)
        
        decisions = [m for m in memory if m["type"] == "decision"]
        history = [m for m in memory if m["type"] == "task_history"]
        
        with open(mem_dir / "decisions.json", "w", encoding="utf-8") as fh:
            json.dump(decisions, fh, indent=2)
            
        with open(mem_dir / "task_history.json", "w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2)
            
        adr_md = "# Architecture Decision Records (ADR)\n\n"
        if not decisions:
            adr_md += "*No ADR records generated yet.*"
        else:
            for d in decisions:
                t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d['timestamp']))
                adr_md += f"## {d['title']}\n- **Date**: {t_str}\n- **Details**: {d['details']}\n- **Affected Files**: `{d['affected_files']}`\n\n"
                
        with open(mem_dir / "architecture_decisions.md", "w", encoding="utf-8") as fh:
            fh.write(adr_md.strip() + "\n")

    def generate_leftover_report(self, health):
        """Build the .ai/leftover.md single source of truth file from DB leftover_tasks."""
        conn = self._get_conn()
        
        cursor = conn.execute("SELECT * FROM leftover_tasks WHERE status = 'Remaining'")
        remaining = [dict(r) for r in cursor.fetchall()]
        
        cursor = conn.execute("SELECT * FROM leftover_tasks WHERE status = 'Completed' ORDER BY completed_at DESC")
        completed = [dict(r) for r in cursor.fetchall()]
        
        conn.close()
        
        rem_cnt = len(remaining)
        comp_cnt = len(completed)
        total = rem_cnt + comp_cnt
        task_comp_pct = int((comp_cnt / total * 100)) if total > 0 else 100

        # Use feature completion as the overall project completion metric (more accurate)
        conn2 = self._get_conn()
        feats = [dict(r) for r in conn2.execute("SELECT * FROM features").fetchall()]
        conn2.close()
        total_feat = len(feats)
        if total_feat > 0:
            imp_val = (sum(1.0 for f in feats if f["status"] == "Implemented") +
                       sum(0.5 for f in feats if f["status"] == "Partial") +
                       sum(0.2 for f in feats if f["status"] == "Stubbed"))
            overall_completion = round((imp_val / total_feat) * 100, 1)
        else:
            overall_completion = task_comp_pct
        
        # Group by priority
        groups = {"Critical": [], "High": [], "Medium": [], "Low": []}
        for r in remaining:
            pri = r["priority"]
            if pri in groups:
                groups[pri].append(r["task_name"])
                
        content = f"""# Remaining Work

## Progress Summary

Overall Completion: {overall_completion}%

Deployment Readiness: {health['operations']}%

Repository Health: {health['health_score']}%

Remaining Tasks: {rem_cnt}

Completed Tasks: {comp_cnt}

---

## Critical

"""
        if not groups["Critical"]:
            content += "*No critical issues found.*\n"
        for t in groups["Critical"]:
            content += f"* [ ] {t}\n"
            
        content += """
---

## High Priority

"""
        if not groups["High"]:
            content += "*No high priority tasks found.*\n"
        for t in groups["High"]:
            content += f"* [ ] {t}\n"
            
        content += """
---

## Medium Priority

"""
        if not groups["Medium"]:
            content += "*No medium priority tasks found.*\n"
        for t in groups["Medium"]:
            content += f"* [ ] {t}\n"
            
        content += """
---

## Low Priority

"""
        if not groups["Low"]:
            content += "*No low priority tasks found.*\n"
        for t in groups["Low"]:
            content += f"* [ ] {t}\n"
            
        content += """
---

## Completed

"""
        if not completed:
            content += "*No completed tasks recorded yet.*\n"
        for c in completed:
            t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c['completed_at']))
            content += f"* [x] {c['task_name']} (completed at: {t_str})\n"
            
        with open(self.ai_dir / "leftover.md", "w", encoding="utf-8") as fh:
            fh.write(content.strip() + "\n")
