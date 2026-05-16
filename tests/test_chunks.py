from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.chunks import build_chunks
from projectlens_ai.scanner import scan_repository


class ChunkTests(unittest.TestCase):
    def test_builds_symbol_chunks_for_python_functions(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "service.py").write_text(
                "def first():\n"
                "    return 1\n\n"
                "def second():\n"
                "    return 2\n",
                encoding="utf-8",
            )
            report = scan_repository(root)
            chunks = build_chunks(report)

        labels = {chunk.label for chunk in chunks}
        self.assertIn("first", labels)
        self.assertIn("second", labels)
        self.assertTrue(all(chunk.chunk_kind == "function" for chunk in chunks))


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
