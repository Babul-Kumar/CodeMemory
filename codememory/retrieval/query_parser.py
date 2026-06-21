"""Query parser for the CodeMemory retrieval engine.

Extracts structured information from a free-text query so that the
retrieval engine can apply targeted boosting and filtering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "fix": ["fix", "bug", "error", "broken", "crash", "exception", "debug"],
    "refactor": ["refactor", "clean", "improve", "restructure", "simplify"],
    "test": ["test", "tests", "testing", "spec", "specs", "coverage", "assert", "mock"],
    "document": ["doc", "docstring", "comment", "explain", "readme"],
    "understand": ["how", "what", "why", "understand", "explain", "overview"],
    "add": ["add", "create", "implement", "new", "build", "write"],
    "search": ["find", "where", "which", "show", "list", "search", "locate"],
}

# Regex patterns
_CAMEL_CASE_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]{2,})\b")
_SNAKE_CASE_RE = re.compile(r"\b([a-z_][a-z0-9_]{2,})\b")
_FILE_PATH_RE = re.compile(
    r"""
    (?:                         # path separators
        (?:[a-zA-Z0-9_\-./\\]+  # path components
            \.(?:py|js|ts|go|rs|java|c|cpp|h|rb|php|swift|kt|md|json|yaml|yml|toml|cfg|ini)
        )
    )
    """,
    re.VERBOSE,
)


@dataclass
class ParsedQuery:
    """Structured representation of a raw query string."""

    original_query: str
    """The unmodified query text."""

    keywords: list[str] = field(default_factory=list)
    """Significant words after stripping stop-words."""

    file_hints: list[str] = field(default_factory=list)
    """File paths or module names detected in the query."""

    symbol_hints: list[str] = field(default_factory=list)
    """Class / function names detected in the query."""

    intent: str = "search"
    """High-level intent: add | fix | refactor | test | document | search | understand."""


class QueryParser:
    """Parse a free-text query into a :class:`ParsedQuery`."""

    _STOP_WORDS: frozenset[str] = frozenset(
        {
            "a", "an", "and", "are", "as", "at", "be", "been", "by",
            "can", "do", "for", "get", "has", "have", "how", "i",
            "if", "in", "is", "it", "its", "me", "my", "of", "on",
            "or", "please", "so", "that", "the", "their", "them",
            "then", "there", "they", "this", "to", "was", "we",
            "what", "when", "where", "which", "who", "will", "with",
            "you", "your",
        }
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, query: str) -> ParsedQuery:
        """Parse *query* and return a :class:`ParsedQuery`.

        Args:
            query: Raw user query string.

        Returns:
            Structured :class:`ParsedQuery` with extracted metadata.
        """
        pq = ParsedQuery(original_query=query)

        pq.file_hints = self._extract_file_hints(query)
        pq.symbol_hints = self._extract_symbol_hints(query)
        pq.keywords = self._extract_keywords(query)
        pq.intent = self._detect_intent(query)

        return pq

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_file_hints(self, query: str) -> list[str]:
        """Extract file path references from *query*."""
        matches = _FILE_PATH_RE.findall(query)
        # Also check for bare module names like ``codememory.scanner``
        module_pattern = re.findall(r"\b([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+)\b", query)
        return list(dict.fromkeys(matches + module_pattern))

    def _extract_symbol_hints(self, query: str) -> list[str]:
        """Extract CamelCase class hints and snake_case function hints."""
        camel = _CAMEL_CASE_RE.findall(query)
        snake = [
            m for m in _SNAKE_CASE_RE.findall(query)
            if m not in self._STOP_WORDS and len(m) > 3
        ]
        # Deduplicate preserving order
        seen: set[str] = set()
        result: list[str] = []
        for s in camel + snake:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def _extract_keywords(self, query: str) -> list[str]:
        """Return significant lowercase tokens after stop-word removal."""
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", query)
        seen: set[str] = set()
        keywords: list[str] = []
        for tok in tokens:
            lower = tok.lower()
            if lower not in self._STOP_WORDS and len(lower) > 1 and lower not in seen:
                seen.add(lower)
                keywords.append(lower)
        return keywords

    def _detect_intent(self, query: str) -> str:
        """Identify the dominant intent from *query*."""
        lower_query = query.lower()
        scores: dict[str, int] = {intent: 0 for intent in _INTENT_KEYWORDS}
        for intent, kws in _INTENT_KEYWORDS.items():
            for kw in kws:
                if re.search(rf"\b{re.escape(kw)}\b", lower_query):
                    scores[intent] += 1
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "search"
