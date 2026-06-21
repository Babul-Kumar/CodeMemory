"""Template-based file and project summarizer (no LLM required)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codememory.models import ScanResult

logger = logging.getLogger(__name__)


class FileSummarizer:
    """Generates human-readable summaries from static analysis data.

    No external AI model is used — summaries are produced purely from the
    structured data in :class:`~codememory.models.ScanResult`.
    """

    def summarize_file(self, scan_result: "ScanResult") -> str:
        """Generate a one-paragraph summary for a single source file.

        Example output::

            Python module with 3 classes (AuthService, UserModel, JWTManager)
            and 12 functions. Imports: jwt, hashlib, sqlalchemy.

        Args:
            scan_result: The extraction result for the file.

        Returns:
            A human-readable summary string.
        """
        fi = scan_result.file_info
        language = fi.language or "unknown"

        # Categorize symbols
        classes = [s.name for s in scan_result.symbols if s.kind == "class"]
        functions = [s.name for s in scan_result.symbols if s.kind == "function"]
        methods = [s.name for s in scan_result.symbols if s.kind == "method"]
        imports = scan_result.imports

        parts: list[str] = []

        # Language intro
        lang_display = language.capitalize() if language != "unknown" else "Source"
        parts.append(f"{lang_display} module")

        # Classes
        if classes:
            class_names = ", ".join(classes[:5])
            if len(classes) > 5:
                class_names += f" (+{len(classes) - 5} more)"
            parts.append(
                f"with {len(classes)} class{'es' if len(classes) != 1 else ''} "
                f"({class_names})"
            )

        # Functions and methods
        total_funcs = len(functions) + len(methods)
        if total_funcs > 0:
            if classes:
                parts.append(f"and {total_funcs} function{'s' if total_funcs != 1 else ''}")
            else:
                parts.append(
                    f"with {total_funcs} function{'s' if total_funcs != 1 else ''}"
                )

        if not classes and not functions and not methods:
            parts.append("(no symbols detected)")

        summary = " ".join(parts) + "."

        # Imports line
        if imports:
            shown = imports[:8]
            import_text = ", ".join(shown)
            if len(imports) > 8:
                import_text += f" (+{len(imports) - 8} more)"
            summary += f" Imports: {import_text}."

        # Exports
        if scan_result.exports:
            export_text = ", ".join(scan_result.exports[:5])
            summary += f" Exports: {export_text}."

        # Size
        if fi.size_bytes:
            kb = fi.size_bytes / 1024
            summary += f" Size: {kb:.1f} KB."

        return summary

    def summarize_project(self, stats: dict, architecture: dict) -> str:
        """Generate a high-level project summary.

        Args:
            stats:        Output from :meth:`~codememory.storage.repository.CodeRepository.get_project_stats`.
            architecture: Output from :meth:`~codememory.intelligence.architecture.ArchitectureAnalyzer.analyze`.

        Returns:
            A multi-line project summary string.
        """
        total_files = stats.get("total_files", 0)
        total_symbols = stats.get("total_symbols", 0)
        languages: dict = stats.get("languages", {})

        lines: list[str] = [
            f"Project with {total_files} indexed files and {total_symbols} symbols.",
        ]

        # Language breakdown
        if languages:
            lang_summary = ", ".join(
                f"{lang} ({count})" for lang, count in list(languages.items())[:6]
            )
            lines.append(f"Languages: {lang_summary}.")

        # Architecture layers
        layers: dict = architecture.get("layers", {})
        if layers:
            layer_names = [k for k, v in layers.items() if v]
            if layer_names:
                lines.append(f"Architecture layers: {', '.join(layer_names)}.")

        # Entry points
        entry_points: list = architecture.get("entry_points", [])
        if entry_points:
            shown = entry_points[:3]
            lines.append(f"Entry points: {', '.join(shown)}.")

        # Hub files
        hub_files: list = architecture.get("hub_files", [])
        if hub_files:
            shown = hub_files[:3]
            lines.append(f"Most connected modules: {', '.join(shown)}.")

        return "\n".join(lines)
