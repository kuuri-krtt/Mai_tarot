from __future__ import annotations

import json
import unittest
from pathlib import Path


class ManifestTests(unittest.TestCase):
    def test_runtime_capabilities_are_declared(self) -> None:
        manifest_path = Path(__file__).resolve().parents[1] / "_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        capabilities = set(manifest.get("capabilities") or [])

        self.assertTrue(
            {
                "send.text",
                "send.image",
                "llm.generate",
                "llm.get_available_models",
                "config.get",
            }.issubset(capabilities)
        )


if __name__ == "__main__":
    unittest.main()
