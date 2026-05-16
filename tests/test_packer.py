from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.packer import build_repository_pack


class RepositoryPackTests(unittest.TestCase):
    def test_builds_markdown_pack_with_tree_and_symbols(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / "app.py").write_text(
                "def start():\n"
                "    return 'ok'\n",
                encoding="utf-8",
            )

            text = build_repository_pack(root)

        self.assertIn("# ProjectLens Repository Pack", text)
        self.assertIn("## Directory Tree", text)
        self.assertIn("app.py", text)
        self.assertIn("`start`", text)
        self.assertIn("```python", text)


def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
