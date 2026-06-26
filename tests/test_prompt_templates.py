from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plugin import (
    AdjustmentConfig,
    DEFAULT_INTERPRETATION_PROMPT,
    TarotRuntime,
    TarotsPlugin,
)


class PromptTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._ctx = SimpleNamespace(logger=SimpleNamespace(warning=MagicMock()))
        self.runtime = TarotRuntime(self.plugin)

    def test_custom_prompt_placeholders_are_rendered(self) -> None:
        rendered = self.runtime._render_prompt_template(
            "牌阵={formation}\n牌={cards_info}",
            DEFAULT_INTERPRETATION_PROMPT,
            bot_style_context="风格",
            target_text="解读",
            formation="单张",
            cards_info="愚者正位",
        )

        self.assertEqual(rendered, "牌阵=单张\n牌=愚者正位")

    def test_invalid_custom_prompt_falls_back_to_default(self) -> None:
        rendered = self.runtime._render_prompt_template(
            "错误占位符：{missing}",
            DEFAULT_INTERPRETATION_PROMPT,
            bot_style_context="风格",
            target_text="解读",
            formation="单张",
            cards_info="愚者正位",
        )

        self.assertIn("牌阵：单张", rendered)
        self.assertIn("愚者正位", rendered)
        self.plugin.ctx.logger.warning.assert_called_once()

    def test_webui_prompt_fields_are_editable_and_function_sorted(self) -> None:
        plugin = TarotsPlugin()
        plugin._plugin_config_instance = SimpleNamespace(adjustment=AdjustmentConfig())
        plugin._available_llm_task_names = ("planner", "replyer", "utils")

        fields = plugin.get_webui_config_schema()["sections"]["adjustment"]["fields"]

        expected = {
            "follow_bot_persona": (3, "通用"),
            "interpretation_prompt": (13, "牌名与解读"),
            "preface_prompt": (24, "准备台词"),
            "extension_comment_prompt": (34, "延伸评论"),
            "failure_notice_text": (41, "失败处理"),
            "failure_notice_prompt": (42, "失败处理"),
        }
        for name, (order, group) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(fields[name]["order"], order)
                self.assertEqual(fields[name]["group"], group)
                if name.endswith("_prompt"):
                    self.assertEqual(fields[name]["ui_type"], "textarea")
                    self.assertGreaterEqual(fields[name]["rows"], 9)
        self.assertEqual(fields["llm_model"]["ui_type"], "select")
        self.assertEqual(fields["llm_model"]["choices"], ["planner", "replyer", "utils"])


class BotPersonaContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._plugin_config_instance = SimpleNamespace(adjustment=AdjustmentConfig())
        self.plugin._ctx = SimpleNamespace(
            config=SimpleNamespace(get=AsyncMock()),
            logger=SimpleNamespace(
                debug=MagicMock(),
                info=MagicMock(),
                warning=MagicMock(),
                error=MagicMock(),
            ),
        )
        self.runtime = TarotRuntime(self.plugin)

    async def test_persona_option_disabled_skips_host_config_reads(self) -> None:
        self.plugin.config.adjustment.follow_bot_persona = False
        self.runtime._host_persona_context = "旧人格"
        self.runtime._host_reply_style = "旧风格"
        self.runtime._host_persona_cached_at = 100.0

        context = await self.runtime._build_ai_style_context("占卜")

        self.plugin.ctx.config.get.assert_not_awaited()
        self.assertNotIn("【必须遵守的 MaiBot 身份与表达方式】", context)
        self.assertIn("【塔罗任务边界】", context)
        self.assertEqual(self.runtime._host_reply_style, "")

    async def test_host_persona_is_merged_into_existing_style_context(self) -> None:
        values = {
            "bot.nickname": "龙伯特",
            "bot.alias_names": ["龙龙", "伯特"],
            "personality.personality": "一条温和、谦逊的大学生龙。",
            "personality.reply_style": "说话自然简短，偶尔有一点腼腆。",
        }
        self.plugin.ctx.config.get.side_effect = lambda key, default=None: values.get(key, default)

        context = await self.runtime._build_ai_style_context()

        self.assertIn("你的名字：龙伯特", context)
        self.assertIn("你的别名：龙龙、伯特", context)
        self.assertIn("人格设定：一条温和、谦逊的大学生龙。", context)
        self.assertIn("表达风格：说话自然简短，偶尔有一点腼腆。", context)
        self.assertIn("【必须遵守的 MaiBot 身份与表达方式】", context)
        self.assertIn("【塔罗任务边界】", context)
        self.assertIn("不得覆盖这里的人格与表达风格", context)

    async def test_persona_read_failure_falls_back_to_plugin_style(self) -> None:
        self.plugin.ctx.config.get.side_effect = RuntimeError("config unavailable")

        context = await self.runtime._build_ai_style_context()

        self.assertTrue(context.startswith(TarotRuntime._build_bot_style_context()))
        self.assertIn("未取得用户原始请求", context)
        self.plugin.ctx.logger.debug.assert_called_once()

    async def test_persona_context_is_cached(self) -> None:
        values = {
            "bot.nickname": "龙伯特",
            "bot.alias_names": [],
            "personality.personality": "大学生龙。",
            "personality.reply_style": "说话简短。",
        }
        self.plugin.ctx.config.get.side_effect = lambda key, default=None: values.get(key, default)

        await self.runtime._build_ai_style_context()
        await self.runtime._build_ai_style_context()

        self.assertEqual(self.plugin.ctx.config.get.await_count, 4)

    async def test_user_request_language_is_included_even_with_cached_persona(self) -> None:
        values = {
            "bot.nickname": "龙伯特",
            "bot.alias_names": [],
            "personality.personality": "大学生龙。",
            "personality.reply_style": "说话简短。",
        }
        self.plugin.ctx.config.get.side_effect = lambda key, default=None: values.get(key, default)

        english_context = await self.runtime._build_ai_style_context("Please draw a card for me")
        japanese_context = await self.runtime._build_ai_style_context("タロットを一枚引いて")

        self.assertIn("用户原始请求：Please draw a card for me", english_context)
        self.assertIn("用户原始请求：タロットを一枚引いて", japanese_context)
        self.assertNotIn("タロットを一枚引いて", english_context)
        self.assertEqual(self.plugin.ctx.config.get.await_count, 4)

    async def test_stale_persona_cache_without_reply_style_is_refreshed(self) -> None:
        self.runtime._host_persona_context = "旧人格缓存"
        self.runtime._host_persona_cached_at = 100.0
        self.runtime._host_reply_style = ""
        values = {
            "bot.nickname": "龙伯特",
            "bot.alias_names": [],
            "personality.personality": "大学生龙。",
            "personality.reply_style": "每句话末尾必须加一个“汪”。",
        }
        self.plugin.ctx.config.get.side_effect = lambda key, default=None: values.get(key, default)

        with patch("plugin.time.monotonic", return_value=120.0):
            context = await self.runtime._build_ai_style_context()

        self.assertEqual(self.plugin.ctx.config.get.await_count, 4)
        self.assertIn("表达风格：每句话末尾必须加一个“汪”。", context)

    async def test_one_optional_config_failure_does_not_drop_reply_style(self) -> None:
        async def config_get(key: str, default=None):
            if key == "bot.alias_names":
                raise RuntimeError("aliases unavailable")
            return {
                "bot.nickname": "龙伯特",
                "personality.personality": "大学生龙。",
                "personality.reply_style": "说话简短。",
            }.get(key, default)

        self.plugin.ctx.config.get.side_effect = config_get

        context = await self.runtime._build_ai_style_context()

        self.assertIn("表达风格：说话简短。", context)
        self.plugin.ctx.logger.warning.assert_called_once()

    async def test_llm_receives_persona_as_system_message(self) -> None:
        self.plugin._plugin_config_instance = SimpleNamespace(
            adjustment=SimpleNamespace(llm_model="replyer")
        )
        self.plugin._ctx.llm = SimpleNamespace(
            generate=AsyncMock(return_value={"success": True, "response": "符合人设的回复"})
        )

        result = await self.runtime._call_llm(
            "生成塔罗解读",
            max_len=100,
            system_prompt="人格设定与表达风格",
        )

        self.assertEqual(result, "符合人设的回复")
        prompt = self.plugin.ctx.llm.generate.await_args.kwargs["prompt"]
        self.assertEqual(
            prompt,
            [
                {"role": "system", "content": "人格设定与表达风格"},
                {"role": "user", "content": "生成塔罗解读"},
            ],
        )

    async def test_mandatory_reply_style_reaches_system_message_verbatim(self) -> None:
        values = {
            "bot.nickname": "龙伯特",
            "bot.alias_names": [],
            "personality.personality": "一名性格内向的大学生龙。",
            "personality.reply_style": "每句话末尾必须加一个“汪”。",
        }
        self.plugin.ctx.config.get.side_effect = lambda key, default=None: values.get(key, default)
        self.plugin._plugin_config_instance = SimpleNamespace(
            adjustment=SimpleNamespace(llm_model="replyer")
        )
        self.plugin._ctx.llm = SimpleNamespace(
            generate=AsyncMock(
                side_effect=[
                    {"success": True, "response": "我来抽牌了"},
                    {"success": True, "response": "我来抽牌了汪"},
                ]
            )
        )

        style_context = await self.runtime._build_ai_style_context("帮忙占卜")
        await self.runtime._call_llm(
            "生成一句准备台词",
            max_len=80,
            system_prompt=style_context,
        )

        first_prompt = self.plugin.ctx.llm.generate.await_args_list[0].kwargs["prompt"]
        rewrite_prompt = self.plugin.ctx.llm.generate.await_args_list[1].kwargs["prompt"]
        self.assertIn("表达风格：每句话末尾必须加一个“汪”。", first_prompt[0]["content"])
        self.assertEqual(first_prompt[0]["role"], "system")
        self.assertIn("必须完整遵守的表达风格：每句话末尾必须加一个“汪”。", rewrite_prompt[1]["content"])
        self.assertEqual(self.plugin.ctx.llm.generate.await_count, 2)

    async def test_arbitrary_reply_style_uses_dedicated_rewrite_pass(self) -> None:
        self.plugin._plugin_config_instance = SimpleNamespace(
            adjustment=SimpleNamespace(llm_model="replyer")
        )
        self.plugin._ctx.llm = SimpleNamespace(
            generate=AsyncMock(
                side_effect=[
                    {"success": True, "response": "目前需要谨慎处理关系。"},
                    {"success": True, "response": "这个嘛……先别急着下结论，慢慢看就好。"},
                ]
            )
        )
        self.runtime._host_reply_style = "语气腼腆，避免肯定句，多用迟疑停顿，不要说教。"

        result = await self.runtime._call_llm(
            "生成解读",
            max_len=100,
            system_prompt="当前 MaiBot 人格",
        )

        self.assertEqual(result, "这个嘛……先别急着下结论，慢慢看就好。")
        rewrite_prompt = self.plugin.ctx.llm.generate.await_args_list[1].kwargs["prompt"][1]["content"]
        self.assertIn("语气腼腆，避免肯定句，多用迟疑停顿，不要说教。", rewrite_prompt)
        self.assertIn("不得改变或遗漏牌名、正逆位", rewrite_prompt)
        self.assertEqual(self.plugin.ctx.llm.generate.await_count, 2)

    async def test_style_rewrite_failure_falls_back_to_content_draft(self) -> None:
        self.plugin._plugin_config_instance = SimpleNamespace(
            adjustment=SimpleNamespace(llm_model="replyer")
        )
        self.plugin._ctx.llm = SimpleNamespace(
            generate=AsyncMock(
                side_effect=[
                    {"success": True, "response": "先别急，慢慢处理。"},
                    {"success": False, "error": "rewrite failed"},
                ]
            )
        )
        self.runtime._host_reply_style = "说话简短。"

        result = await self.runtime._call_llm(
            "生成解读",
            max_len=100,
            system_prompt="当前 MaiBot 人格",
        )

        self.assertEqual(result, "先别急，慢慢处理。")


if __name__ == "__main__":
    unittest.main()
