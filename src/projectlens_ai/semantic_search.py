from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectLensConfig, load_config
from .embeddings import EmbeddingBackend, EmbeddingUnavailable, create_embedding_backend, cosine_similarity
from .index_store import default_index_path, load_index_stats


@dataclass(frozen=True)
class SemanticSearchResult:
    path: str
    role: str
    chunk_kind: str
    label: str
    start_line: int
    end_line: int
    score: float
    raw_score: float


def search_semantic_index(
    root: str | Path,
    query: str,
    *,
    limit: int = 10,
    config: ProjectLensConfig | None = None,
    backend: EmbeddingBackend | None = None,
    allow_download: bool = False,
) -> list[SemanticSearchResult]:
    root_path = Path(root).expanduser().resolve()
    if load_index_stats(root_path) is None:
        raise FileNotFoundError(f"ProjectLens index not found: {default_index_path(root_path)}")

    active_config = config or load_config(root_path)
    if backend is None:
        backend = create_embedding_backend(active_config.embedding, allow_download=allow_download)

    query_vector = backend.embed_texts([query])[0]
    rows = _load_embedding_rows(root_path, backend.status.backend, backend.status.model)
    if not rows:
        raise EmbeddingUnavailable(
            "No stored embeddings found for the active backend/model. "
            "Run `projectlens embed build .` first."
        )

    results: list[SemanticSearchResult] = []
    for path, role, chunk_kind, label, start_line, end_line, vector_json in rows:
        vector = json.loads(vector_json)
        if not isinstance(vector, list):
            continue
        raw_score = cosine_similarity(query_vector, [float(value) for value in vector])
        adjusted_score = _adjust_score_for_role(raw_score, str(role), query)
        results.append(
            SemanticSearchResult(
                path=str(path),
                role=str(role),
                chunk_kind=str(chunk_kind),
                label=str(label),
                start_line=int(start_line),
                end_line=int(end_line),
                score=adjusted_score,
                raw_score=raw_score,
            )
        )

    return sorted(results, key=lambda item: item.score, reverse=True)[: max(limit, 0)]


def _adjust_score_for_role(score: float, role: str, query: str) -> float:
    normalized_query = query.lower()
    asks_for_tests = any(term in normalized_query for term in ("test", "tests", "pytest", "unit test"))
    asks_for_docs = any(term in normalized_query for term in ("readme", "doc", "docs", "documentation", "install"))

    if role == "test" and not asks_for_tests:
        return score * 0.78
    if role == "documentation" and not asks_for_docs:
        return score * 0.82
    return score


def _load_embedding_rows(root: Path, backend: str, model: str) -> list[tuple[str, str, str, str, int, int, str]]:
    index_path = default_index_path(root)
    with closing(sqlite3.connect(index_path)) as connection:
        return connection.execute(
            """
            SELECT chunks.path,
                   files.role,
                   chunks.chunk_kind,
                   chunks.label,
                   chunks.start_line,
                   chunks.end_line,
                   embeddings.vector_json
            FROM embeddings
            JOIN chunks ON chunks.id = embeddings.chunk_id
            JOIN files ON files.path = chunks.path
            WHERE embeddings.backend = ? AND embeddings.model = ?
            ORDER BY chunks.path, chunks.start_line, chunks.label
            """,
            (backend, model),
        ).fetchall()
