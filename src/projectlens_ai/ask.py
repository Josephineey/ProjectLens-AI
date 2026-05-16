from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectLensConfig
from .embeddings import EmbeddingBackend
from .hybrid_search import HybridSearchResult, search_hybrid_index
from .search import _expand_terms, _tokenize


@dataclass(frozen=True)
class SourceSnippet:
    path: str
    role: str
    label: str | None
    start_line: int
    end_line: int
    score: float
    lexical_score: float
    semantic_score: float
    lines: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class AskResult:
    query: str
    root: str
    semantic_used: bool
    semantic_error: str | None
    snippets: tuple[SourceSnippet, ...]


def build_source_grounded_answer(
    root: str | Path,
    query: str,
    *,
    limit: int = 3,
    context_lines: int = 3,
    config: ProjectLensConfig | None = None,
    backend: EmbeddingBackend | None = None,
) -> AskResult:
    root_path = Path(root).expanduser().resolve()
    response = search_hybrid_index(
        root_path,
        query,
        limit=max(limit * 2, limit),
        config=config,
        backend=backend,
    )
    snippets: list[SourceSnippet] = []
    seen_paths: set[str] = set()
    for result in response.results:
        if result.path in seen_paths:
            continue
        snippet = _snippet_for_result(root_path, query, result, context_lines=context_lines)
        if snippet is None:
            continue
        snippets.append(snippet)
        seen_paths.add(result.path)
        if len(snippets) >= limit:
            break

    return AskResult(
        query=query,
        root=str(root_path),
        semantic_used=response.semantic_used,
        semantic_error=response.semantic_error,
        snippets=tuple(snippets),
    )


def _snippet_for_result(
    root: Path,
    query: str,
    result: HybridSearchResult,
    *,
    context_lines: int,
) -> SourceSnippet | None:
    path = root / result.path
    try:
        file_lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not file_lines:
        return None

    semantic_range = _parse_semantic_location(result.semantic_location, result.path)
    if semantic_range is None:
        start_line, end_line = _best_query_window(file_lines, query, context_lines=context_lines)
    else:
        start_line, end_line = semantic_range
        start_line = max(1, start_line - context_lines)
        end_line = min(len(file_lines), end_line + context_lines)

    selected = tuple((line_number, file_lines[line_number - 1]) for line_number in range(start_line, end_line + 1))
    return SourceSnippet(
        path=result.path,
        role=result.role,
        label=result.semantic_label,
        start_line=start_line,
        end_line=end_line,
        score=result.score,
        lexical_score=result.lexical_score,
        semantic_score=result.semantic_score,
        lines=selected,
    )


def _parse_semantic_location(location: str | None, expected_path: str) -> tuple[int, int] | None:
    if not location:
        return None
    match = re.match(r"^(?P<path>.*):(?P<start>\d+)-(?P<end>\d+)$", location)
    if not match or match.group("path") != expected_path:
        return None
    return int(match.group("start")), int(match.group("end"))


def _best_query_window(lines: list[str], query: str, *, context_lines: int) -> tuple[int, int]:
    terms = _expand_terms(_tokenize(query))
    if not terms:
        return 1, min(len(lines), max(1, context_lines * 2 + 1))

    best_index = 0
    best_score = -1
    for index, line in enumerate(lines):
        normalized = line.lower()
        score = sum(1 for term in terms if term in normalized)
        if score > best_score:
            best_score = score
            best_index = index

    center_line = best_index + 1
    start_line = max(1, center_line - context_lines)
    end_line = min(len(lines), center_line + context_lines)
    return start_line, end_line
