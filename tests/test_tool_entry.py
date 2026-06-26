from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from plugin import AUTO_CARD_TYPE, TarotsPlugin


class ToolEntryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._plugin_config_instance = SimpleNamespace(
            components=SimpleNamespace(enable_tarots=True),
            adjustment=SimpleNamespace(nickname_source="QQ昵称"),
        )
        self.runtime = SimpleNamespace(
            _normalize_display_name=lambda name: "" if name == "用户" else str(name).strip(),
            execute=AsyncMock(return_value=(True, "占卜完成")),
        )
        self.plugin._runtime = self.runtime

    async def test_tool_uses_runtime_display_name_normalizer(self) -> None:
        result = await self.plugin.handle_tarots_tool(
            stream_id="stream",
            card_type=AUTO_CARD_TYPE,
            formation="单张",
            target_user="没空不理",
            user_request="帮忙占卜抽卡运",
        )

        self.assertTrue(result["success"])
        self.runtime.execute.assert_awaited_once_with(
            "stream",
            AUTO_CARD_TYPE,
            "单张",
            "没空不理",
            "帮忙占卜抽卡运",
        )

    async def test_tool_drops_placeholder_user_name(self) -> None:
        await self.plugin.handle_tarots_tool(
            stream_id="stream",
            target_user="用户",
            user_request="占卜",
        )

        self.assertEqual(self.runtime.execute.await_args.args[3], "")


if __name__ == "__main__":
    unittest.main()
