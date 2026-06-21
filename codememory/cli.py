"""CodeMemory CLI — entry point for the ``codememory`` command."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="codememory",
    help="Universal memory and context layer for AI coding agents.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()

_HEADER = """[bold cyan]
 ██████╗ ██████╗ ██████╗ ███████╗███╗   ███╗███████╗███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝████╗ ████║██╔════╝████╗ ████║██╔═══██╗██╔══██╗╚██╗ ██╔╝
██║     ██║   ██║██║  ██║█████╗  ██╔████╔██║█████╗  ██╔████╔██║██║   ██║██████╔╝ ╚████╔╝
██║     ██║   ██║██║  ██║██╔══╝  ██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║██║   ██║██╔══██╗  ╚██╔╝
╚██████╗╚██████╔╝██████╔╝███████╗██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║╚██████╔╝██║  ██║   ██║
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝
[/bold cyan]
[dim]Analyze Once. Remember Forever.[/dim]
"""


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


# ── init ───────────────────────────────────────────────────────────────────────

@app.command()
def init(
    repo: Path = typer.Argument(Path("."), help="Repository path to initialise."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Initialise CodeMemory for a repository and print agent config snippets."""
    _setup_logging(verbose)
    repo_path = repo.resolve()

    console.print(_HEADER)

    from codememory.config import get_repo_data_dir, get_repo_hash, save_config, CodeMemoryConfig

    data_dir = get_repo_data_dir(repo_path)
    data_dir.mkdir(parents=True, exist_ok=True)
    save_config(repo_path, CodeMemoryConfig())

    console.print(Panel(
        f"[green]✓[/green] Initialised CodeMemory for [cyan]{repo_path}[/cyan]\n"
        f"[dim]Data directory: {data_dir}[/dim]",
        title="[bold]CodeMemory Init[/bold]",
        border_style="cyan",
    ))

    repo_hash = get_repo_hash(repo_path)

    # Show MCP config snippets
    cursor_cfg = json.dumps({
        "mcpServers": {
            "codememory": {
                "command": "codememory",
                "args": ["serve", str(repo_path), "--stdio"],
            }
        }
    }, indent=2)

    claude_cfg = json.dumps({
        "mcpServers": {
            "codememory": {
                "command": "codememory",
                "args": ["serve", str(repo_path), "--stdio"],
            }
        }
    }, indent=2)

    console.print(Panel(
        f"[bold]Cursor[/bold] → add to [cyan].cursor/mcp.json[/cyan]:\n"
        f"[dim]{cursor_cfg}[/dim]\n\n"
        f"[bold]Claude Desktop[/bold] → add to [cyan]%APPDATA%\\Claude\\claude_desktop_config.json[/cyan]:\n"
        f"[dim]{claude_cfg}[/dim]",
        title="[bold]MCP Agent Configuration[/bold]",
        border_style="yellow",
    ))

    console.print("\n[bold green]Next step:[/bold green] run [cyan]codememory scan[/cyan] to index your repository.\n")


# ── scan ───────────────────────────────────────────────────────────────────────

