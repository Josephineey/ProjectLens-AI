from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.index_store import build_index, load_index_report
from projectlens_ai.packer import build_repository_pack
from projectlens_ai.scanner import scan_repository
from projectlens_ai.search import search_repository


class LanguageSupportTests(unittest.TestCase):
    def test_scans_typescript_symbols_imports_and_capabilities(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"dependencies":{"react":"latest"}}', encoding="utf-8")
            src = root / "src"
            src.mkdir()
            (src / "App.tsx").write_text(
                "import React from 'react';\n"
                "import { createClient } from './client';\n\n"
                "export interface User { id: string }\n\n"
                "export type Status = 'idle' | 'ready';\n\n"
                "export function loadUser(id: string): User {\n"
                "  return { id };\n"
                "}\n\n"
                "export const useAuth = (): Status => {\n"
                "  return 'ready';\n"
                "};\n\n"
                "export const Dashboard = () => {\n"
                "  return <main />;\n"
                "};\n\n"
                "export class ApiClient {\n"
                "  connect() { return createClient(); }\n"
                "}\n",
                encoding="utf-8",
            )

            report = scan_repository(root)

        self.assertIn("TypeScript", report.technologies)
        self.assertIn("React", report.technologies)
        self.assertTrue(any(cap.language == "TypeScript" and cap.support_level == "structured" for cap in report.language_capabilities))
        self.assertTrue(any(symbol.name == "loadUser" and symbol.kind == "function" for symbol in report.symbols))
        self.assertTrue(any(symbol.name == "useAuth" and symbol.kind == "hook" for symbol in report.symbols))
        self.assertTrue(any(symbol.name == "Dashboard" and symbol.kind == "component" for symbol in report.symbols))
        self.assertTrue(any(symbol.name == "ApiClient" and symbol.kind == "class" for symbol in report.symbols))
        self.assertTrue(any(record.module == "react" for record in report.imports))

    def test_unsupported_language_is_source_fallback_not_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "main.go").write_text(
                "package main\n\n"
                "func main() {\n"
                "  println(\"hello\")\n"
                "}\n",
                encoding="utf-8",
            )

            report = scan_repository(root)
            results = search_repository(root, "main")

        self.assertIn("Go", report.technologies)
        self.assertTrue(any(file.path == "main.go" and file.role == "source" for file in report.files))
        self.assertTrue(any(cap.language == "Go" and cap.support_level == "fallback" for cap in report.language_capabilities))
        self.assertTrue(any("Fallback-only language support" in warning for warning in report.warnings))
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].path, "main.go")

    def test_index_and_pack_include_language_capabilities(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "index.ts").write_text(
                "export function start() {\n"
                "  return true;\n"
                "}\n",
                encoding="utf-8",
            )

            build_index(root)
            loaded = load_index_report(root)
            pack = build_repository_pack(root, include_contents=False)

        self.assertTrue(any(cap.language == "TypeScript" for cap in loaded.language_capabilities))
        self.assertIn("## Language Capabilities", pack)
        self.assertIn("TypeScript", pack)
        self.assertIn("`start`", pack)


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()