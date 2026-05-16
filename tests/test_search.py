from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.search import search_repository


class SearchRepositoryTests(unittest.TestCase):
    def test_turkish_database_query_finds_database_file(self) -> None:
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

            results = search_repository(root, "veritabani baglantisi nerede")

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].path, "src/database.py")
        self.assertGreater(results[0].score, 0)

    def test_auth_query_uses_symbol_names(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "auth.py").write_text(
                "def authenticate_user(username, password):\n"
                "    return username == password\n",
                encoding="utf-8",
            )
            (root / "main.py").write_text("def start():\n    return None\n", encoding="utf-8")

            results = search_repository(root, "oturum acma")

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].path, "auth.py")
        self.assertTrue(any("symbol match" in reason for reason in results[0].reasons))


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
