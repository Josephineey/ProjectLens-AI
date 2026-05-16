from __future__ import annotations

import sys
import tempfile
import unittest
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.scanner import scan_repository


class ScanRepositoryTests(unittest.TestCase):
    def test_scans_python_project_symbols_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            (root / "main.py").write_text(
                "import sqlite3\n\n"
                "class App:\n"
                "    pass\n\n"
                "def run():\n"
                "    return sqlite3.connect(':memory:')\n",
                encoding="utf-8",
            )

            report = scan_repository(root)

        self.assertEqual(report.file_count, 3)
        self.assertIn("Python", report.technologies)
        self.assertIn("main.py", report.entrypoints)
        self.assertTrue(any(symbol.name == "App" and symbol.kind == "class" for symbol in report.symbols))
        self.assertTrue(any(symbol.name == "run" and symbol.kind == "function" for symbol in report.symbols))
        self.assertTrue(any("No test files" in warning for warning in report.warnings))

    def test_secret_like_files_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")

            report = scan_repository(root)

        self.assertTrue(any("Secret-like file" in warning for warning in report.warnings))
    def test_generated_projectlens_output_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "projectlens-output.md").write_text("# Generated\n", encoding="utf-8")
            (root / "main.py").write_text("def run():\n    return None\n", encoding="utf-8")

            report = scan_repository(root)

        self.assertEqual([file.path for file in report.files], ["main.py"])

    def test_scans_python_file_with_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "bom.py").write_text("\ufeffdef from_bom():\n    return True\n", encoding="utf-8")

            report = scan_repository(root)

        self.assertTrue(any(symbol.name == "from_bom" for symbol in report.symbols))

def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)

if __name__ == "__main__":
    unittest.main()
