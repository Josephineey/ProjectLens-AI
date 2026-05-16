from __future__ import annotations

import importlib.util
import math
import os
from dataclasses import dataclass
from typing import Callable, Protocol

from .config import EmbeddingConfig


class EmbeddingUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingStatus:
    backend: str
    model: str
    available: bool
    reason: str
    install_hint: str
    cost_privacy: str


class EmbeddingBackend(Protocol):
    status: EmbeddingStatus

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


ProgressCallback = Callable[[str], None]


def embedding_status(config: EmbeddingConfig) -> EmbeddingStatus:
    if config.backend == "disabled":
        return EmbeddingStatus(
            backend="disabled",
            model=config.model,
            available=False,
            reason="Embedding is disabled in config.",
            install_hint="Set embedding.backend to local or openai to enable semantic search.",
            cost_privacy="free; semantic search unavailable",
        )
    if config.backend == "local":
        available = importlib.util.find_spec("sentence_transformers") is not None
        return EmbeddingStatus(
            backend="local",
            model=config.model,
            available=available,
            reason="sentence-transformers package is installed; run `projectlens embed test .` to check the model cache." if available else "sentence-transformers is not installed.",
            install_hint='Install with: python -m pip install "projectlens-ai[local-embeddings]"',
            cost_privacy="free; code stays on this machine",
        )
    if config.backend == "openai":
        has_package = importlib.util.find_spec("openai") is not None
        has_key = bool(os.environ.get("OPENAI_API_KEY"))
        available = has_package and has_key
        missing = []
        if not has_package:
            missing.append("openai package is not installed")
        if not has_key:
            missing.append("OPENAI_API_KEY is not set")
        return EmbeddingStatus(
            backend="openai",
            model=config.model,
            available=available,
            reason="OpenAI embedding backend is ready." if available else "; ".join(missing),
            install_hint='Install with: python -m pip install "projectlens-ai[openai]" and set OPENAI_API_KEY.',
            cost_privacy="low API cost; code chunks are sent to OpenAI for embeddings",
        )
    return EmbeddingStatus(
        backend=config.backend,
        model=config.model,
        available=False,
        reason="Unknown embedding backend.",
        install_hint="Use one of: local, openai, disabled.",
        cost_privacy="unknown",
    )


def create_embedding_backend(
    config: EmbeddingConfig,
    *,
    allow_download: bool = False,
    progress: ProgressCallback | None = None,
) -> EmbeddingBackend:
    status = embedding_status(config)
    if not status.available:
        raise EmbeddingUnavailable(status.reason)
    if config.backend == "local":
        return LocalSentenceTransformerBackend(config.model, status, allow_download=allow_download, progress=progress)
    if config.backend == "openai":
        return OpenAIEmbeddingBackend(config.model, status)
    raise EmbeddingUnavailable(status.reason)


class LocalSentenceTransformerBackend:
    def __init__(
        self,
        model: str,
        status: EmbeddingStatus,
        *,
        allow_download: bool = False,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.status = status
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        if progress:
            progress("Loading sentence-transformers package")

        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        if progress:
            mode = "download allowed" if allow_download else "local cache only"
            progress(f"Loading local embedding model: {model} ({mode})")
        try:
            self._model = SentenceTransformer(model, local_files_only=not allow_download)
        except Exception as error:  # pragma: no cover - depends on local model cache/network state
            if not allow_download:
                raise EmbeddingUnavailable(
                    "Local embedding model is not available in the local cache yet. "
                    "Run `projectlens embed test . --download-model` once to download it, "
                    "then run `projectlens embed build .` again."
                ) from error
            raise EmbeddingUnavailable(f"Could not load local embedding model: {error}") from error

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]


class OpenAIEmbeddingBackend:
    def __init__(self, model: str, status: EmbeddingStatus) -> None:
        self.status = status
        from openai import OpenAI  # type: ignore[import-not-found]

        self._client = OpenAI()
        self._model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [list(map(float, item.embedding)) for item in response.data]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
