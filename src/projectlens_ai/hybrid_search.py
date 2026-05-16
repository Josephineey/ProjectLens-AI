from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ProjectLensConfig
from .embeddings import EmbeddingBackend, EmbeddingUnavailable
from .index_store import load_index_stats
from .search import SearchResult, search_index
from .semantic_search import SemanticSearchResult, search_semantic_index


@dataclass(frozen=True)
class HybridSearchResult:
    path: str
    role: str
    score: float
    lexical_score: float
    semantic_score: float
    semantic_location: str | None
    semantic_label: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HybridSearchResponse:
    results: list[HybridSearchResult]
    semantic_used: bool
    semantic_error: str | None


def search_hybrid_index(
    root: str | Path,
    query: str,
    *,
    limit: int = 10,
    config: ProjectLensConfig | None = None,
    backend: EmbeddingBackend | None = None,
    allow_download: bool = False,
) -> HybridSearchResponse:
    root_path = Path(root).expanduser().resolve()
    lexical_results = search_index(root_path, query, limit=max(limit * 4, 20))

    semantic_results: list[SemanticSearchResult] = []
    semantic_error: str | None = None
    semantic_used = False
    stats = load_index_stats(root_path)
    if stats is None:
        raise FileNotFoundError(f"ProjectLens index not found for: {root_path}")
    if stats.embedding_count == 0:
        semantic_error = "No embeddings are stored for this repository. Run `projectlens embed build .` to enable semantic ranking."
    else:
        try:
            semantic_results = search_semantic_index(
                root_path,
                query,
                limit=max(limit * 8, 50),
                config=config,
                backend=backend,
                allow_download=allow_download,
            )
            semantic_used = True
        except EmbeddingUnavailable as error:
            semantic_error = str(error)

    results = _merge_results(lexical_results, semantic_results, query=query, limit=limit, semantic_used=semantic_used)
    return HybridSearchResponse(results=results, semantic_used=semantic_used, semantic_error=semantic_error)


def _merge_results(
    lexical_results: list[SearchResult],
    semantic_results: list[SemanticSearchResult],
    *,
    query: str,
    limit: int,
    semantic_used: bool,
) -> list[HybridSearchResult]:
    lexical_by_path = {result.path: result for result in lexical_results}
    semantic_by_path = _best_semantic_result_by_path(semantic_results)

    max_lexical = max((result.score for result in lexical_results), default=0.0)
    max_semantic = max((result.score for result in semantic_by_path.values()), default=0.0)
    paths = set(lexical_by_path) | set(semantic_by_path)

    merged: list[HybridSearchResult] = []
    for path in paths:
        lexical = lexical_by_path.get(path)
        semantic = semantic_by_path.get(path)
        lexical_norm = (lexical.score / max_lexical) if lexical and max_lexical else 0.0
        semantic_norm = (semantic.score / max_semantic) if semantic and max_semantic else 0.0

        if semantic_used:
            score = (lexical_norm * 0.45) + (semantic_norm * 0.55)
            if lexical and semantic:
                score += 0.08
        else:
            score = lexical_norm

        role = lexical.role if lexical else semantic.role if semantic else "unknown"
        score, role_reason = _adjust_score_for_role(score, role, query)
        score = min(score, 1.0)
        reasons = _build_reasons(lexical, semantic, lexical_norm, semantic_norm)
        if role_reason:
            reasons.append(role_reason)
        merged.append(
            HybridSearchResult(
                path=path,
                role=role,
                score=round(score, 4),
                lexical_score=round(lexical_norm, 4),
                semantic_score=round(semantic_norm, 4),
                semantic_location=_semantic_location(semantic),
                semantic_label=semantic.label if semantic else None,
                reasons=tuple(reasons),
            )
        )

    merged.sort(key=lambda item: (-item.score, -item.semantic_score, -item.lexical_score, item.path))
    return merged[: max(limit, 0)]


def _adjust_score_for_role(score: float, role: str, query: str) -> tuple[float, str | None]:
    normalized_query = query.lower()
    asks_for_tests = any(term in normalized_query for term in ("test", "tests", "pytest", "unit test"))
    asks_for_docs = any(term in normalized_query for term in ("readme", "doc", "docs", "documentation", "install"))

    if role == "test" and not asks_for_tests:
        return score * 0.72, "role adjustment: test file downranked for non-test query"
    if role == "documentation" and not asks_for_docs:
        return score * 0.86, "role adjustment: documentation downranked for implementation query"
    return score, None

def _best_semantic_result_by_path(results: list[SemanticSearchResult]) -> dict[str, SemanticSearchResult]:
    best: dict[str, SemanticSearchResult] = {}
    for result in results:
        current = best.get(result.path)
        if current is None or result.score > current.score:
            best[result.path] = result
    return best


def _build_reasons(
    lexical: SearchResult | None,
    semantic: SemanticSearchResult | None,
    lexical_norm: float,
    semantic_norm: float,
) -> list[str]:
    reasons: list[str] = []
    if lexical:
        reasons.append(f"lexical score {lexical.score:.2f} normalized to {lexical_norm:.2f}")
        for reason in lexical.reasons[:3]:
            reasons.append(f"lexical: {reason}")
    if semantic:
        reasons.append(
            f"semantic chunk {semantic.label} at {_semantic_location(semantic)} normalized to {semantic_norm:.2f}"
        )
    return reasons


def _semantic_location(result: SemanticSearchResult | None) -> str | None:
    if result is None:
        return None
    return f"{result.path}:{result.start_line}-{result.end_line}"
