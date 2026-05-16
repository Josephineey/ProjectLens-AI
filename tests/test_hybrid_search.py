from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.config import default_config
from projectlens_ai.embedding_store import build_embedding_index
from projectlens_ai.embeddings import EmbeddingStatus
from projectlens_ai.hybrid_search import search_hybrid_index
from projectlens_ai.index_store import build_index


class KeywordFakeEmbeddingBackend:
    status = EmbeddingStatus(
        backend="local",
        model="fake-hybrid-model",
        available=True,
        reason="fake hybrid backend for tests",
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


class HybridSearchTests(unittest.TestCase):
    def test_hybrid_search_combines_lexical_and_semantic_scores(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            src = root / "src"
            src.mkdir()
            (src / "database.py").write_text(
                "import sqlite3\n\n"
                "def get_connection():\n"
                "    return sqlite3.connect('app.db')\n",
                encoding="utf-8",
            )
            (src / "views.py").write_text("def render_home():\n    return 'home'\n", encoding="utf-8")
            build_index(root)
            backend = KeywordFakeEmbeddingBackend()
            build_embedding_index(root, config=default_config(), backend=backend)

            response = search_hybrid_index(root, "database connection", config=default_config(), backend=backend)

        self.assertTrue(response.semantic_used)
        self.assertIsNone(response.semantic_error)
        self.assertGreater(len(response.results), 0)
        self.assertEqual(response.results[0].path, "src/database.py")
        self.assertGreater(response.results[0].lexical_score, 0.0)
        self.assertGreater(response.results[0].semantic_score, 0.0)
        self.assertIsNotNone(response.results[0].semantic_location)

    def test_hybrid_search_falls_back_to_lexical_when_embeddings_are_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "database.py").write_text(
                "def connect_database():\n"
                "    return 'sqlite connection'\n",
                encoding="utf-8",
            )
            (root / "ui.py").write_text("def render_button():\n    return 'ok'\n", encoding="utf-8")
            build_index(root)

            response = search_hybrid_index(root, "database connection")

        self.assertFalse(response.semantic_used)
        self.assertIsNotNone(response.semantic_error)
        self.assertGreater(len(response.results), 0)
        self.assertEqual(response.results[0].path, "database.py")
        self.assertEqual(response.results[0].semantic_score, 0.0)
        self.assertGreater(response.results[0].lexical_score, 0.0)


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
