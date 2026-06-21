"""Import relationship detection and resolution across scan results."""
from __future__ import annotations

import logging
from pathlib import Path

from codememory.models import RelationshipInfo, ScanResult

logger = logging.getLogger(__name__)

# Language-specific module file suffixes for resolution
_LANG_SUFFIXES: dict[str, list[str]] = {
    "python": [".py", "/__init__.py"],
    "javascript": [".js", "/index.js", ".jsx", "/index.jsx", ".mjs"],
    "typescript": [".ts", "/index.ts", ".tsx", "/index.tsx"],
    "go": [".go"],
    "rust": [".rs", "/mod.rs"],
    "java": [".java"],
}


class RelationshipDetector:
    """Resolves raw import strings to actual file paths and emits relationships.

    Uses a two-pass strategy:
    1. Build an index of all known file paths.
    2. For each import string, attempt to resolve it to a known path.
    """

    def __init__(self, repo_root: Path) -> None:
        """Initialise with the repository root.

        Args:
            repo_root: Absolute path to the repository root directory.
        """
        self.repo_root = repo_root.resolve()

    def _build_path_index(self, scan_results: list[ScanResult]) -> dict[str, str]:
        """Build an index mapping various path representations to actual paths.

        Args:
            scan_results: All file scan results.

        Returns:
            Dict mapping ``{canonical_key: file_path}``.
        """
        index: dict[str, str] = {}
        for result in scan_results:
            fp = result.file_info.path
            p = Path(fp)
            # Absolute key
            index[fp] = fp
            # Relative to repo root
            try:
                rel = str(p.relative_to(self.repo_root))
                index[rel] = fp
                # Without extension
                index[str(p.relative_to(self.repo_root).with_suffix(""))] = fp
                # Module-style: replace path separators with dots
                module_key = str(p.relative_to(self.repo_root).with_suffix("")).replace("\\", ".").replace("/", ".")
                index[module_key] = fp
            except ValueError:
                pass
        return index

    def _resolve_import(
        self,
        import_str: str,
        from_file: str,
        language: str | None,
        path_index: dict[str, str],
    ) -> str | None:
        """Attempt to resolve an import string to a known file path.

        Args:
            import_str: Raw import string (e.g. ``"../utils/helpers"``).
            from_file:  Path of the file containing the import.
            language:   Language of the importing file.
            path_index: Prebuilt path index.

        Returns:
            Resolved file path string or ``None`` if resolution fails.
        """
        # Exact match
        if import_str in path_index:
            return path_index[import_str]

        # Module-style dot notation (Python)
        if import_str in path_index:
            return path_index[import_str]

        # Relative path resolution
        from_dir = Path(from_file).parent
        suffixes = _LANG_SUFFIXES.get(language or "", [".py"])

        # Try relative
        for suffix in suffixes:
            candidate = (from_dir / (import_str + suffix)).resolve()
            candidate_str = str(candidate)
            if candidate_str in path_index:
                return path_index[candidate_str]
            # Try repo-relative
            try:
                rel = str(candidate.relative_to(self.repo_root))
                if rel in path_index:
                    return path_index[rel]
            except ValueError:
                pass

        # Try from repo root
        for suffix in suffixes:
            # Replace dots with slashes for Python-style module names
            module_path = import_str.replace(".", "/")
            candidate = (self.repo_root / (module_path + suffix)).resolve()
            candidate_str = str(candidate)
            if candidate_str in path_index:
                return path_index[candidate_str]

        return None

    def detect_relationships(
        self, scan_results: list[ScanResult]
    ) -> list[RelationshipInfo]:
        """Resolve imports to file relationships.

        Args:
            scan_results: All file extraction results.

        Returns:
            List of resolved :class:`~codememory.models.RelationshipInfo` objects.
        """
        path_index = self._build_path_index(scan_results)
        relationships: list[RelationshipInfo] = []
        seen: set[tuple] = set()

        for result in scan_results:
            from_file = result.file_info.path
            language = result.file_info.language

            for imp in result.imports:
                to_file = self._resolve_import(imp, from_file, language, path_index)
                if to_file and to_file != from_file:
                    key = (from_file, to_file, "imports")
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            RelationshipInfo(
                                from_file=from_file,
                                to_file=to_file,
                                rel_type="imports",
                            )
                        )

        logger.info("Detected %d file relationships.", len(relationships))
        return relationships
