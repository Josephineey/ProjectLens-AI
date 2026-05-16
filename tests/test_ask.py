from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.ask import build_source_grounded_answer
from projectlens_ai.config import default_config
from projectlens_ai.embedding_store import build_embedding_index
from projectlens_ai.embeddings import EmbeddingStatus
from projectlens_ai.index_store import build_index


class KeywordFakeEmbeddingBackend:
    status = EmbeddingStatus(
        backend="local",
        model="fake-ask-model",
        available=True,
        reason="fake ask backend for tests",
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


class AskTests(unittest.TestCase):
    def test_ask_returns_source_snippet_with_line_numbers(self) -> None:
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

            result = build_source_grounded_answer(
                root,
                "where is database connection handled?",
                limit=1,
                context_lines=1,
                config=default_config(),
                backend=backend,
            )

        self.assertTrue(result.semantic_used)
        self.assertEqual(len(result.snippets), 1)
        snippet = result.snippets[0]
        self.assertEqual(snippet.path, "src/database.py")
        self.assertGreaterEqual(snippet.start_line, 1)
        self.assertLessEqual(snippet.end_line, 4)
        self.assertTrue(any("sqlite3.connect" in line for _, line in snippet.lines))

    def test_ask_falls_back_to_lexical_evidence_without_embeddings(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "config.py").write_text(
                "def load_settings():\n"
                "    return {'debug': True}\n",
                encoding="utf-8",
            )
            build_index(root)

            result = build_source_grounded_answer(root, "configuration settings", limit=1, context_lines=1)

        self.assertFalse(result.semantic_used)
        self.assertIsNotNone(result.semantic_error)
        self.assertEqual(len(result.snippets), 1)
        self.assertEqual(result.snippets[0].path, "config.py")
        self.assertTrue(any("load_settings" in line for _, line in result.snippets[0].lines))


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
