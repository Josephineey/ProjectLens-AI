from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.config import init_config, load_config, set_config_value


class ConfigTests(unittest.TestCase):
    def test_loads_defaults_when_config_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            config = load_config(directory)

        self.assertFalse(config.exists)
        self.assertEqual(config.embedding.backend, "local")
        self.assertEqual(config.llm.provider, "none")
        self.assertTrue(config.runtime.privacy_mode)

    def test_init_writes_default_toml_config(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            config = init_config(directory)
            text = Path(config.path).read_text(encoding="utf-8")

        self.assertTrue(config.exists)
        self.assertIn("[embedding]", text)
        self.assertIn('backend = "local"', text)

    def test_set_config_value_updates_and_validates(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            config = set_config_value(directory, "embedding.backend", "openai")
            loaded = load_config(directory)

        self.assertEqual(config.embedding.backend, "openai")
        self.assertEqual(loaded.embedding.backend, "openai")

    def test_invalid_embedding_backend_raises(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            with self.assertRaises(ValueError):
                set_config_value(directory, "embedding.backend", "bad-backend")

    def test_switching_embedding_backend_updates_default_model(self) -> None:
        with tempfile.TemporaryDirectory(dir=_test_tmp_root()) as directory:
            openai_config = set_config_value(directory, "embedding.backend", "openai")
            local_config = set_config_value(directory, "embedding.backend", "local")
            disabled_config = set_config_value(directory, "embedding.backend", "disabled")

        self.assertEqual(openai_config.embedding.model, "text-embedding-3-small")
        self.assertEqual(local_config.embedding.model, "sentence-transformers/all-MiniLM-L6-v2")
        self.assertEqual(disabled_config.embedding.model, "")

def _test_tmp_root() -> str:
    root = Path(os.environ.get("PROJECTLENS_TEST_TMP", Path.cwd() / ".test-tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


if __name__ == "__main__":
    unittest.main()
