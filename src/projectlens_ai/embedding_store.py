from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectLensConfig, load_config
from .embeddings import (
    EmbeddingBackend,
    EmbeddingStatus,
    ProgressCallback,
    create_embedding_backend,
    embedding_status,
)
from .index_store import build_index, default_index_path, load_chunks, load_index_stats


@dataclass(frozen=True)
class EmbeddingBuildResult:
    index_path: str
    backend: str
    model: str
    chunk_count: int
    embedding_count: int
    status: EmbeddingStatus


@dataclass(frozen=True)
class EmbeddingProbeResult:
    backend: str
    model: str
    vector_dimensions: int
    status: EmbeddingStatus


def build_embedding_index(
    root: str | Path,
    *,
    config: ProjectLensConfig | None = None,
    backend: EmbeddingBackend | None = None,
    batch_size: int = 16,
    limit: int | None = None,
    allow_download: bool = False,
    progress: ProgressCallback | None = None,
) -> EmbeddingBuildResult:
    root_path = Path(root).expanduser().resolve()
    active_config = config or load_config(root_path)

    _emit(progress, "Checking SQLite index")
    stats = load_index_stats(root_path)
    if stats is None:
        _emit(progress, "Index not found; building it first")
        build_index(root_path)

    _emit(progress, "Loading code chunks from SQLite")
    chunks = load_chunks(root_path)
    if limit is not None:
        chunks = chunks[: max(limit, 0)]
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    if backend is None:
        backend = create_embedding_backend(
            active_config.embedding,
            allow_download=allow_download,
            progress=progress,
        )
    status = backend.status

    index_path = default_index_path(root_path)
    created_at_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    embedding_count = 0
    _emit(progress, f"Embedding {len(chunks)} chunks in batches of {batch_size}")
    with closing(sqlite3.connect(index_path)) as connection:
        connection.execute("DELETE FROM embeddings WHERE backend = ? AND model = ?", (status.backend, status.model))
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            end = start + len(batch)
            _emit(progress, f"Embedding chunk batch {start + 1}-{end} of {len(chunks)}")
            vectors = backend.embed_texts([chunk.text for chunk in batch])
            rows = []
            for chunk, vector in zip(batch, vectors):
                chunk_id = _find_chunk_id(connection, chunk.path, chunk.start_line, chunk.end_line, chunk.label)
                if chunk_id is None:
                    continue
                rows.append((chunk_id, status.backend, status.model, json.dumps(vector), created_at_utc))
            connection.executemany(
                """
                INSERT INTO embeddings(chunk_id, backend, model, vector_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
            embedding_count += len(rows)
        connection.commit()

    _emit(progress, f"Embedding build finished; wrote {embedding_count} vectors")
    return EmbeddingBuildResult(
        index_path=str(index_path),
        backend=status.backend,
        model=status.model,
        chunk_count=len(chunks),
        embedding_count=embedding_count,
        status=status,
    )


def test_embedding_backend(
    root: str | Path,
    *,
    config: ProjectLensConfig | None = None,
    backend: EmbeddingBackend | None = None,
    allow_download: bool = False,
    progress: ProgressCallback | None = None,
) -> EmbeddingProbeResult:
    root_path = Path(root).expanduser().resolve()
    active_config = config or load_config(root_path)
    if backend is None:
        backend = create_embedding_backend(
            active_config.embedding,
            allow_download=allow_download,
            progress=progress,
        )
    _emit(progress, "Embedding one small probe text")
    vector = backend.embed_texts(["ProjectLens embedding probe"])[0]
    return EmbeddingProbeResult(
        backend=backend.status.backend,
        model=backend.status.model,
        vector_dimensions=len(vector),
        status=backend.status,
    )


def current_embedding_status(root: str | Path) -> EmbeddingStatus:
    config = load_config(root)
    return embedding_status(config.embedding)


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


def _find_chunk_id(
    connection: sqlite3.Connection,
    path: str,
    start_line: int,
    end_line: int,
    label: str,
) -> int | None:
    row = connection.execute(
        """
        SELECT id FROM chunks
        WHERE path = ? AND start_line = ? AND end_line = ? AND label = ?
        LIMIT 1
        """,
        (path, start_line, end_line, label),
    ).fetchone()
    return int(row[0]) if row else None
