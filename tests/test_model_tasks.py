from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from plugin import DEFAULT_LLM_TASK_NAMES, TarotsPlugin


class ModelTaskTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._available_llm_task_names = DEFAULT_LLM_TASK_NAMES
        self.plugin._ctx = SimpleNamespace(
            llm=SimpleNamespace(get_available_models=AsyncMock()),
            logger=SimpleNamespace(warning=MagicMock()),
        )

    async def test_available_model_tasks_are_loaded_and_sorted(self) -> None:
        self.plugin.ctx.llm.get_available_models.return_value = ["utils", "replyer", "planner"]

        await self.plugin._refresh_available_llm_task_names()

        self.assertEqual(
            self.plugin._available_llm_task_names,
            ("planner", "replyer", "utils"),
        )

    async def test_model_task_failure_keeps_existing_choices(self) -> None:
        self.plugin.ctx.llm.get_available_models.side_effect = RuntimeError("unavailable")

        await self.plugin._refresh_available_llm_task_names()

        self.assertEqual(self.plugin._available_llm_task_names, DEFAULT_LLM_TASK_NAMES)
        self.plugin.ctx.logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
