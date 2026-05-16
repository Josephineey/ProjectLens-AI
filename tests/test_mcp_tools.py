from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.mcp_tools import (
    mcp_ask_codebase,
    mcp_index_repository,
    mcp_language_capabilities,
    mcp_repository_overview,
    mcp_run_checks,
    mcp_run_eval,
    mcp_scan_repository,
    mcp_search_code,
    mcp_status,
)


class McpToolTests(unittest.TestCase):
    def test_scan_status_index_search_ask_and_checks_are_json_safe(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_sample_repo(root)

            scan = mcp_scan_repository(root)
            capabilities = mcp_language_capabilities(root)
            before_status = mcp_status(root)
            index = mcp_index_repository(root)
            after_status = mcp_status(root)
            search = mcp_search_code(root, "database connection", limit=3)
            ask = mcp_ask_codebase(root, "where is the database connection handled?", limit=2)
            checks = mcp_run_checks(root)

        self.assertTrue(scan["ok"])
        self.assertGreaterEqual(scan["files"], 1)
        self.assertTrue(capabilities["ok"])
        self.assertGreater(len(capabilities["language_capabilities"]), 0)
        self.assertFalse(before_status["indexed"])
        self.assertTrue(index["ok"])
        self.assertGreater(index["chunks"], 0)
        self.assertTrue(after_status["indexed"])
        self.assertTrue(search["ok"])
        self.assertGreater(len(search["results"]), 0)
        self.assertTrue(ask["ok"])
        self.assertGreater(len(ask["snippets"]), 0)
        self.assertIn("No LLM was called", ask["answer_policy"])
        self.assertTrue(checks["ok"])
        self.assertEqual(checks["summary"]["fail"], 0)

    def test_repository_overview_builds_compact_first_pass_payload(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_sample_repo(root)

            overview = mcp_repository_overview(root)
            status = mcp_status(root)

        self.assertTrue(overview["ok"])
        self.assertEqual(overview["summary"]["files"], status["files"])
        self.assertTrue(overview["index"]["indexed"])
        self.assertTrue(overview["index"]["built_now"])
        self.assertTrue(overview["checks"]["ok"])
        self.assertGreater(len(overview["important_files"]), 0)
        self.assertGreater(len(overview["suggested_follow_up_queries"]), 0)
        self.assertIn("No LLM was called", overview["answer_policy"])

    def test_search_and_ask_return_hint_before_index_exists(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_sample_repo(root)

            search = mcp_search_code(root, "database connection")
            ask = mcp_ask_codebase(root, "where is configuration handled?")

        self.assertFalse(search["ok"])
        self.assertIn("Run projectlens_index_repository first", search["hint"])
        self.assertFalse(ask["ok"])
        self.assertIn("Run projectlens_index_repository first", ask["hint"])



    def test_eval_tool_uses_case_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_sample_repo(root)
            cases_path = root / "cases.json"
            cases_path.write_text(
                '{"name":"mcp","cases":[{"id":"database","query":"where is database connection?","expected_paths":["src/demo_app/database.py"]}]}',
                encoding="utf-8",
            )
            mcp_index_repository(root)

            report = mcp_run_eval(root, cases_path=str(cases_path))

        self.assertTrue(report["ok"])
        self.assertEqual(report["passed"], 1)
        self.assertEqual(report["failed"], 0)

def _write_sample_repo(root: Path) -> None:
    src = root / "src" / "demo_app"
    src.mkdir(parents=True)
    (src / "database.py").write_text(
        "import sqlite3\n\n"
        "def get_connection(path: str = 'app.db'):\n"
        "    return sqlite3.connect(path)\n",
        encoding="utf-8",
    )
    (src / "config.py").write_text(
        "DEFAULT_DATABASE = 'app.db'\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    for name in ("test_database.py", "test_config.py", "test_cli.py"):
        (tests / name).write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (root / "README.md").write_text(
        "# Demo App\n\n"
        "## Quick Start\n\nRun tests with pytest.\n\n"
        "## Usage\n\nUse the database helper for SQLite connections.\n\n"
        "## Configuration\n\nConfiguration lives in src/demo_app/config.py.\n\n"
        "## Roadmap\n\nAdd more adapters and MCP integration.\n\n"
        + "This sample repository contains enough public documentation. " * 20,
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        ".venv/\n__pycache__/\n.env\n.projectlens/\n*.sqlite\n*.db\nprojectlens-output.md\n",
        encoding="utf-8",
    )
    (root / "config-example.toml").write_text(
        "[embedding]\nbackend = 'local'\n\n[runtime]\nprivacy_mode = true\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[build-system]\n"
        "requires = ['setuptools>=69', 'wheel']\n"
        "build-backend = 'setuptools.build_meta'\n\n"
        "[project]\n"
        "name = 'demo-app'\n"
        "version = '0.1.0'\n"
        "description = 'Demo application'\n"
        "requires-python = '>=3.10'\n\n"
        "[project.scripts]\n"
        "demo-app = 'demo_app:main'\n",
        encoding="utf-8",
    )
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "test.yml").write_text("name: tests\n", encoding="utf-8")


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()