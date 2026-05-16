from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.checks import run_project_checks


class ChecksTests(unittest.TestCase):
    def test_complete_repo_has_no_blocking_failures(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_minimal_good_repo(root)

            report = run_project_checks(root)

        self.assertEqual(report.fail_count, 0)
        self.assertTrue(report.is_passing)
        self.assertTrue(any(result.code == "readme" and result.status == "pass" for result in report.results))
        self.assertTrue(any(result.code == "ci" and result.status == "pass" for result in report.results))

    def test_missing_pyproject_is_blocking_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_minimal_good_repo(root)
            (root / "pyproject.toml").unlink()

            report = run_project_checks(root)

        self.assertGreater(report.fail_count, 0)
        self.assertTrue(any(result.code == "pyproject" and result.status == "fail" for result in report.results))

    def test_secret_like_file_is_blocking_failure_without_reading_contents(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_minimal_good_repo(root)
            (root / ".env").write_text("API_KEY=do-not-read\n", encoding="utf-8")

            report = run_project_checks(root)

        self.assertGreater(report.fail_count, 0)
        secret_result = next(result for result in report.results if result.code == "secrets")
        self.assertEqual(secret_result.status, "fail")
        self.assertIn(".env", secret_result.paths)

    def test_gitignore_missing_patterns_is_warning(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            _write_minimal_good_repo(root)
            (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")

            report = run_project_checks(root)

        gitignore_result = next(result for result in report.results if result.code == "gitignore")
        self.assertEqual(gitignore_result.status, "warn")
        self.assertIn(".env", gitignore_result.message)


def _write_minimal_good_repo(root: Path) -> None:
    (root / "README.md").write_text(
        "# Example Project\n\n"
        "## Quick Start\n\nRun the tool locally.\n\n"
        "## Usage\n\nUse the CLI to scan, index, search, and ask questions.\n\n"
        "## Configuration\n\nSet local privacy and embedding options.\n\n"
        "## Roadmap\n\nAdd checks, MCP integration, and evaluation.\n\n"
        + "This README has enough detail for a public project. " * 20,
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[build-system]\n"
        "requires = [\"setuptools>=69\", \"wheel\"]\n"
        "build-backend = \"setuptools.build_meta\"\n\n"
        "[project]\n"
        "name = \"example-project\"\n"
        "version = \"0.1.0\"\n"
        "description = \"Example project\"\n"
        "requires-python = \">=3.10\"\n\n"
        "[project.scripts]\n"
        "projectlens = \"example:main\"\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        ".venv/\n__pycache__/\n.env\n.projectlens/\n*.sqlite\nprojectlens-output.md\n",
        encoding="utf-8",
    )
    (root / "config-example.toml").write_text(
        "[embedding]\nbackend = \"local\"\n\n[runtime]\nprivacy_mode = true\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    for name in ("test_a.py", "test_b.py", "test_c.py"):
        (tests / name).write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "test.yml").write_text("name: tests\n", encoding="utf-8")


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