@app.command()
def scan(
    repo: Path = typer.Argument(Path("."), help="Repository path to scan."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Scan and index a repository into the CodeMemory knowledge store."""
    _setup_logging(verbose)
    start = time.time()
    asyncio.run(_scan(repo.resolve(), start))


async def _scan(repo_path: Path, start: float) -> None:
    from codememory.config import load_config, get_repo_data_dir
    from codememory.scanner import RepositoryScanner
    from codememory.storage.database import Database
    from codememory.storage.repository import CodeRepository
    from codememory.graph.builder import GraphBuilder
    from codememory.graph.relationships import RelationshipDetector
    from codememory.graph.serializer import GraphSerializer
    from codememory.embeddings.encoder import EmbeddingEncoder
    from codememory.embeddings.indexer import EmbeddingIndexer
    from codememory.intelligence.summarizer import FileSummarizer
    from codememory.constants import GRAPH_FILENAME

    config = load_config(repo_path)
    data_dir = get_repo_data_dir(repo_path)
    db_path = Database.get_db_path(repo_path)

    console.print(f"\n[bold green]Scanning[/bold green] [cyan]{repo_path}[/cyan]")
    console.print(f"[dim]Data stored in: {data_dir}[/dim]\n")

    async with Database(db_path) as db:
        repo_store = CodeRepository(repo_path, db)
        scanner = RepositoryScanner(repo_path, config)
        summarizer = FileSummarizer()
        encoder = EmbeddingEncoder(config.embedding_model)
        indexer = EmbeddingIndexer()
        builder = GraphBuilder()
        scan_results = []

        async for result in scanner.scan_repository():
            result.file_info.summary = summarizer.summarize_file(result)
            await repo_store.upsert_file(result)
            await indexer.index_scan_result(db, encoder, result)
            scan_results.append(result)

        # Detect and store relationships
        detector = RelationshipDetector(repo_path)
        relationships = detector.detect_relationships(scan_results)
        for rel in relationships:
            await repo_store.upsert_relationship(rel)

        # Build and save graph
        G = builder.build_from_scan_results(scan_results)
        graph_path = data_dir / GRAPH_FILENAME
        GraphSerializer.save(G, graph_path)

        stats = await repo_store.get_project_stats()

        # Compile codebase intelligence layer
        try:
            console.print("\n[bold green]Compiling Codebase Intelligence Layer...[/bold green]")
            from codememory.intelligence.report_generator import CodebaseIntelligenceCompiler
            compiler = CodebaseIntelligenceCompiler(repo_path)
            compiler.compile_from_codememory(db_path, graph_path)
            console.print("[green]✓ Intelligence Layer compiled successfully at .ai/[/green]\n")
        except Exception as exc:
            console.print(f"[red]✗ Failed to compile Intelligence Layer: {exc}[/red]\n")

    elapsed = time.time() - start
    table = Table(title="[bold]Scan Complete[/bold]", show_lines=True, border_style="cyan")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="yellow")
    table.add_row("Files indexed", str(stats["total_files"]))
    table.add_row("Symbols found", str(stats["total_symbols"]))
    table.add_row("Time taken", f"{elapsed:.1f}s")
    for lang, count in list(stats.get("languages", {}).items())[:6]:
        table.add_row(f"  {lang or 'unknown'}", str(count))
    console.print(table)


# ── watch ──────────────────────────────────────────────────────────────────────

@app.command()
def watch(
    repo: Path = typer.Argument(Path("."), help="Repository path to watch."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Watch a repository for changes and incrementally re-index modified files."""
    _setup_logging(verbose)
    console.print(f"\n[bold green]Watching[/bold green] [cyan]{repo.resolve()}[/cyan] for changes…")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")
    asyncio.run(_watch(repo.resolve()))


async def _watch(repo_path: Path) -> None:
    from codememory.watcher import IncrementalScanner
    from codememory.storage.database import Database
    from codememory.embeddings.encoder import EmbeddingEncoder
    from codememory.config import load_config

    config = load_config(repo_path)
    db_path = Database.get_db_path(repo_path)

    async with Database(db_path) as db:
        encoder = EmbeddingEncoder(config.embedding_model)
        watcher = IncrementalScanner(repo_path, db, encoder)
        await watcher.run_watch_loop(repo_path)


# ── serve ──────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    repo: Path = typer.Argument(Path("."), help="Repository path to serve."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
    stdio: bool = typer.Option(False, "--stdio", help="Run MCP server in stdio mode."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Start the CodeMemory MCP + REST server."""
    _setup_logging(verbose)
    repo_path = repo.resolve()

    if stdio:
        console.print("[bold cyan]Starting MCP stdio server…[/bold cyan]")
        from codememory.server.app import get_mcp_server
        mcp = get_mcp_server(repo_path)
        mcp.run(transport="stdio")
    else:
        console.print(
            Panel(
                f"[green]REST API:[/green]  http://{host}:{port}\n"
                f"[green]API Docs:[/green]  http://{host}:{port}/docs\n"
                f"[green]MCP SSE:[/green]   http://{host}:{port}/mcp",
                title="[bold]CodeMemory Server[/bold]",
                border_style="cyan",
            )
        )
        import uvicorn
        from codememory.server.app import create_app
        uvicorn.run(create_app(repo_path), host=host, port=port)


# ── query ──────────────────────────────────────────────────────────────────────

@app.command()
def query(
    search_query: str = typer.Argument(..., help="Search query."),
    repo: Path = typer.Option(Path("."), "--repo", "-r", help="Repository path."),
    max_results: int = typer.Option(10, "--max-results", "-n"),
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Query the indexed codebase for relevant files and symbols."""
    _setup_logging(verbose)
    asyncio.run(_query(search_query, repo.resolve(), max_results, output_json))


async def _query(query_str: str, repo_path: Path, max_results: int, output_json: bool) -> None:
    from codememory.storage.database import Database
    from codememory.storage.repository import CodeRepository
    from codememory.embeddings.encoder import EmbeddingEncoder
    from codememory.embeddings.searcher import EmbeddingSearcher
    from codememory.config import load_config

    config = load_config(repo_path)
    db_path = Database.get_db_path(repo_path)

    async with Database(db_path) as db:
        repo_store = CodeRepository(repo_path, db)
        encoder = EmbeddingEncoder(config.embedding_model)
        searcher = EmbeddingSearcher()

        query_vec = encoder.encode_query(query_str)
        vec_results = await searcher.search(db, query_vec, limit=max_results)
        fts_results = await repo_store.search_fts(query_str, limit=max_results)

    # Merge deduplicated
    seen: dict[str, dict] = {}
    for r in vec_results:
        fp = r.get("file_path", "")
        if fp:
            seen[fp] = {"file_path": fp, "score": f"{r['score']:.3f}", "match": "semantic"}
    for r in fts_results:
        fp = r.get("file_path", "")
        if fp and fp not in seen:
            seen[fp] = {"file_path": fp, "score": "FTS", "match": r.get("snippet", "")[:60]}

    merged = list(seen.values())[:max_results]

    if output_json:
        console.print(json.dumps(merged, indent=2))
        return

    table = Table(title=f"Results for: [cyan]{query_str!r}[/cyan]", show_lines=True, border_style="cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("File", style="cyan")
    table.add_column("Score", justify="right", style="yellow")
    table.add_column("Match", style="dim")
    for i, r in enumerate(merged, 1):
        table.add_row(str(i), r["file_path"], str(r["score"]), r["match"])
    console.print(table)


# ── status ─────────────────────────────────────────────────────────────────────

@app.command()
def status(
    repo: Path = typer.Option(Path("."), "--repo", "-r", help="Repository path."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Show the current scan status and statistics for a repository."""
    _setup_logging(verbose)
    asyncio.run(_status(repo.resolve()))


async def _status(repo_path: Path) -> None:
    import datetime
    from codememory.storage.database import Database
    from codememory.storage.repository import CodeRepository
    from codememory.config import get_repo_data_dir, get_repo_hash

    data_dir = get_repo_data_dir(repo_path)
    db_path = Database.get_db_path(repo_path)

    if not db_path.exists():
        console.print(
            Panel(
                f"[yellow]No index found for[/yellow] [cyan]{repo_path}[/cyan]\n"
                "Run [bold cyan]codememory scan[/bold cyan] to index this repository.",
                border_style="yellow",
            )
        )
        return

    db_size_kb = db_path.stat().st_size / 1024

    async with Database(db_path) as db:
        repo_store = CodeRepository(repo_path, db)
        stats = await repo_store.get_project_stats()

    last_ts = stats.get("last_indexed")
    last_str = (
        datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S")
        if last_ts else "Never"
    )

    table = Table(title="[bold]CodeMemory Status[/bold]", show_lines=True, border_style="cyan")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="yellow")
    table.add_row("Repository", str(repo_path))
    table.add_row("Repo hash", get_repo_hash(repo_path))
    table.add_row("Data directory", str(data_dir))
    table.add_row("DB size", f"{db_size_kb:.1f} KB")
    table.add_row("Files indexed", str(stats["total_files"]))
    table.add_row("Symbols found", str(stats["total_symbols"]))
    table.add_row("Last scanned", last_str)
    for lang, count in list(stats.get("languages", {}).items())[:5]:
        table.add_row(f"  {lang or 'unknown'}", str(count))
    console.print(table)


# ── reset ──────────────────────────────────────────────────────────────────────

@app.command()
def reset(
    repo: Path = typer.Argument(Path("."), help="Repository path."),
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation prompt."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Delete all stored CodeMemory data for a repository."""
    _setup_logging(verbose)
    from codememory.config import get_repo_data_dir
    import shutil

    repo_path = repo.resolve()
    data_dir = get_repo_data_dir(repo_path)

    if not data_dir.exists():
        console.print(f"[yellow]No data found for[/yellow] [cyan]{repo_path}[/cyan]")
        raise typer.Exit(0)

    if not confirm:
        typer.confirm(
            f"Delete all CodeMemory data for {repo_path}?\n  ({data_dir})",
            abort=True,
        )

    shutil.rmtree(data_dir)
    console.print(f"[green]✓[/green] Deleted [cyan]{data_dir}[/cyan]")


# ── report ─────────────────────────────────────────────────────────────────────

@app.command()
def report(
    repo: Path = typer.Argument(Path("."), help="Repository path."),
    incremental: bool = typer.Option(False, "--incremental", help="Run incremental update."),
    changed_file: list[Path] = typer.Option([], "--file", "-f", help="File(s) changed for incremental update."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Compile or update the Codebase Intelligence Platform Layer in .ai/."""
    _setup_logging(verbose)
    repo_path = repo.resolve()
    
    from codememory.config import get_repo_data_dir
    from codememory.storage.database import Database
    
    data_dir = get_repo_data_dir(repo_path)
    db_path = Database.get_db_path(repo_path)
    graph_path = data_dir / "graph.json"
    
    from codememory.intelligence.report_generator import CodebaseIntelligenceCompiler
    compiler = CodebaseIntelligenceCompiler(repo_path)
    
    if incremental:
        if not changed_file:
            console.print("[yellow]No changed files provided for incremental update. Updating all...[/yellow]")
            compiler.compile_from_codememory(db_path, graph_path)
        else:
            console.print(f"[bold green]Incrementally updating[/bold green] {len(changed_file)} files...")
            for f in changed_file:
                compiler.update_file_incremental(f.resolve())
            console.print("[green]✓ Incremental update complete.[/green]")
    else:
        console.print("[bold green]Compiling Codebase Intelligence Platform Layer...[/bold green]")
        compiler.compile_from_codememory(db_path, graph_path)
        console.print("[green]✓ Full compilation complete at .ai/[/green]")


if __name__ == "__main__":
    app()
