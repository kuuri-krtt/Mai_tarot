from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from plugin import AUTO_CARD_TYPE, TarotsPlugin


class NaturalTriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._bot_mention_names = ()

    def assert_trigger(self, text: str, mode: str = "平衡") -> None:
        self.assertTrue(
            self.plugin._is_tarot_divination_request(text, mode),
            msg=f"{mode}模式应触发: {text!r}",
        )

    def assert_no_trigger(self, text: str, mode: str = "平衡") -> None:
        self.assertFalse(
            self.plugin._is_tarot_divination_request(text, mode),
            msg=f"{mode}模式不应触发: {text!r}",
        )

    def test_balanced_mode_accepts_explicit_short_commands(self) -> None:
        for text in (
            "占卜",
            "占卜！",
            " 占卜 ？ ",
            "塔罗",
            "塔罗牌。",
            "抽牌",
            "抽一张",
            "来一张",
            "算一卦",
            "问牌",
            "测测",
            "tarot",
            "Tarot reading please",
            "draw a card",
            "PULL ONE CARD PLEASE!",
        ):
            with self.subTest(text=text):
                self.assert_trigger(text)
                self.assert_trigger(text, mode="宽松")

    def test_balanced_mode_accepts_explicit_requests(self) -> None:
        for text in (
            "龙伯特帮我占卜",
            "龙伯特帮忙占卜",
            "给我来个塔罗",
            "抽一张牌",
            "帮我问牌",
            "麻烦为我算一卦",
            "可以占卜一下吗",
            "帮我做个 tarot reading",
            "pull a card for me",
        ):
            with self.subTest(text=text):
                self.assert_trigger(text)
                self.assert_trigger(text, mode="宽松")

    def test_loose_mode_adds_topic_based_ambiguous_requests(self) -> None:
        for text in (
            "帮我看看感情",
            "算算最近的运势",
            "看看我们以后会不会在一起",
        ):
            with self.subTest(text=text):
                self.assert_no_trigger(text, mode="平衡")
                self.assert_trigger(text, mode="宽松")

    def test_balanced_mode_accepts_measure_requests_with_divination_topics(self) -> None:
        for text in (
            "测测今年工作有没有机会",
            "测一测最近的运势",
            "测一下以后会不会复合",
        ):
            with self.subTest(text=text):
                self.assert_trigger(text, mode="平衡")
                self.assert_trigger(text, mode="宽松")

    def test_all_modes_reject_knowledge_discussion_and_unrelated_messages(self) -> None:
        for text in (
            "看看这个图片",
            "帮我算算价格",
            "测试一下插件",
            "测测这个功能能不能用",
            "测一下网络速度",
            "塔罗有哪些牌",
            "占卜是什么意思",
            "介绍一下占卜",
            "怎么解读这张牌",
            "what is tarot",
            "explain tarot reading",
            "我买了一副塔罗牌",
            "他昨天去占卜了",
            "tarot cards are pretty",
            "今天天气怎么样",
        ):
            with self.subTest(text=text):
                for mode in ("严格", "平衡", "宽松"):
                    self.assert_no_trigger(text, mode=mode)

    def test_strict_mode_is_conservative_subset_of_balanced(self) -> None:
        for text in ("占卜", "占卜！", "塔罗", "给我来个塔罗", "Tarot reading please", "pull a card for me"):
            with self.subTest(text=text):
                self.assert_no_trigger(text, mode="严格")
        for text in ("龙伯特帮我占卜", "抽一张牌", "测测今年工作机会"):
            with self.subTest(text=text):
                self.assert_trigger(text, mode="严格")
                self.assert_trigger(text, mode="平衡")
                self.assert_trigger(text, mode="宽松")

    def test_legacy_strict_false_positive_is_rejected_in_all_modes(self) -> None:
        for text in (
            "测测这个功能能不能用",
            "测一下网络速度",
            "测试一下插件",
        ):
            with self.subTest(text=text):
                for mode in ("严格", "平衡", "宽松"):
                    self.assert_no_trigger(text, mode=mode)

    def test_trigger_modes_are_monotonic_for_representative_corpus(self) -> None:
        corpus = (
            "占卜",
            "占卜！",
            "塔罗",
            "龙伯特帮我占卜",
            "给我来个塔罗",
            "抽一张牌",
            "帮我问牌",
            "测测今年工作有没有机会",
            "Tarot reading please",
            "pull a card for me",
            "帮我看看感情",
            "算算最近运势",
            "看看我们以后会不会在一起",
            "测测这个功能能不能用",
            "测一下网络速度",
            "塔罗有哪些牌",
            "占卜是什么意思",
            "我买了一副塔罗牌",
            "今天天气怎么样",
        )
        for text in corpus:
            with self.subTest(text=text):
                strict = self.plugin._is_tarot_divination_request(text, "严格")
                balanced = self.plugin._is_tarot_divination_request(text, "平衡")
                loose = self.plugin._is_tarot_divination_request(text, "宽松")
                self.assertFalse(strict and not balanced, msg=f"严格命中但平衡未命中: {text!r}")
                self.assertFalse(balanced and not loose, msg=f"平衡命中但宽松未命中: {text!r}")

    def test_raw_message_text_has_priority_and_ignores_at_components(self) -> None:
        message = {
            "processed_plain_text": "@龙伯特  占卜",
            "raw_message": [
                {
                    "type": "at",
                    "data": {
                        "target_user_id": "3675370963",
                        "target_user_nickname": "龙伯特",
                    },
                },
                {"type": "text", "data": " 占卜"},
            ],
        }
        extracted = self.plugin._extract_message_text(message)
        self.assertEqual(extracted, " 占卜")
        self.assert_trigger(self.plugin._normalize_request_text(extracted))

    def test_text_field_is_used_when_raw_message_has_no_text(self) -> None:
        message = {
            "processed_plain_text": "占卜！",
            "raw_message": [{"type": "at", "data": {"target_user_id": "3675370963"}}],
        }
        self.assertEqual(self.plugin._extract_message_text(message), "占卜！")

    def test_plain_text_mention_of_bot_name_alias_or_account_is_ignored_for_triggering(self) -> None:
        self.plugin._bot_mention_names = ("3675370963", "龙伯特", "牢麦", "lbt")
        for text in (
            "@龙伯特 占卜",
            "＠龙伯特，占卜！",
            "@牢麦：塔罗",
            "@LBT 抽一张牌",
            "@3675370963 问牌",
        ):
            with self.subTest(text=text):
                self.assert_trigger(text)

    def test_plain_text_mention_of_other_person_is_not_removed(self) -> None:
        self.plugin._bot_mention_names = ("龙伯特", "牢麦")

        self.assert_no_trigger("@其他人 占卜")
        self.assertEqual(self.plugin._strip_own_text_mention("@其他人 占卜"), "@其他人 占卜")

    def test_plain_text_mention_requires_separator_after_name(self) -> None:
        self.plugin._bot_mention_names = ("龙伯特",)

        self.assert_no_trigger("@龙伯特占卜")
        self.assertEqual(self.plugin._strip_own_text_mention("@龙伯特占卜"), "@龙伯特占卜")

    def test_natural_options_do_not_match_ambiguous_single_char_aliases(self) -> None:
        for text in (
            "帮我占卜一下大学生活",
            "帮我占卜一下小时候的事",
            "帮我占卜一下四月份",
            "帮我占卜一下马上的考试",
            "帮我占卜一下时间安排",
            "帮我占卜一下吉他演出",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    self.plugin._parse_natural_request_options(text),
                    (AUTO_CARD_TYPE, "单张"),
                )

    def test_natural_options_accept_complete_explicit_aliases(self) -> None:
        cases = {
            "帮我用大阿卡纳占卜": ("大阿卡纳", "单张"),
            "帮我用小牌占卜": ("小阿卡纳", "单张"),
            "用全部牌做圣三角占卜": ("全部", "圣三角"),
            "帮我用时间之流占卜": (AUTO_CARD_TYPE, "时间之流"),
            "帮我用四要素占卜": (AUTO_CARD_TYPE, "四要素"),
            "帮我用吉普赛十字占卜": (AUTO_CARD_TYPE, "吉普赛十字"),
            "帮我用马蹄牌阵占卜": (AUTO_CARD_TYPE, "马蹄"),
            "帮我用六芒星占卜": (AUTO_CARD_TYPE, "六芒星"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.plugin._parse_natural_request_options(text), expected)

    def test_command_options_reject_single_character_shortcuts(self) -> None:
        self.assertEqual(self.plugin._parse_command_args("大 圣"), (AUTO_CARD_TYPE, "单张"))
        self.assertEqual(self.plugin._parse_command_args("小 马"), (AUTO_CARD_TYPE, "单张"))

    def test_command_options_accept_unambiguous_shortcuts(self) -> None:
        self.assertEqual(self.plugin._parse_command_args("大阿 圣三角"), ("大阿卡纳", "圣三角"))
        self.assertEqual(self.plugin._parse_command_args("小牌 马蹄"), ("小阿卡纳", "马蹄"))

    def test_unspecified_and_explicit_all_are_distinct(self) -> None:
        self.assertEqual(self.plugin._parse_natural_request_options("帮我占卜"), (AUTO_CARD_TYPE, "单张"))
        self.assertEqual(self.plugin._parse_natural_request_options("用全部牌占卜"), ("全部", "单张"))
        self.assertEqual(self.plugin._parse_command_args(""), (AUTO_CARD_TYPE, "单张"))
        self.assertEqual(self.plugin._parse_command_args("全部"), ("全部", "单张"))


class BotMentionNameTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_bot_mention_names_uses_official_config_values(self) -> None:
        plugin = object.__new__(TarotsPlugin)
        plugin._bot_mention_names = ()
        values = {
            "bot.nickname": "龙伯特",
            "bot.alias_names": ["牢麦", "lbt", "龙伯特"],
            "bot.qq_account": "3675370963",
        }
        plugin._ctx = SimpleNamespace(
            config=SimpleNamespace(
                get=AsyncMock(side_effect=lambda key, default=None: values.get(key, default))
            ),
            logger=SimpleNamespace(debug=MagicMock()),
        )

        await plugin._refresh_bot_mention_names()

        self.assertEqual(
            set(plugin._bot_mention_names),
            {"龙伯特", "牢麦", "lbt", "3675370963"},
        )

    async def test_refresh_failure_disables_text_mention_stripping(self) -> None:
        plugin = object.__new__(TarotsPlugin)
        plugin._bot_mention_names = ("旧名称",)
        plugin._ctx = SimpleNamespace(
            config=SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("unavailable"))),
            logger=SimpleNamespace(debug=MagicMock()),
        )

        await plugin._refresh_bot_mention_names()

        self.assertEqual(plugin._bot_mention_names, ())
        plugin.ctx.logger.debug.assert_called_once()


if __name__ == "__main__":
    unittest.main()
