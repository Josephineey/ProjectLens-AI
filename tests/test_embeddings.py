from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.config import EmbeddingConfig, default_config
from projectlens_ai.embedding_store import build_embedding_index, test_embedding_backend
from projectlens_ai.embeddings import EmbeddingStatus, cosine_similarity, embedding_status
from projectlens_ai.index_store import build_index, load_index_stats
from projectlens_ai.semantic_search import search_semantic_index


class FakeEmbeddingBackend:
    status = EmbeddingStatus(
        backend="local",
        model="fake-test-model",
        available=True,
        reason="fake backend for tests",
        install_hint="none",
        cost_privacy="free test backend",
    )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]


class KeywordFakeEmbeddingBackend:
    status = EmbeddingStatus(
        backend="local",
        model="fake-keyword-model",
        available=True,
        reason="fake keyword backend for tests",
        install_hint="none",
        cost_privacy="free test backend",
    )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            normalized = text.lower()
            if "database" in normalized or "sqlite" in normalized or "connection" in normalized:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


class EmbeddingTests(unittest.TestCase):
    def test_cosine_similarity(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_disabled_embedding_status_is_unavailable(self) -> None:
        status = embedding_status(EmbeddingConfig(backend="disabled", model=""))
        self.assertFalse(status.available)
        self.assertEqual(status.backend, "disabled")

    def test_probe_embedding_backend_with_fake_backend(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            result = test_embedding_backend(Path(directory), config=default_config(), backend=FakeEmbeddingBackend())

        self.assertEqual(result.backend, "local")
        self.assertEqual(result.vector_dimensions, 2)

    def test_build_embedding_index_with_fake_backend(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "service.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
            build_index(root)
            result = build_embedding_index(root, config=default_config(), backend=FakeEmbeddingBackend())
            stats = load_index_stats(root)

        self.assertGreater(result.embedding_count, 0)
        self.assertEqual(stats.embedding_count, result.embedding_count)

    def test_semantic_search_uses_stored_embedding_vectors(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "database.py").write_text(
                "import sqlite3\n\n"
                "def connect_database():\n"
                "    return sqlite3.connect(':memory:')\n",
                encoding="utf-8",
            )
            (root / "ui.py").write_text("def render_button():\n    return 'ok'\n", encoding="utf-8")
            build_index(root)
            backend = KeywordFakeEmbeddingBackend()
            build_embedding_index(root, config=default_config(), backend=backend)
            results = search_semantic_index(root, "database connection", config=default_config(), backend=backend)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].path, "database.py")


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
