from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plugin import DEFAULT_FAILURE_NOTICE_TEXT, DEFAULT_FAILURE_NOTICE_PROMPT, TarotsPlugin


class BackgroundFailureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._pending_tasks = set()
        self.plugin._memory_silent_texts = {}
        self.plugin._ctx = SimpleNamespace(
            send=SimpleNamespace(text=AsyncMock(return_value=True)),
            logger=SimpleNamespace(
                warning=MagicMock(),
                exception=MagicMock(),
                error=MagicMock(),
            ),
        )
        self.plugin._plugin_config_instance = SimpleNamespace(
            adjustment=SimpleNamespace(
                ai_failure_notice=False,
                failure_notice_text=DEFAULT_FAILURE_NOTICE_TEXT,
                failure_notice_prompt=DEFAULT_FAILURE_NOTICE_PROMPT,
            )
        )

    async def test_background_exception_sends_failure_notice(self) -> None:
        async def fail() -> None:
            raise RuntimeError("boom")

        task = self.plugin._spawn_background_task(
            fail(),
            "tarots_intercept",
            failure_stream_id="stream",
        )
        await task

        self.plugin.ctx.send.text.assert_awaited_once()
        self.assertEqual(self.plugin.ctx.send.text.await_args.args[1], "stream")
        self.assertEqual(self.plugin.ctx.send.text.await_args.args[0], DEFAULT_FAILURE_NOTICE_TEXT)

    async def test_background_timeout_sends_failure_notice(self) -> None:
        task = self.plugin._spawn_background_task(
            asyncio.sleep(1),
            "tarots_intercept",
            timeout=0.001,
            failure_stream_id="stream",
        )
        await task

        self.plugin.ctx.send.text.assert_awaited_once()
        self.plugin.ctx.logger.warning.assert_called_once()

    async def test_plugin_unload_cancellation_does_not_send_failure_notice(self) -> None:
        task = self.plugin._spawn_background_task(
            asyncio.sleep(1),
            "tarots_intercept",
            failure_stream_id="stream",
        )
        await asyncio.sleep(0)
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task

        self.plugin.ctx.send.text.assert_not_awaited()

    async def test_failed_failure_notice_rolls_back_silent_marker(self) -> None:
        self.plugin.ctx.send.text.return_value = False

        await self.plugin._send_background_failure_notice("stream", "tarots_intercept")

        self.assertEqual(self.plugin._memory_silent_texts, {})

    async def test_failure_notice_send_exception_rolls_back_silent_marker(self) -> None:
        self.plugin.ctx.send.text.side_effect = RuntimeError("send failed")

        await self.plugin._send_background_failure_notice("stream", "tarots_intercept")

        self.assertEqual(self.plugin._memory_silent_texts, {})

    async def test_ai_failure_notice_uses_generated_text_when_enabled(self) -> None:
        self.plugin.config.adjustment.ai_failure_notice = True
        runtime = SimpleNamespace(
            _render_prompt_template=lambda template, fallback, **kwargs: (template or fallback).format(**kwargs),
            _build_ai_style_context=AsyncMock(return_value="风格"),
            _call_llm=AsyncMock(return_value="这次抽牌没能完成，稍后再试或使用 /塔罗 吧。"),
        )
        self.plugin._runtime = runtime

        await self.plugin._send_background_failure_notice("stream", "tarots_intercept")

        runtime._call_llm.assert_awaited_once()
        self.assertEqual(
            self.plugin.ctx.send.text.await_args.args,
            ("这次抽牌没能完成，稍后再试或使用 /塔罗 吧。", "stream"),
        )

    async def test_ai_failure_notice_falls_back_when_generation_is_empty(self) -> None:
        self.plugin.config.adjustment.ai_failure_notice = True
        runtime = SimpleNamespace(
            _render_prompt_template=lambda template, fallback, **kwargs: (template or fallback).format(**kwargs),
            _build_ai_style_context=AsyncMock(return_value="风格"),
            _call_llm=AsyncMock(return_value=""),
        )
        self.plugin._runtime = runtime

        await self.plugin._send_background_failure_notice("stream", "tarots_intercept")

        self.assertEqual(
            self.plugin.ctx.send.text.await_args.args,
            (DEFAULT_FAILURE_NOTICE_TEXT, "stream"),
        )

    async def test_ai_failure_notice_falls_back_when_generation_times_out(self) -> None:
        self.plugin.config.adjustment.ai_failure_notice = True
        runtime = SimpleNamespace(
            _render_prompt_template=lambda template, fallback, **kwargs: (template or fallback).format(**kwargs),
            _build_ai_style_context=AsyncMock(return_value="风格"),
            _call_llm=AsyncMock(),
        )
        self.plugin._runtime = runtime

        async def timeout_wait_for(awaitable, timeout):
            del timeout
            awaitable.close()
            raise asyncio.TimeoutError

        with patch("plugin.asyncio.wait_for", new=timeout_wait_for):
            await self.plugin._send_background_failure_notice("stream", "tarots_intercept")

        self.assertEqual(
            self.plugin.ctx.send.text.await_args.args,
            (DEFAULT_FAILURE_NOTICE_TEXT, "stream"),
        )
        self.plugin.ctx.logger.warning.assert_called_once()

    async def test_fixed_failure_notice_is_editable(self) -> None:
        self.plugin.config.adjustment.failure_notice_text = "牌掉到桌子下面了，我捡好就回来。"

        await self.plugin._send_background_failure_notice("stream", "tarots_intercept")

        self.assertEqual(
            self.plugin.ctx.send.text.await_args.args,
            ("牌掉到桌子下面了，我捡好就回来。", "stream"),
        )

    async def test_ai_failure_prompt_is_editable(self) -> None:
        self.plugin.config.adjustment.ai_failure_notice = True
        self.plugin.config.adjustment.failure_notice_prompt = "自定义失败提示：{bot_style_context}"
        runtime = SimpleNamespace(
            _render_prompt_template=lambda template, fallback, **kwargs: (template or fallback).format(**kwargs),
            _build_ai_style_context=AsyncMock(return_value="风格"),
            _call_llm=AsyncMock(return_value="等我把牌整理好，很快回来。"),
        )
        self.plugin._runtime = runtime

        await self.plugin._send_background_failure_notice("stream", "tarots_intercept")

        prompt = runtime._call_llm.await_args.args[0]
        self.assertTrue(prompt.startswith("自定义失败提示："))
        self.assertEqual(runtime._call_llm.await_args.kwargs["system_prompt"], "风格")

    async def test_ai_failure_notice_receives_original_request_language(self) -> None:
        self.plugin.config.adjustment.ai_failure_notice = True
        runtime = SimpleNamespace(
            _render_prompt_template=lambda template, fallback, **kwargs: (template or fallback).format(**kwargs),
            _build_ai_style_context=AsyncMock(return_value="English language context"),
            _call_llm=AsyncMock(return_value="I dropped the cards. Please come back to me later."),
        )
        self.plugin._runtime = runtime

        await self.plugin._send_background_failure_notice(
            "stream",
            "tarots_intercept",
            "Please draw a card for me",
        )

        runtime._build_ai_style_context.assert_awaited_once_with("Please draw a card for me")
        self.assertEqual(
            runtime._call_llm.await_args.kwargs["system_prompt"],
            "English language context",
        )
        self.assertEqual(
            self.plugin.ctx.send.text.await_args.args,
            ("I dropped the cards. Please come back to me later.", "stream"),
        )


if __name__ == "__main__":
    unittest.main()
