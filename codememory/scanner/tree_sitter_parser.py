"""Tree-sitter parser wrapper with lazy language loading."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache: language_name -> (Language, Parser)
_parser_cache: dict[str, tuple] = {}


def _load_language_module(language: str):
    """Dynamically import the tree-sitter language module.

    Each language ships as a separate PyPI package (e.g. ``tree-sitter-python``).
    This function imports the relevant module and returns it.

    Args:
        language: Lowercase language name (e.g. ``"python"``).

    Returns:
        The imported language module, or ``None`` if unavailable.
    """
    module_map = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "go": "tree_sitter_go",
        "rust": "tree_sitter_rust",
        "java": "tree_sitter_java",
    }
    module_name = module_map.get(language)
    if not module_name:
        return None
    try:
        import importlib

        return importlib.import_module(module_name)
    except ImportError:
        logger.warning(
            "tree-sitter language package '%s' is not installed. "
            "Install it with: pip install %s",
            module_name,
            module_name.replace("_", "-"),
        )
        return None


class TreeSitterParser:
    """Wraps tree-sitter v0.23+ to parse source files.

    Language parsers are created lazily and cached across calls.
    """

    def get_parser(self, language: str):
        """Return a ``(Language, Parser)`` tuple for the given language.

        Results are cached so each language module is only imported once.

        Args:
            language: Lowercase language name.

        Returns:
            A ``(Language, Parser)`` tuple or ``(None, None)`` if unavailable.
        """
        if language in _parser_cache:
            return _parser_cache[language]

        try:
            from tree_sitter import Language, Parser
        except ImportError:
            logger.error("tree-sitter package is not installed.")
            return None, None

        mod = _load_language_module(language)
        if mod is None:
            _parser_cache[language] = (None, None)
            return None, None

        try:
            # tree-sitter >= 0.22: Language(binding.language())
            lang_fn = getattr(mod, "language", None)
            if lang_fn is None:
                logger.warning("Module %s has no 'language' callable.", mod.__name__)
                _parser_cache[language] = (None, None)
                return None, None

            lang_obj = Language(lang_fn())
            parser = Parser(lang_obj)
            _parser_cache[language] = (lang_obj, parser)
            return lang_obj, parser
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to initialise tree-sitter parser for '%s': %s", language, exc
            )
            _parser_cache[language] = (None, None)
            return None, None

    def parse_file(self, file_path: Path, language: str):
        """Parse *file_path* with the tree-sitter parser for *language*.

        Args:
            file_path: Absolute path to the source file.
            language:  Detected language name.

        Returns:
            A ``tree_sitter.Tree`` object or ``None`` on failure.
        """
        _, parser = self.get_parser(language)
        if parser is None:
            return None

        try:
            source = file_path.read_bytes()
            return parser.parse(source)
        except OSError as exc:
            logger.warning("Could not read %s: %s", file_path, exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tree-sitter parse error for %s: %s", file_path, exc)
            return None

    def parse_bytes(self, source: bytes, language: str):
        """Parse raw *source* bytes for *language*.

        Args:
            source:   Raw source code bytes.
            language: Detected language name.

        Returns:
            A ``tree_sitter.Tree`` object or ``None`` on failure.
        """
        _, parser = self.get_parser(language)
        if parser is None:
            return None
        try:
            return parser.parse(source)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tree-sitter parse_bytes error: %s", exc)
            return None
