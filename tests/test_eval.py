from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.eval import EvalCase, EvalSuite, load_eval_suite, run_eval
from projectlens_ai.index_store import build_index


class EvalTests(unittest.TestCase):
    def test_run_eval_passes_when_expected_file_is_found_and_used_by_ask(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_sample_repo(root)
            build_index(root)
            suite = EvalSuite(
                name="sample",
                cases=(
                    EvalCase(
                        id="database",
                        query="where is the database connection handled?",
                        expected_paths=("src/database.py",),
                        top_k=3,
                    ),
                ),
            )

            report = run_eval(root, suite)

        self.assertTrue(report.is_passing)
        self.assertEqual(report.passed, 1)
        self.assertEqual(report.results[0].search_rank, 1)
        self.assertTrue(report.results[0].ask_source_found)
        self.assertIn(report.results[0].confidence, {"high", "medium"})

    def test_run_eval_fails_when_expected_file_is_not_found(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_sample_repo(root)
            build_index(root)
            suite = EvalSuite(
                name="sample",
                cases=(
                    EvalCase(
                        id="wrong",
                        query="where is the database connection handled?",
                        expected_paths=("src/not_database.py",),
                        top_k=2,
                    ),
                ),
            )

            report = run_eval(root, suite)

        self.assertFalse(report.is_passing)
        self.assertEqual(report.failed, 1)
        self.assertIsNone(report.results[0].search_rank)
        self.assertEqual(report.results[0].confidence, "low")

    def test_load_eval_suite_validates_json_case_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            path = Path(directory) / "cases.json"
            path.write_text(
                '{"name":"demo","cases":[{"id":"config","query":"where is config?","expected_paths":["src/config.py"]}]}',
                encoding="utf-8",
            )

            suite = load_eval_suite(path)

        self.assertEqual(suite.name, "demo")
        self.assertEqual(suite.cases[0].id, "config")
        self.assertEqual(suite.cases[0].expected_paths, ("src/config.py",))

    def test_fallback_language_case_can_pass_with_lower_confidence(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "main.go").write_text(
                "package main\n\n"
                "func main() {\n"
                "  println(\"hello\")\n"
                "}\n",
                encoding="utf-8",
            )
            build_index(root)
            suite = EvalSuite(
                name="fallback",
                cases=(EvalCase(id="go-main", query="where is main?", expected_paths=("main.go",), top_k=3),),
            )

            report = run_eval(root, suite, run_ask=False)

        self.assertTrue(report.is_passing)
        self.assertEqual(report.results[0].support_levels, ("fallback",))
        self.assertIn("fallback-only", " ".join(report.results[0].notes))
        self.assertNotEqual(report.results[0].confidence, "high")


def _write_sample_repo(root: Path) -> None:
    src = root / "src"
    src.mkdir()
    (src / "database.py").write_text(
        "import sqlite3\n\n"
        "def get_connection():\n"
        "    return sqlite3.connect('app.db')\n",
        encoding="utf-8",
    )
    (src / "config.py").write_text("DATABASE_URL = 'sqlite:///app.db'\n", encoding="utf-8")


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()