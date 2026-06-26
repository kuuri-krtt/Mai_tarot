from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from plugin import AUTO_CARD_TYPE, BUILTIN_TEXT_DECK_PATH, TarotRuntime, TarotsPlugin


def make_card(
    name: str,
    *,
    standard_id: int | None = None,
    arcana: str | None = None,
) -> dict:
    card = {
        "name": name,
        "info": {
            "description": f"{name}正位",
            "reverseDescription": f"{name}逆位",
        },
    }
    if standard_id is not None:
        card["standard_id"] = standard_id
    if arcana is not None:
        card["arcana"] = arcana
    return card


class DeckLoadingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._ctx = SimpleNamespace(
            logger=SimpleNamespace(
                debug=MagicMock(),
                info=MagicMock(),
                warning=MagicMock(),
                error=MagicMock(),
            )
        )
        self.plugin._plugin_config_instance = SimpleNamespace(
            cards=SimpleNamespace(using_cards="classic", auto_complete_standard_cards=True)
        )
        self.runtime = TarotRuntime(self.plugin)

    def write_json(self, path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_builtin_text_deck_contains_complete_standard_tarot(self) -> None:
        cards = self.runtime._load_validated_deck(
            BUILTIN_TEXT_DECK_PATH,
            source_name="builtin",
            image_dir=None,
        )

        self.assertEqual(len(cards), 78)
        self.assertEqual(sum(card["arcana"] == "major" for card in cards.values()), 22)
        self.assertEqual(sum(card["arcana"] == "minor" for card in cards.values()), 56)
        self.assertTrue(all(card["_image_dir"] is None for card in cards.values()))

    def test_major_only_custom_deck_uses_auto_major_and_explicit_full_fallbacks(self) -> None:
        builtin = self.runtime._load_validated_deck(
            BUILTIN_TEXT_DECK_PATH,
            source_name="builtin",
            image_dir=None,
        )
        classic = self.runtime._load_validated_deck(
            Path("tarot_jsons/classic/tarots.json"),
            source_name="classic",
            image_dir=Path("tarot_jsons/classic"),
        )
        selected = {
            "custom-fool": {
                **make_card("自定义愚者", standard_id=0, arcana="major"),
                "_source": "custom",
                "_image_dir": Path("custom"),
                "_raw_id": "custom-fool",
            }
        }

        cards, pools, native = self.runtime._compose_card_pools(selected, classic, builtin)

        self.assertEqual(native, {"major"})
        self.assertEqual(len(pools[AUTO_CARD_TYPE]), 22)
        self.assertEqual(len(pools["大阿卡纳"]), 22)
        self.assertEqual(len(pools["小阿卡纳"]), 56)
        self.assertEqual(len(pools["全部"]), 78)
        self.assertEqual(cards["standard:0"]["name"], "自定义愚者")
        self.assertEqual(cards["standard:22"]["_source"], "classic")

    def test_builtin_text_fallback_is_used_when_classic_is_missing(self) -> None:
        builtin = self.runtime._load_validated_deck(
            BUILTIN_TEXT_DECK_PATH,
            source_name="builtin",
            image_dir=None,
        )
        selected = {
            "0": {
                **make_card("自定义愚者", standard_id=0, arcana="major"),
                "_source": "custom",
                "_image_dir": Path("custom"),
                "_raw_id": "0",
            }
        }

        cards, pools, _ = self.runtime._compose_card_pools(selected, {}, builtin)

        self.assertEqual(len(pools["全部"]), 78)
        self.assertEqual(cards["standard:22"]["_source"], "builtin")
        self.assertIsNone(cards["standard:22"]["_image_dir"])

    def test_auto_complete_standard_cards_can_be_disabled(self) -> None:
        self.plugin.config.cards.auto_complete_standard_cards = False
        builtin = self.runtime._load_validated_deck(
            BUILTIN_TEXT_DECK_PATH,
            source_name="builtin",
            image_dir=None,
        )
        classic = self.runtime._load_validated_deck(
            Path("tarot_jsons/classic/tarots.json"),
            source_name="classic",
            image_dir=Path("tarot_jsons/classic"),
        )
        selected = {
            "custom-fool": {
                **make_card("自定义愚者", standard_id=0, arcana="major"),
                "_source": "custom",
                "_image_dir": Path("custom"),
                "_raw_id": "custom-fool",
            }
        }

        cards, pools, native = self.runtime._compose_card_pools(selected, classic, builtin)

        self.assertEqual(native, {"major"})
        self.assertEqual(len(cards), 1)
        self.assertEqual(pools[AUTO_CARD_TYPE], ["standard:0"])
        self.assertEqual(pools["全部"], ["standard:0"])
        self.assertEqual(pools["大阿卡纳"], ["standard:0"])
        self.assertEqual(pools["小阿卡纳"], [])

    def test_minor_only_custom_deck_uses_auto_minor_pool(self) -> None:
        builtin = self.runtime._load_validated_deck(
            BUILTIN_TEXT_DECK_PATH,
            source_name="builtin",
            image_dir=None,
        )
        selected = {
            "cup-ace": {
                **make_card("自定义圣杯王牌", standard_id=22, arcana="minor"),
                "_source": "custom",
                "_image_dir": Path("custom"),
                "_raw_id": "cup-ace",
            }
        }

        cards, pools, native = self.runtime._compose_card_pools(selected, {}, builtin)

        self.assertEqual(native, {"minor"})
        self.assertEqual(len(pools[AUTO_CARD_TYPE]), 56)
        self.assertEqual(len(pools["大阿卡纳"]), 22)
        self.assertEqual(cards["standard:22"]["name"], "自定义圣杯王牌")

    def test_custom_standard_card_overrides_fallback_and_extra_card_is_preserved(self) -> None:
        builtin = self.runtime._load_validated_deck(
            BUILTIN_TEXT_DECK_PATH,
            source_name="builtin",
            image_dir=None,
        )
        selected = {
            "moon-custom": {
                **make_card("新月", standard_id=18, arcana="major"),
                "_source": "custom",
                "_image_dir": Path("custom"),
                "_raw_id": "moon-custom",
            },
            "extra": {
                **make_card("旅人", arcana="major"),
                "standard_id": None,
                "_source": "custom",
                "_image_dir": Path("custom"),
                "_raw_id": "extra",
            },
        }

        cards, pools, _ = self.runtime._compose_card_pools(selected, {}, builtin)

        self.assertEqual(cards["standard:18"]["name"], "新月")
        self.assertIn("custom:extra", pools[AUTO_CARD_TYPE])
        self.assertEqual(len(pools[AUTO_CARD_TYPE]), 23)
        self.assertEqual(len(pools["全部"]), 79)

    def test_invalid_card_structure_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_path = Path(temp_dir) / "tarots.json"
            self.write_json(
                deck_path,
                {
                    "x": {
                        "name": "坏牌",
                        "arcana": "major",
                        "info": {"description": "只有正位"},
                    }
                },
            )

            with self.assertRaisesRegex(ValueError, "逆位牌义"):
                self.runtime._load_validated_deck(
                    deck_path,
                    source_name="bad",
                    image_dir=deck_path.parent,
                )

    def test_invalid_arcana_and_duplicate_standard_id_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_path = Path(temp_dir) / "tarots.json"
            self.write_json(
                deck_path,
                {
                    "a": make_card("甲", standard_id=0, arcana="minor"),
                },
            )
            with self.assertRaisesRegex(ValueError, "不一致"):
                self.runtime._load_validated_deck(
                    deck_path,
                    source_name="bad",
                    image_dir=deck_path.parent,
                )

            self.write_json(
                deck_path,
                {
                    "a": make_card("甲", standard_id=0, arcana="major"),
                    "b": make_card("乙", standard_id=0, arcana="major"),
                },
            )
            with self.assertRaisesRegex(ValueError, "standard_id 重复"):
                self.runtime._load_validated_deck(
                    deck_path,
                    source_name="bad",
                    image_dir=deck_path.parent,
                )

    def test_invalid_formation_structure_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cards_num"):
            self.runtime._validate_formations(
                {
                    "坏牌阵": {
                        "cards_num": 0,
                        "is_cut": True,
                        "represent": [["位置"]],
                    }
                }
            )

    async def test_invalid_configured_deck_falls_back_atomically(self) -> None:
        formation = {
            "单张": {
                "cards_num": 1,
                "is_cut": True,
                "represent": [["现状"]],
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            tarot_dir = Path(temp_dir)
            self.write_json(tarot_dir / "formation.json", formation)
            self.write_json(
                tarot_dir / "broken" / "tarots.json",
                {"x": {"name": "损坏", "arcana": "major", "info": {}}},
            )
            self.write_json(
                tarot_dir / "classic" / "tarots.json",
                {"0": make_card("后备愚者")},
            )
            self.plugin.config.cards.using_cards = "broken"

            with patch("plugin.TAROT_DIR", tarot_dir):
                await self.runtime.reload()

        self.assertEqual(self.runtime.using_cards, "classic")
        self.assertEqual(len(self.runtime.card_pools["全部"]), 78)
        self.assertEqual(self.runtime.card_map["standard:0"]["_source"], "classic")

    async def test_no_external_deck_uses_complete_builtin_text_deck(self) -> None:
        formation = {
            "单张": {
                "cards_num": 1,
                "is_cut": True,
                "represent": [["现状"]],
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            tarot_dir = Path(temp_dir)
            self.write_json(tarot_dir / "formation.json", formation)

            with patch("plugin.TAROT_DIR", tarot_dir):
                await self.runtime.reload()

        self.assertEqual(self.runtime.using_cards, "内置文字牌库")
        self.assertEqual(len(self.runtime.card_pools[AUTO_CARD_TYPE]), 78)
        self.assertTrue(
            all(card["_image_dir"] is None for card in self.runtime.card_map.values())
        )

    def test_draw_cards_uses_only_requested_dynamic_pool(self) -> None:
        self.runtime.card_map = {
            "major": make_card("大牌", standard_id=0, arcana="major"),
            "minor": make_card("小牌", standard_id=22, arcana="minor"),
        }
        self.runtime.card_pools = {
            AUTO_CARD_TYPE: ["major"],
            "全部": ["major", "minor"],
            "大阿卡纳": ["major"],
            "小阿卡纳": ["minor"],
        }
        self.runtime.formation_map = {
            "单张": {
                "cards_num": 1,
                "is_cut": False,
                "represent": [["现状"]],
            }
        }

        with patch("plugin.random.sample", return_value=["major"]) as sample:
            result = self.runtime._draw_cards(AUTO_CARD_TYPE, "单张")

        sample.assert_called_once_with(["major"], 1)
        self.assertEqual(result, [("major", False)])


if __name__ == "__main__":
    unittest.main()
