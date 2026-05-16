from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.index_store import build_index, default_index_path, load_index_report, load_index_stats
from projectlens_ai.scanner import scan_repository
from projectlens_ai.search import search_index


class IndexStoreTests(unittest.TestCase):
    def test_builds_and_loads_sqlite_index(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / "database.py").write_text(
                "import sqlite3\n\n"
                "def get_connection():\n"
                "    return sqlite3.connect('demo.db')\n",
                encoding="utf-8",
            )

            stats = build_index(root)
            loaded_stats = load_index_stats(root)
            report = load_index_report(root)
            results = search_index(root, "database connection")
            self.assertTrue(Path(stats.index_path).exists())

        self.assertEqual(Path(stats.index_path).name, "index.sqlite")
        self.assertIsNotNone(loaded_stats)
        self.assertEqual(loaded_stats.file_count, 2)
        self.assertEqual(report.file_count, 2)
        self.assertTrue(any(symbol.name == "get_connection" for symbol in report.symbols))
        self.assertEqual(results[0].path, "database.py")

    def test_scanner_ignores_projectlens_index_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "main.py").write_text("def run():\n    return None\n", encoding="utf-8")
            index_dir = default_index_path(root).parent
            index_dir.mkdir(parents=True)
            (index_dir / "index.sqlite").write_text("not a real database", encoding="utf-8")

            report = scan_repository(root)

        self.assertEqual([file.path for file in report.files], ["main.py"])


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
