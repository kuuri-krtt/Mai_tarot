from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from maibot_sdk import Command, EventHandler, Field, HookHandler, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ErrorPolicy, EventType, HookMode, HookOrder, ToolParameterInfo, ToolParamType

import asyncio
import base64
import json
import random
import re
import time

PLUGIN_DIR = Path(__file__).parent
TAROT_DIR = PLUGIN_DIR / "tarot_jsons"
BUILTIN_TEXT_DECK_PATH = PLUGIN_DIR / "resources" / "standard_tarot_text.json"
QQ_ID_PATTERN = re.compile(r"^\d{5,}$")
STRICT_COMPAT_REQUEST_PATTERN = re.compile(
    r"(占卜一下|帮.*?占卜|给.*?占卜|为.*?占卜|塔罗占卜|塔罗一下|塔罗.*?看看|用塔罗.*?看|抽.*?牌|算一卦|算卦|测一测|测测|问牌)"
)
TAROT_KNOWLEDGE_PATTERN = re.compile(
    r"(是什么|什么意思|含义|牌义|有哪些|说明|介绍|教程|怎么解读|如何解读|代表什么|"
    r"\bwhat\s+is\b|\bwhat\s+does\b|\bmeaning\b|\bexplain\b|\bhow\s+to\b|\bhow\s+do\b)",
    re.IGNORECASE,
)
TAROT_DISCUSSION_PATTERN = re.compile(
    r"((?:我|他|她|他们|朋友).{0,10}(?:买|学|研究|看过|听说|去|做过|玩过).{0,10}(?:塔罗|占卜)|"
    r"(?:塔罗牌|占卜).{0,10}(?:好看|漂亮|很贵|便宜|到货|买了)|"
    r"\b(?:bought|studying|learning|watched|likes?|pretty|beautiful)\b.{0,20}\btarot\b|"
    r"\btarot\s+cards?\s+(?:are|look|seem)\b)",
    re.IGNORECASE,
)
TAROT_SHORT_COMMAND_PATTERN = re.compile(
    r"^\s*(?:占卜|塔罗|塔罗牌|抽牌|抽一张|抽张牌|来一张|来个塔罗|算卦|算一卦|问牌|测测|"
    r"tarot|tarot\s+reading|draw\s+(?:a|one)\s+card|pull\s+(?:a|one)\s+card)"
    r"\s*(?:please)?\s*[!！?？。．…~～]*\s*$",
    re.IGNORECASE,
)
BALANCED_CHINESE_REQUEST_PATTERN = re.compile(
    r"((?:帮我|帮忙|给我|替我|为我|麻烦|请|可以|能不能|能否|想要|我想|来个|来一次).{0,16}"
    r"(?:塔罗|占卜|抽.{0,4}牌|问牌|算(?:一)?卦)|"
    r"(?:塔罗占卜|占卜一下|塔罗一下|用塔罗.{0,12}(?:看|占卜)|"
    r"抽(?:一张|张|个|一|1)?.{0,2}牌|问牌|算一卦|算卦))"
)
BALANCED_ENGLISH_REQUEST_PATTERN = re.compile(
    r"((?:帮我|给我|替我|为我|麻烦|请|可以|想要|我想|来个).{0,20}"
    r"(?:\btarot(?:\s+reading)?\b|\b(?:draw|pull)\b.{0,8}\bcard\b)|"
    r"\b(?:do|give|perform|start)\b.{0,20}\btarot\s+reading\b|"
    r"\btarot\s+reading\b.{0,12}\bplease\b|"
    r"\b(?:draw|pull)\b.{0,8}\bcard\b(?:.{0,12}\b(?:for\s+me|please)\b)?)",
    re.IGNORECASE,
)
BALANCED_TOPIC_REQUEST_PATTERN = re.compile(
    r"(?:测测|测一测|测一下).{0,24}"
    r"(?:今年|未来|以后|最近|近期|今晚|明天|感情|恋爱|工作|学业|运势|"
    r"结果|发展|有戏|机会|在一起|复合|脱单)"
)
LOOSE_REQUEST_PATTERN = re.compile(r"(帮.*?看看|帮.*?看|看一下|看看|算算|算一下|测一下|测测)")
LOOSE_TOPIC_PATTERN = re.compile(
    r"(今年|未来|以后|最近|近期|今晚|明天|感情|恋爱|工作|学业|运势|"
    r"结果|发展|有戏|机会|在一起|复合|脱单)"
)
NATURAL_TRIGGER_MODES = ("严格", "平衡", "宽松")
DEFAULT_LLM_TASK_NAMES = ("replyer", "utils", "planner")
AUTO_CARD_TYPE = "自动"
STANDARD_MAJOR_IDS = frozenset(range(22))
STANDARD_MINOR_IDS = frozenset(range(22, 78))
MEMORY_SILENT_TTL_SECONDS = 60.0
MEMORY_SILENT_MAX_ENTRIES = 2048
MEMORY_SILENT_PLACEHOLDER = "收到"
DEFAULT_FAILURE_NOTICE_TEXT = "我不小心把牌弄洒了，还在整理，稍后再来找我吧。"
DEFAULT_PREFACE_PROMPT = """{bot_style_context}

请生成一句占卜前的准备台词。
要求：只输出一句话，10-30字，不透露具体牌面。
如果没有用户昵称，就用“好的”“知道了”“明白了”这类无称呼开头。

{user_line}
抽牌范围：{card_type}
牌阵：{formation}
{context_line}

准备台词："""
DEFAULT_INTERPRETATION_PROMPT = """{bot_style_context}

请{target_text}，保持非常简短（2-3句话）。

牌阵：{formation}
抽到的牌：{cards_info}

请用1句话总结牌面意思，再用1句话给出实用建议。不要用专业术语，不要讲大道理。
你的解读（50字以内）："""
DEFAULT_EXTENSION_PROMPT = """{bot_style_context}

请生成一句占卜后的延伸评论。
要求：只输出一句话，字数不限，不复述牌面。
如果没有用户昵称，就不要称呼用户。

{user_line}
牌阵：{formation}
{context_text}
上文解读：{interpretation}

延伸评论："""
DEFAULT_FAILURE_NOTICE_PROMPT = """{bot_style_context}

塔罗占卜没有完成。请生成一句对用户发送的失败提示。
要求：只输出一句话，使用与本次用户请求相同的语言，长度简短。
请给出符合塔罗场景的生活化理由，例如不小心把牌弄洒了、牌找不到了。
不要编造抽到的牌面，不要解释技术原因。
不要表达你会自动重试、稍后主动继续或整理好后自行返回结果。

失败提示："""


def scan_available_card_sets() -> list[str]:
    """扫描本地可用牌组目录。"""

    if not TAROT_DIR.exists():
        return []
    return sorted(
        item.name
        for item in TAROT_DIR.iterdir()
        if item.is_dir() and (item / "tarots.json").exists()
    )


def get_default_card_set() -> str:
    """优先使用 classic，否则使用第一个本地可用牌组。"""

    available_card_sets = scan_available_card_sets()
    if "classic" in available_card_sets:
        return "classic"
    return available_card_sets[0] if available_card_sets else ""


CARD_TYPE_ALIASES = {
    "全部": "全部",
    "阿卡纳": "全部",
    "阿卡那": "全部",
    "阿尔卡纳": "全部",
    "阿尔卡那": "全部",
    "阿尔克那": "全部",
    "大阿": "大阿卡纳",
    "大阿卡纳": "大阿卡纳",
    "大阿卡那": "大阿卡纳",
    "大牌": "大阿卡纳",
    "小阿": "小阿卡纳",
    "小阿卡纳": "小阿卡纳",
    "小阿卡那": "小阿卡纳",
    "小牌": "小阿卡纳",
}
FORMATION_ALIASES = {
    "单张": "单张",
    "一张": "单张",
    "圣三角": "圣三角",
    "三角": "圣三角",
    "时间": "时间之流",
    "时间之流": "时间之流",
    "四要素": "四要素",
    "四元素": "四要素",
    "五牌": "五牌阵",
    "五牌阵": "五牌阵",
    "吉普赛": "吉普赛十字",
    "吉普赛十字": "吉普赛十字",
    "马蹄": "马蹄",
    "六芒": "六芒星",
    "六芒星": "六芒星",
}
NATURAL_CARD_TYPE_ALIASES = {
    alias: mapped
    for alias, mapped in CARD_TYPE_ALIASES.items()
}
NATURAL_FORMATION_ALIASES = {
    alias: mapped
    for alias, mapped in FORMATION_ALIASES.items()
    if alias != "时间"
}
NUMBER_NAME_MAP = {
    "ACE": "王牌",
    "10": "十",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}
CARD_NAME_ALIASES = {
    "皇后": "女皇",
    "隐士": "隐者",
    "星辰": "星星",
    "王后": "皇后",
}


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__: ClassVar[str] = "插件"
    __ui_icon__: ClassVar[str] = "package"
    __ui_order__: ClassVar[int] = 0

    config_version: str = Field(
        default="1.2.1",
        description="配置版本号",
        json_schema_extra={"label": "配置版本", "disabled": True, "hidden": True, "input_type": "text"},
    )
    enabled: bool = Field(default=True, description="是否启用塔罗插件", json_schema_extra={"label": "启用插件"})


class ComponentConfig(PluginConfigBase):
    """组件启用配置。"""

    __ui_label__: ClassVar[str] = "组件"
    __ui_icon__: ClassVar[str] = "puzzle"
    __ui_order__: ClassVar[int] = 1

    enable_tarots: bool = Field(
        default=True,
        description="开启后会拦截自然语言塔罗请求；未命中拦截时也允许 planner 调用塔罗兜底",
        json_schema_extra={"label": "自然语言触发"},
    )
    enable_tarots_command: bool = Field(
        default=True,
        description="开启后可使用 /塔罗、/tarot 或 /tarots 命令手动触发",
        json_schema_extra={"label": "启用 /塔罗 命令"},
    )
    natural_trigger_mode: str = Field(
        default="平衡",
        description="严格是平衡规则的保守子集；平衡识别明确占卜请求；宽松额外识别带占卜主题的看看/算算类请求",
        json_schema_extra={"label": "自然语言触发模式", "x-widget": "select"},
    )


class CardConfig(PluginConfigBase):
    """牌组配置。"""

    __ui_label__: ClassVar[str] = "牌组"
    __ui_icon__: ClassVar[str] = "gallery-vertical"
    __ui_order__: ClassVar[int] = 2

    using_cards: str = Field(
        default_factory=get_default_card_set,
        description="当前使用的牌组目录名，只能选择 tarot_jsons 下包含 tarots.json 的本地牌组",
        json_schema_extra={"label": "当前牌组", "x-widget": "select"},
    )


class AdjustmentConfig(PluginConfigBase):
    """占卜输出配置。"""

    __ui_label__: ClassVar[str] = "输出"
    __ui_icon__: ClassVar[str] = "settings-2"
    __ui_order__: ClassVar[int] = 3

    follow_bot_persona: bool = Field(
        default=True,
        description="AI 生成文本时是否读取并遵循 MaiBot 当前人格与表达风格",
        json_schema_extra={"label": "遵循 MaiBot 人格"},
    )
    send_card_names: bool = Field(default=True, description="是否发送抽到的牌名列表", json_schema_extra={"label": "报牌名"})
    send_interpretation: bool = Field(default=True, description="是否发送牌义解读", json_schema_extra={"label": "发送牌义解读"})
    ai_interpretation: bool = Field(default=True, description="是否使用 AI 生成塔罗解读", json_schema_extra={"label": "AI 解读"})
    interpretation_prompt: str = Field(
        default=DEFAULT_INTERPRETATION_PROMPT,
        description="AI 牌义解读提示词，可用 {bot_style_context} {target_text} {formation} {cards_info}",
        json_schema_extra={"label": "牌义解读提示词"},
    )
    send_preface: bool = Field(default=True, description="占卜前是否发送准备台词", json_schema_extra={"label": "发送准备台词"})
    ai_preface: bool = Field(default=True, description="准备台词是否使用 AI 生成", json_schema_extra={"label": "AI 生成准备台词"})
    contextual_preface: bool = Field(
        default=True,
        description="AI 生成准备台词时是否参考触发语句中的占卜要求和前文语境",
        json_schema_extra={"label": "准备台词参照语境"},
    )
    preface_prompt: str = Field(
        default=DEFAULT_PREFACE_PROMPT,
        description="AI 准备台词提示词，可用 {bot_style_context} {user_line} {card_type} {formation} {context_line}",
        json_schema_extra={"label": "准备台词提示词"},
    )
    send_extension_comment: bool = Field(default=True, description="占卜后是否发送延伸评论", json_schema_extra={"label": "发送延伸评论"})
    ai_extension_comment: bool = Field(default=True, description="延伸评论是否使用 AI 生成", json_schema_extra={"label": "AI 生成延伸评论"})
    contextual_extension_comment: bool = Field(
        default=True,
        description="AI 生成延伸评论时是否结合触发语句和抽牌内容",
        json_schema_extra={"label": "延伸评论参照语境"},
    )
    extension_comment_prompt: str = Field(
        default=DEFAULT_EXTENSION_PROMPT,
        description="AI 延伸评论提示词，可用 {bot_style_context} {user_line} {formation} {context_text} {interpretation}",
        json_schema_extra={"label": "延伸评论提示词"},
    )
    ai_failure_notice: bool = Field(
        default=False,
        description="后台占卜异常或超时时，是否尝试使用 AI 生成失败提示；生成失败时自动使用固定提示",
        json_schema_extra={"label": "AI 生成失败提示"},
    )
    failure_notice_text: str = Field(
        default=DEFAULT_FAILURE_NOTICE_TEXT,
        description="AI 失败提示关闭或生成失败时使用的固定文案",
        json_schema_extra={"label": "固定失败提示"},
    )
    failure_notice_prompt: str = Field(
        default=DEFAULT_FAILURE_NOTICE_PROMPT,
        description="AI 失败提示词，可用 {bot_style_context}",
        json_schema_extra={"label": "失败提示词"},
    )
    delay_preface_seconds: float = Field(default=2.0, description="准备台词发送前延迟秒数", json_schema_extra={"label": "准备台词延迟秒数"})
    delay_image_seconds: float = Field(default=2.0, description="牌面图片发送前延迟秒数", json_schema_extra={"label": "牌面图片延迟秒数"})
    delay_text_seconds: float = Field(default=2.0, description="文字解读发送前延迟秒数", json_schema_extra={"label": "文字解读延迟秒数"})
    delay_extension_seconds: float = Field(default=1.0, description="延伸评论发送前延迟秒数", json_schema_extra={"label": "延伸评论延迟秒数"})
    delay_error_seconds: float = Field(default=1.0, description="错误提示发送前延迟秒数", json_schema_extra={"label": "错误提示延迟秒数"})
    nickname_source: str = Field(
        default="QQ昵称",
        description="称呼来源：优先使用 QQ 昵称，或优先使用群名片",
        json_schema_extra={"label": "称呼来源", "x-widget": "select"},
    )
    preface_text: str = Field(
        default="好的，我这就抽一张牌。",
        description="准备台词模板，可用 {user} {card_type} {formation}",
        json_schema_extra={"label": "准备台词模板"},
    )
    extension_comment_text: str = Field(
        default="先把这句记心里，慢慢来就好。",
        description="延伸评论模板，可用 {user} {formation}",
        json_schema_extra={"label": "延伸评论模板"},
    )
    llm_model: str = Field(default="replyer", description="AI 解读使用的模型任务名", json_schema_extra={"label": "AI 模型任务名"})


class TarotsConfig(PluginConfigBase):
    """塔罗插件完整配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    components: ComponentConfig = Field(default_factory=ComponentConfig)
    cards: CardConfig = Field(default_factory=CardConfig)
    adjustment: AdjustmentConfig = Field(default_factory=AdjustmentConfig)


class TarotRuntime:
    """塔罗占卜运行时逻辑。"""

    def __init__(self, plugin: "TarotsPlugin") -> None:
        self.plugin = plugin
        self.card_map: dict[str, Any] = {}
        self.formation_map: dict[str, Any] = {}
        self.card_pools: dict[str, list[str]] = {
            AUTO_CARD_TYPE: [],
            "全部": [],
            "大阿卡纳": [],
            "小阿卡纳": [],
        }
        self.native_arcana: set[str] = set()
        self.available_card_sets: list[str] = []
        self.using_cards = ""
        self._host_persona_context = ""
        self._host_reply_style = ""
        self._host_persona_cached_at = 0.0

    async def reload(self) -> None:
        """校验并原子加载配置牌组、classic 后备和内置文字牌库。"""

        available = self._scan_available_card_sets()
        configured = str(self.plugin.config.cards.using_cards or "").strip()
        formation_json_path = TAROT_DIR / "formation.json"
        try:
            raw_formations = json.loads(formation_json_path.read_text(encoding="utf-8"))
            validated_formations = self._validate_formations(raw_formations)
            builtin_cards = self._load_validated_deck(
                BUILTIN_TEXT_DECK_PATH,
                source_name="builtin",
                image_dir=None,
            )
        except Exception as exc:
            self.plugin.ctx.logger.error("加载塔罗基础资源失败: %s", exc, exc_info=True)
            return

        candidate_names = list(
            dict.fromkeys(
                name
                for name in (
                    configured,
                    "classic",
                    *available,
                )
                if name
            )
        )
        selected_name = ""
        selected_cards: dict[str, dict[str, Any]] | None = None
        validated_decks: dict[str, dict[str, dict[str, Any]]] = {}
        for name in candidate_names:
            deck_path = TAROT_DIR / name / "tarots.json"
            if not deck_path.exists():
                continue
            try:
                validated_decks[name] = self._load_validated_deck(
                    deck_path,
                    source_name=name,
                    image_dir=TAROT_DIR / name,
                )
            except Exception as exc:
                self.plugin.ctx.logger.error("牌组 %s 校验失败，已跳过: %s", name, exc)
                continue
            if selected_cards is None:
                selected_name = name
                selected_cards = validated_decks[name]

        if configured and selected_name != configured:
            self.plugin.ctx.logger.warning(
                "配置牌组 %s 不可用，临时切换为 %s",
                configured,
                selected_name or "内置文字牌库",
            )

        if selected_cards is None:
            selected_name = "内置文字牌库"
            selected_cards = builtin_cards

        classic_cards = validated_decks.get("classic", {})
        combined_cards, pools, native_arcana = self._compose_card_pools(
            selected_cards,
            classic_cards,
            builtin_cards,
        )
        if not combined_cards or not pools["全部"]:
            self.plugin.ctx.logger.error("没有可用的塔罗牌数据")
            return

        self.available_card_sets = available
        self.using_cards = selected_name
        self.card_map = combined_cards
        self.card_pools = pools
        self.native_arcana = native_arcana
        self.formation_map = validated_formations
        self.plugin.ctx.logger.info(
            "塔罗牌组已加载: cards=%s total=%s auto=%s major=%s minor=%s formations=%s",
            self.using_cards,
            len(self.card_map),
            len(self.card_pools[AUTO_CARD_TYPE]),
            len(self.card_pools["大阿卡纳"]),
            len(self.card_pools["小阿卡纳"]),
            len(self.formation_map),
        )

    def _load_validated_deck(
        self,
        path: Path,
        *,
        source_name: str,
        image_dir: Path | None,
    ) -> dict[str, dict[str, Any]]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("根节点必须是对象")

        cards: dict[str, dict[str, Any]] = {}
        seen_names: set[str] = set()
        seen_standard_ids: set[int] = set()
        for raw_id, raw_card in raw.items():
            if raw_id == "_meta":
                continue
            card_id = str(raw_id).strip()
            if not card_id:
                raise ValueError("牌 ID 不能为空")
            if not isinstance(raw_card, dict):
                raise ValueError(f"牌 {card_id} 必须是对象")

            name = raw_card.get("name")
            info = raw_card.get("info")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"牌 {card_id} 缺少有效 name")
            name = name.strip()
            if name in seen_names:
                raise ValueError(f"牌名重复: {name}")
            if not isinstance(info, dict):
                raise ValueError(f"牌 {card_id} 缺少 info 对象")
            description = info.get("description")
            reverse_description = info.get("reverseDescription")
            if not isinstance(description, str) or not description.strip():
                raise ValueError(f"牌 {card_id} 缺少正位牌义")
            if not isinstance(reverse_description, str) or not reverse_description.strip():
                raise ValueError(f"牌 {card_id} 缺少逆位牌义")

            standard_id_value = raw_card.get("standard_id")
            if standard_id_value is None and card_id.isdigit() and 0 <= int(card_id) <= 77:
                standard_id_value = int(card_id)
            if standard_id_value is not None:
                if isinstance(standard_id_value, bool) or not isinstance(standard_id_value, int):
                    raise ValueError(f"牌 {card_id} 的 standard_id 必须是 0-77 整数")
                if not 0 <= standard_id_value <= 77:
                    raise ValueError(f"牌 {card_id} 的 standard_id 超出 0-77")
                if standard_id_value in seen_standard_ids:
                    raise ValueError(f"standard_id 重复: {standard_id_value}")

            arcana = raw_card.get("arcana")
            if arcana is None and standard_id_value is not None:
                arcana = "major" if standard_id_value in STANDARD_MAJOR_IDS else "minor"
            if arcana not in {"major", "minor"}:
                raise ValueError(f"牌 {card_id} 缺少有效 arcana（major/minor）")
            if standard_id_value is not None:
                expected_arcana = "major" if standard_id_value in STANDARD_MAJOR_IDS else "minor"
                if arcana != expected_arcana:
                    raise ValueError(
                        f"牌 {card_id} 的 arcana 与 standard_id {standard_id_value} 不一致"
                    )

            seen_names.add(name)
            if standard_id_value is not None:
                seen_standard_ids.add(standard_id_value)
            cards[card_id] = {
                **raw_card,
                "name": name,
                "info": {
                    **info,
                    "description": description.strip(),
                    "reverseDescription": reverse_description.strip(),
                },
                "arcana": arcana,
                "standard_id": standard_id_value,
                "_source": source_name,
                "_image_dir": image_dir,
                "_raw_id": card_id,
            }

        if not cards:
            raise ValueError("牌组中没有有效牌")
        meta = raw.get("_meta")
        if isinstance(meta, dict) and isinstance(meta.get("total_cards"), int):
            if meta["total_cards"] != len(cards):
                self.plugin.ctx.logger.warning(
                    "牌组 %s 的 _meta.total_cards=%s，与实际数量 %s 不一致",
                    source_name,
                    meta["total_cards"],
                    len(cards),
                )
        if image_dir is not None:
            missing_images = sum(
                self._find_card_image_path(card, is_reverse) is None
                for card in cards.values()
                for is_reverse in (False, True)
            )
            if missing_images:
                self.plugin.ctx.logger.warning(
                    "牌组 %s 有 %s 张正逆位图片缺失；对应牌将使用文字结果",
                    source_name,
                    missing_images,
                )
        return cards

    def _validate_formations(self, raw: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(raw, dict) or not raw:
            raise ValueError("formation.json 根节点必须是非空对象")
        result: dict[str, dict[str, Any]] = {}
        for name, formation in raw.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(formation, dict):
                raise ValueError("牌阵名称和内容必须有效")
            cards_num = formation.get("cards_num")
            if isinstance(cards_num, bool) or not isinstance(cards_num, int) or cards_num <= 0:
                raise ValueError(f"牌阵 {name} 的 cards_num 必须是正整数")
            if not isinstance(formation.get("is_cut"), bool):
                raise ValueError(f"牌阵 {name} 的 is_cut 必须是布尔值")
            represent = formation.get("represent")
            if not isinstance(represent, list) or not represent:
                raise ValueError(f"牌阵 {name} 的 represent 必须是非空数组")
            for row_index, row in enumerate(represent[:2]):
                if not isinstance(row, list) or len(row) < cards_num:
                    raise ValueError(f"牌阵 {name} 的 represent[{row_index}] 长度不足")
                if any(not isinstance(item, str) or not item.strip() for item in row):
                    raise ValueError(f"牌阵 {name} 的 represent[{row_index}] 必须是非空字符串数组")
            result[name.strip()] = formation
        return result

    def _compose_card_pools(
        self,
        selected_cards: dict[str, dict[str, Any]],
        classic_cards: dict[str, dict[str, Any]],
        builtin_cards: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], set[str]]:
        native_arcana = {card["arcana"] for card in selected_cards.values()}
        standard_sources: dict[int, dict[str, Any]] = {}
        for source_cards in (builtin_cards, classic_cards, selected_cards):
            for card in source_cards.values():
                standard_id = card.get("standard_id")
                if isinstance(standard_id, int):
                    standard_sources[standard_id] = card

        combined: dict[str, dict[str, Any]] = {}
        standard_keys: dict[int, str] = {}
        for standard_id in sorted(standard_sources):
            card = standard_sources[standard_id]
            key = f"standard:{standard_id}"
            combined[key] = card
            standard_keys[standard_id] = key

        extra_keys: list[str] = []
        for raw_id, card in selected_cards.items():
            if card.get("standard_id") is not None:
                continue
            key = f"custom:{raw_id}"
            suffix = 2
            while key in combined:
                key = f"custom:{raw_id}:{suffix}"
                suffix += 1
            combined[key] = card
            extra_keys.append(key)

        major_keys = [
            standard_keys[standard_id]
            for standard_id in sorted(STANDARD_MAJOR_IDS)
            if standard_id in standard_keys
        ] + [key for key in extra_keys if combined[key]["arcana"] == "major"]
        minor_keys = [
            standard_keys[standard_id]
            for standard_id in sorted(STANDARD_MINOR_IDS)
            if standard_id in standard_keys
        ] + [key for key in extra_keys if combined[key]["arcana"] == "minor"]
        all_keys = major_keys + minor_keys
        auto_keys: list[str] = []
        if "major" in native_arcana:
            auto_keys.extend(major_keys)
        if "minor" in native_arcana:
            auto_keys.extend(minor_keys)
        pools = {
            AUTO_CARD_TYPE: auto_keys or all_keys,
            "全部": all_keys,
            "大阿卡纳": major_keys,
            "小阿卡纳": minor_keys,
        }
        return combined, pools, native_arcana

    def _scan_available_card_sets(self) -> list[str]:
        return scan_available_card_sets()

    async def execute(
        self,
        stream_id: str,
        card_type: str = AUTO_CARD_TYPE,
        formation: str = "单张",
        target_user: str = "",
        user_request: str = "",
    ) -> tuple[bool, str]:
        """按聊天流串行执行一次完整塔罗占卜。"""

        if not stream_id:
            return False, "无法获取聊天流"

        stream_lock = await self.plugin._acquire_stream_execution_lock(stream_id)
        try:
            return await self._execute_unlocked(
                stream_id,
                card_type,
                formation,
                target_user,
                user_request,
            )
        finally:
            self.plugin._release_stream_execution_lock(stream_id, stream_lock)

    async def _execute_unlocked(
        self,
        stream_id: str,
        card_type: str = AUTO_CARD_TYPE,
        formation: str = "单张",
        target_user: str = "",
        user_request: str = "",
    ) -> tuple[bool, str]:
        """执行已取得聊天流锁的一次塔罗占卜。"""

        if not self.plugin.config.plugin.enabled:
            return False, "塔罗插件未启用"
        if not self.card_map or not self.formation_map:
            await self.reload()
        if not self.card_map:
            await self._send_after_delay("error", "没有可用的塔罗牌组，无法占卜。", stream_id)
            return False, "没有可用牌组"

        card_type = self._map_card_type(card_type)
        formation = self._map_formation(formation)
        target_user = self._normalize_display_name(target_user)

        if card_type not in {AUTO_CARD_TYPE, "全部", "大阿卡纳", "小阿卡纳"}:
            await self._send_after_delay(
                "error",
                "不存在的抽牌范围，可选：自动、全部、大阿卡纳、小阿卡纳。",
                stream_id,
            )
            return False, "抽牌范围错误"
        if formation not in self.formation_map:
            await self._send_after_delay("error", f"不存在的牌阵：{formation}", stream_id)
            return False, "牌阵错误"

        if self.plugin.config.adjustment.send_preface:
            card_type_label = "当前牌组原生类别（自动）" if card_type == AUTO_CARD_TYPE else card_type
            preface = await self._build_preface(target_user, card_type_label, formation, user_request)
            if preface:
                if not await self._send_after_delay("preface", preface, stream_id):
                    return False, "准备台词发送失败"
                await asyncio.sleep(0.4)

        selected_cards = self._draw_cards(card_type, formation)
        if not selected_cards:
            await self._send_after_delay("error", "当前牌组数据不完整，无法抽牌。", stream_id)
            return False, "牌组数据不完整"

        card_details: list[dict[str, Any]] = []
        failed_images = 0
        represent_list = self.formation_map[formation].get("represent", [])
        for index, (card_id, is_reverse) in enumerate(selected_cards):
            card_data = self.card_map.get(card_id, {})
            if not isinstance(card_data, dict):
                continue

            image_path = self._find_card_image_path(card_data, is_reverse)
            if image_path is None:
                self.plugin.ctx.logger.warning(
                    "塔罗牌缺少图片，继续使用文字结果: source=%s name=%s reverse=%s",
                    card_data.get("_source", "unknown"),
                    card_data.get("name", "未知"),
                    is_reverse,
                )
            else:
                await self._delay_before_send("image")
                if await self._send_card_image(card_data, is_reverse, stream_id, image_path=image_path):
                    await asyncio.sleep(0.5)
                else:
                    failed_images += 1

            card_info = card_data.get("info", {})
            card_details.append(
                {
                    "position": self._get_position_name(represent_list, index),
                    "name": card_data.get("name", "未知"),
                    "is_reverse": is_reverse,
                    "description": card_info.get("reverseDescription" if is_reverse else "description", "暂无描述"),
                    "position_meaning": self._get_position_meaning(represent_list, index, formation),
                }
            )

        if failed_images:
            await self._send_after_delay("error", "塔罗牌图片发送失败，无法继续占卜。", stream_id)
            return False, "图片发送失败"

        await asyncio.sleep(1)
        card_names_text = self._format_card_names(card_details)
        interpretation = ""
        if self.plugin.config.adjustment.send_interpretation:
            interpretation = await self._generate_interpretation(
                card_details,
                formation,
                target_user,
                user_request,
            )

        result_parts: list[str] = []
        if self.plugin.config.adjustment.send_card_names and card_names_text:
            result_parts.append(f"抽到的牌：\n{card_names_text}")
        if self.plugin.config.adjustment.send_interpretation and interpretation:
            result_parts.append(interpretation)
        if result_parts:
            if not await self._send_after_delay("text", "\n\n".join(result_parts), stream_id):
                return False, "占卜结果发送失败"

        if self.plugin.config.adjustment.send_extension_comment:
            extension = await self._build_extension(target_user, formation, interpretation, user_request, card_details)
            if extension:
                if not await self._send_after_delay("extension", extension, stream_id):
                    return False, "延伸评论发送失败"

        if target_user:
            return True, f"已为{target_user}抽取塔罗牌"
        return True, "已抽取塔罗牌"

    def _draw_cards(self, card_type: str, formation_name: str) -> list[tuple[str, bool]]:
        formation = self.formation_map.get(formation_name, {})
        cards_num = int(formation.get("cards_num", 1))
        valid_ids = list(self.card_pools.get(card_type, []))
        if len(valid_ids) < cards_num:
            return []

        selected_ids = random.sample(valid_ids, cards_num)
        is_cut = bool(formation.get("is_cut", False))
        return [(card_id, is_cut and random.random() < 0.5) for card_id in selected_ids]

    async def _send_card_image(
        self,
        card_data: dict[str, Any],
        is_reverse: bool,
        stream_id: str,
        *,
        image_path: Path | None = None,
    ) -> bool:
        card_name = str(card_data.get("name") or "").strip()
        if not card_name:
            return False

        image_path = image_path or self._find_card_image_path(card_data, is_reverse)
        if image_path is None:
            self.plugin.ctx.logger.warning(
                "塔罗牌图片不存在: source=%s name=%s reverse=%s",
                card_data.get("_source", "unknown"),
                card_name,
                is_reverse,
            )
            return False

        try:
            img_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
            sent = await self.plugin.ctx.send.image(img_base64, stream_id)
            if not sent:
                self.plugin.ctx.logger.error(
                    "发送塔罗牌图片失败: send.image 返回 False, cards=%s name=%s reverse=%s",
                    card_data.get("_source", self.using_cards),
                    card_name,
                    is_reverse,
                )
            return bool(sent)
        except Exception as exc:
            self.plugin.ctx.logger.error("发送塔罗牌图片失败: %s", exc, exc_info=True)
            return False

    async def _send_after_delay(self, stage: str, text: str, stream_id: str) -> bool:
        await self._delay_before_send(stage)
        self.plugin._mark_memory_silent_text(stream_id, text)
        try:
            sent = await self.plugin.ctx.send.text(text, stream_id)
        except Exception as exc:
            self.plugin._unmark_memory_silent_text(stream_id, text)
            self.plugin.ctx.logger.error("发送塔罗文本失败: stage=%s error=%s", stage, exc, exc_info=True)
            return False
        if not sent:
            self.plugin._unmark_memory_silent_text(stream_id, text)
            self.plugin.ctx.logger.error("发送塔罗文本失败: stage=%s send.text 返回 False", stage)
            return False
        return True

    async def _delay_before_send(self, stage: str) -> None:
        cfg = self.plugin.config.adjustment
        delay_map = {
            "preface": cfg.delay_preface_seconds,
            "image": cfg.delay_image_seconds,
            "text": cfg.delay_text_seconds,
            "extension": cfg.delay_extension_seconds,
            "error": cfg.delay_error_seconds,
        }
        try:
            await asyncio.sleep(max(0.0, float(delay_map.get(stage, cfg.delay_text_seconds))))
        except (TypeError, ValueError):
            await asyncio.sleep(0.8)

    @staticmethod
    def _build_bot_style_context() -> str:
        """构建不覆盖宿主人设的塔罗任务边界。"""

        return "\n".join(
            [
                "【塔罗任务边界】",
                "你正在生成由 MaiBot 本人对外发送的塔罗相关文本。",
                "请使用与本次用户请求相同的语言回复；无法判断时，跟随 MaiBot 人设和当前会话的常用语言。",
                "塔罗任务只规定内容、长度和安全边界，不定义新的角色或说话风格。",
                "不要自称塔罗助手或专业占卜师。",
                "不要编造没有抽到的牌面，也不要输出与本次塔罗结果无关的内容。",
            ]
        )

    @staticmethod
    def _append_request_language_context(context: str, user_request: str) -> str:
        request_text = str(user_request or "").strip()
        if request_text:
            language_context = "\n".join(
                [
                    "【本次输出语言】",
                    f"用户原始请求：{request_text[:1000]}",
                    "请判断该请求使用的主要语言，并使用同一种语言输出。不要因为牌名、牌义资料或提示词是中文就切换成中文。",
                ]
            )
        else:
            language_context = "\n".join(
                [
                    "【本次输出语言】",
                    "未取得用户原始请求，请跟随 MaiBot 人设和当前会话的常用语言输出。",
                ]
            )
        return f"{context}\n\n{language_context}"

    async def _build_ai_style_context(self, user_request: str = "") -> str:
        """合并插件约束与 MaiBot 当前人设；读取失败时只使用插件约束。"""

        base_context = self._build_bot_style_context()
        if not bool(getattr(self.plugin.config.adjustment, "follow_bot_persona", True)):
            self._host_persona_context = ""
            self._host_reply_style = ""
            self._host_persona_cached_at = 0.0
            return self._append_request_language_context(base_context, user_request)

        now = time.monotonic()
        cached_reply_style = str(getattr(self, "_host_reply_style", "") or "").strip()
        if (
            cached_reply_style
            and self._host_persona_cached_at
            and now - self._host_persona_cached_at < 60.0
        ):
            context = "\n\n".join(part for part in (self._host_persona_context, base_context) if part)
            return self._append_request_language_context(context, user_request)

        config_results = await asyncio.gather(
            self.plugin.ctx.config.get("bot.nickname", ""),
            self.plugin.ctx.config.get("bot.alias_names", []),
            self.plugin.ctx.config.get("personality.personality", ""),
            self.plugin.ctx.config.get("personality.reply_style", ""),
            return_exceptions=True,
        )
        defaults: tuple[Any, ...] = ("", [], "", "")
        values: list[Any] = []
        failed_keys: list[str] = []
        config_keys = (
            "bot.nickname",
            "bot.alias_names",
            "personality.personality",
            "personality.reply_style",
        )
        for key, result, default in zip(config_keys, config_results, defaults, strict=True):
            if isinstance(result, BaseException):
                failed_keys.append(key)
                values.append(default)
            else:
                values.append(result)
        nickname, aliases, personality, reply_style = values

        if failed_keys:
            self.plugin.ctx.logger.warning(
                "塔罗插件读取部分 MaiBot 人设配置失败: %s",
                ", ".join(failed_keys),
            )
        if len(failed_keys) == len(config_keys):
            self._host_persona_context = ""
            self._host_reply_style = ""
            self._host_persona_cached_at = 0.0
            logger_debug = getattr(self.plugin.ctx.logger, "debug", None)
            if callable(logger_debug):
                logger_debug("塔罗插件读取 MaiBot 人设失败，继续使用插件内置风格")
            return self._append_request_language_context(base_context, user_request)

        persona_lines = [
            "【必须遵守的 MaiBot 身份与表达方式】",
            "下面的人格和表达风格决定最终文本的措辞、句式、语气与态度，优先于塔罗任务中的一般性措辞。",
        ]
        nickname_text = str(nickname or "").strip()
        if nickname_text:
            persona_lines.append(f"你的名字：{nickname_text}")

        if isinstance(aliases, (list, tuple, set)):
            alias_text = "、".join(str(alias).strip() for alias in aliases if str(alias).strip())
        else:
            alias_text = str(aliases or "").strip()
        if alias_text:
            persona_lines.append(f"你的别名：{alias_text[:300]}")

        personality_text = str(personality or "").strip()
        if personality_text:
            persona_lines.append(f"人格设定：{personality_text[:2000]}")

        reply_style_text = str(reply_style or "").strip()
        self._host_reply_style = reply_style_text[:1600]
        if reply_style_text:
            self._host_persona_cached_at = now
            persona_lines.append(f"表达风格：{self._host_reply_style}")
            self.plugin.ctx.logger.info(
                "塔罗 AI 已读取 MaiBot 表达风格: chars=%s preview=%s",
                len(self._host_reply_style),
                self._host_reply_style[:80].replace("\n", " "),
            )
        else:
            self._host_persona_cached_at = 0.0
            self.plugin.ctx.logger.warning("塔罗 AI 未读取到 personality.reply_style，将无法执行宿主风格渲染")

        if len(persona_lines) == 2:
            self._host_persona_context = ""
            return self._append_request_language_context(base_context, user_request)

        persona_lines.extend(
            [
                "请直接以这个角色本人说话，不要切换成通用 AI、客服或占卜师腔调。",
                "下方塔罗任务只能限制要说什么和输出长度，不得覆盖这里的人格与表达风格。",
            ]
        )
        self._host_persona_context = "\n".join(persona_lines)
        context = f"{self._host_persona_context}\n\n{base_context}"
        return self._append_request_language_context(context, user_request)

    async def _build_preface(self, user: str, card_type: str, formation: str, user_request: str) -> str:
        cfg = self.plugin.config.adjustment
        template = cfg.preface_text.strip()
        if cfg.send_preface and cfg.ai_preface:
            user_line = f"用户昵称：{user}" if user else "用户昵称：未取得，请不要称呼用户"
            context_line = (
                f"用户占卜请求：{user_request}\n请自然承接这个占卜问题，但不要提前给出结果。"
                if cfg.contextual_preface
                else "用户占卜请求：未启用参照语境"
            )
            ai_style_context = await self._build_ai_style_context(user_request)
            prompt = self._render_prompt_template(
                cfg.preface_prompt,
                DEFAULT_PREFACE_PROMPT,
                bot_style_context="请严格遵守系统消息中的身份、表达方式与塔罗任务边界。",
                user_line=user_line,
                card_type=card_type,
                formation=formation,
                context_line=context_line,
            )
            generated = await self._call_llm(prompt, max_len=80, system_prompt=ai_style_context)
            if generated:
                return generated
        if not user and "{user}" in template:
            return random.choice(("好的，我这就抽一张牌。", "知道了，我来抽牌。", "明白了，我这就开始。"))
        return self._render_template(template, user=user, card_type=card_type, formation=formation)

    async def _build_extension(
        self,
        user: str,
        formation: str,
        interpretation: str,
        user_request: str,
        card_details: list[dict[str, Any]],
    ) -> str:
        cfg = self.plugin.config.adjustment
        template = cfg.extension_comment_text.strip()
        if cfg.send_extension_comment and cfg.ai_extension_comment:
            user_line = f"用户昵称：{user}" if user else "用户昵称：未取得，请不要称呼用户"
            context_lines = ["用户原话：未启用参照语境", "抽牌内容：未启用参照语境"]
            if cfg.contextual_extension_comment:
                cards_info = self._format_cards_for_prompt(card_details)
                context_lines = [
                    f"用户占卜请求：{user_request}",
                    f"抽牌内容：{cards_info}",
                    "请结合用户真正关心的问题和抽到的牌，给一句后续提醒。",
                ]
            context_text = "\n".join(context_lines)
            ai_style_context = await self._build_ai_style_context(user_request)
            prompt = self._render_prompt_template(
                cfg.extension_comment_prompt,
                DEFAULT_EXTENSION_PROMPT,
                bot_style_context="请严格遵守系统消息中的身份、表达方式与塔罗任务边界。",
                user_line=user_line,
                formation=formation,
                context_text=context_text,
                interpretation=interpretation,
            )
            generated = await self._call_llm(prompt, max_len=60, system_prompt=ai_style_context)
            if generated:
                return generated
        if not user and "{user}" in template:
            return random.choice(("先把这句记心里，慢慢来就好。", "整体先别急，按自己的节奏走。", "放轻松，接下来顺着感觉调整就好。"))
        return self._render_template(template, user=user, formation=formation)

    async def _generate_interpretation(
        self,
        card_details: list[dict[str, Any]],
        formation: str,
        user: str,
        user_request: str = "",
    ) -> str:
        if self.plugin.config.adjustment.ai_interpretation:
            cards_info = self._format_cards_for_prompt(card_details)
            target_text = f"为{user}解读塔罗牌" if user else "解读塔罗牌，不要称呼用户"
            ai_style_context = await self._build_ai_style_context(user_request)
            prompt = self._render_prompt_template(
                self.plugin.config.adjustment.interpretation_prompt,
                DEFAULT_INTERPRETATION_PROMPT,
                bot_style_context="请严格遵守系统消息中的身份、表达方式与塔罗任务边界。",
                target_text=target_text,
                formation=formation,
                cards_info=cards_info,
            )
            generated = await self._call_llm(prompt, max_len=100, system_prompt=ai_style_context)
            if generated:
                return generated
        return self._generate_fallback_interpretation(card_details, user)

    def _format_cards_for_prompt(self, card_details: list[dict[str, Any]]) -> str:
        return "；".join(
            f"{card['position']}：{card['name']}（{'逆位' if card['is_reverse'] else '正位'}，{card['description']}）"
            for card in card_details
        )

    async def _call_llm(self, prompt: str, max_len: int, system_prompt: str = "") -> str:
        draft = await self._request_llm_text(
            prompt,
            system_prompt=system_prompt,
            temperature=0.7,
        )
        if not draft:
            return ""

        reply = draft
        reply_style = str(getattr(self, "_host_reply_style", "") or "").strip()
        if reply_style and system_prompt.strip():
            styled_reply = await self._rewrite_in_host_style(
                draft,
                system_prompt=system_prompt,
                reply_style=reply_style,
                max_len=max_len,
            )
            if styled_reply:
                reply = styled_reply
                self.plugin.ctx.logger.info(
                    "塔罗 AI 风格重写完成: draft_chars=%s styled_chars=%s",
                    len(draft),
                    len(styled_reply),
                )
            else:
                self.plugin.ctx.logger.warning("塔罗 AI 风格重写失败，回退到内容草稿")
        elif system_prompt.strip():
            self.plugin.ctx.logger.warning("塔罗 AI 本次未执行风格重写: personality.reply_style 为空")

        reply = self._normalize_llm_reply(reply)
        if 0 < len(reply) <= max_len:
            return reply
        return ""

    async def _request_llm_text(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        try:
            llm_prompt: str | list[dict[str, str]]
            if system_prompt.strip():
                llm_prompt = [
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": prompt},
                ]
            else:
                llm_prompt = prompt
            result = await self.plugin.ctx.llm.generate(
                prompt=llm_prompt,
                model=self.plugin.config.adjustment.llm_model or "replyer",
                temperature=temperature,
            )
        except Exception as exc:
            self.plugin.ctx.logger.error("塔罗插件调用 LLM 失败: %s", exc, exc_info=True)
            return ""

        result = self._peel_envelope(result)
        if isinstance(result, dict):
            if not result.get("success"):
                self.plugin.ctx.logger.error("塔罗插件 LLM 返回失败: %s", result.get("error", "未知错误"))
                return ""
            reply = str(result.get("response") or "").strip()
        else:
            reply = str(result or "").strip()
        return self._normalize_llm_reply(reply)

    async def _rewrite_in_host_style(
        self,
        draft: str,
        *,
        system_prompt: str,
        reply_style: str,
        max_len: int,
    ) -> str:
        """将任务草稿统一渲染成宿主当前人格的实际发言。"""

        rewrite_prompt = "\n".join(
            [
                "【最终发言风格渲染】",
                "请把下面的草稿改写成 MaiBot 当前角色本人会直接发送的发言。",
                f"必须完整遵守的表达风格：{reply_style}",
                "逐项落实其中关于语气、用词、句式、立场、口癖、结尾、标点、禁止事项和强制格式的全部要求。",
                "只改变表达方式，不得改变或遗漏牌名、正逆位、牌阵位置、牌义事实、建议方向和失败原因。",
                "保持草稿使用的主要语言，不要添加解释、标签、引号或分析过程。",
                f"最终文本不得超过 {max_len} 个字符，只输出最终可发送文本。",
                "",
                "【待改写草稿】",
                draft,
            ]
        )
        return await self._request_llm_text(
            rewrite_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )

    @staticmethod
    def _normalize_llm_reply(text: str) -> str:
        return str(text or "").replace("\n", " ").strip(" \"'")

    def _peel_envelope(self, data: Any, max_depth: int = 4) -> Any:
        for _ in range(max_depth):
            if not isinstance(data, dict):
                return data
            if "success" not in data or "result" not in data:
                return data
            inner = data.get("result")
            if inner is None:
                return data
            data = inner
        return data

    def _generate_fallback_interpretation(self, card_details: list[dict[str, Any]], user: str) -> str:
        summaries: list[str] = []
        for card in card_details:
            name = str(card.get("name") or "未知")
            orientation = "逆位" if card.get("is_reverse") else "正位"
            position = str(card.get("position") or "").strip()
            description = self._compact_card_meaning(str(card.get("description") or "暂无牌义"))
            card_line = f"{name}（{orientation}）：{description}"
            summaries.append(f"{position}：\n{card_line}" if position else card_line)

        if not summaries:
            return "已抽到牌，但当前牌组没有可用的牌义文本。"
        if len(summaries) == 1:
            return summaries[0]
        return "\n".join(summaries)

    @staticmethod
    def _compact_card_meaning(description: str, max_items: int = 4) -> str:
        parts = [
            part.strip()
            for part in re.split(r"[、,，;；。.\s]+", description)
            if part.strip()
        ]
        if not parts:
            return "暂无牌义"
        return "、".join(parts[:max_items])

    def _format_card_names(self, card_details: list[dict[str, Any]]) -> str:
        parts = []
        for card in card_details:
            name = str(card.get("name") or "未知")
            orientation = "逆位" if card.get("is_reverse") else "正位"
            name = f"{name}（{orientation}）"
            position = self._format_position_label(str(card.get("position") or ""))
            parts.append(f"{position}：{name}" if position else name)
        return "\n".join(parts)

    @staticmethod
    def _format_position_label(position: str) -> str:
        normalized = str(position or "").strip()
        if not normalized:
            return ""
        return re.split(r"[，,]", normalized, maxsplit=1)[0].strip() or normalized

    def _map_card_type(self, card_type: str) -> str:
        normalized = str(card_type or "").strip()
        if not normalized or normalized == AUTO_CARD_TYPE:
            return AUTO_CARD_TYPE
        return CARD_TYPE_ALIASES.get(normalized, normalized)

    def _map_formation(self, formation: str) -> str:
        return FORMATION_ALIASES.get(str(formation or "").strip(), str(formation or "").strip() or "单张")

    def _get_position_name(self, represent_list: Any, index: int) -> str:
        try:
            names = represent_list[0]
            if isinstance(names, list) and index < len(names):
                return str(names[index])
        except (IndexError, TypeError):
            pass
        return f"位置{index + 1}"

    def _get_position_meaning(self, represent_list: Any, index: int, formation: str) -> str:
        try:
            meanings = represent_list[1]
            if isinstance(meanings, list) and index < len(meanings):
                return str(meanings[index])
        except (IndexError, TypeError):
            pass

        defaults: dict[str, str | list[str]] = {
            "单张": "当前状况",
            "圣三角": ["现状", "愿望", "行动"],
            "时间之流": ["过去", "现在", "未来"],
            "四要素": ["行动", "言语", "感情", "物质"],
            "五牌阵": ["现在或主要问题", "过去的影响", "未来", "主要原因", "行动结果"],
            "吉普赛十字": ["对方的想法", "你的想法", "问题", "环境", "结果"],
            "马蹄": ["现状", "可预知", "不可预知", "即将发生", "结果", "主观想法"],
            "六芒星": ["过去", "现在", "未来", "对策", "环境", "态度", "预测结果"],
        }
        meaning = defaults.get(formation, "未知")
        if isinstance(meaning, list) and index < len(meaning):
            return meaning[index]
        if isinstance(meaning, str):
            return meaning
        return "未知"

    def _find_card_image_path(self, card_data: dict[str, Any], is_reverse: bool) -> Path | None:
        card_name = str(card_data.get("name") or "").strip()
        image_dir = card_data.get("_image_dir")
        if not card_name or not isinstance(image_dir, Path):
            return None
        deck_dir = image_dir
        for filename in self._get_local_image_filenames(card_name, is_reverse):
            image_path = deck_dir / filename
            if image_path.exists():
                return image_path
        return None

    def _get_local_image_filenames(self, card_name: str, is_reverse: bool) -> list[str]:
        cleaned_name = card_name
        for source, target in NUMBER_NAME_MAP.items():
            cleaned_name = cleaned_name.replace(source, target)
        position = "逆位" if is_reverse else "正位"
        candidates = [f"{cleaned_name}{position}.jpg"]
        for source, target in CARD_NAME_ALIASES.items():
            if source in cleaned_name:
                candidates.append(f"{cleaned_name.replace(source, target)}{position}.jpg")
        return list(dict.fromkeys(candidates))

    def _render_template(self, template: str, **kwargs: str) -> str:
        if not template:
            return ""
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _render_prompt_template(self, template: str, fallback: str, **kwargs: str) -> str:
        selected = str(template or "").strip() or fallback
        try:
            return selected.format(**kwargs)
        except (KeyError, IndexError, ValueError) as exc:
            self.plugin.ctx.logger.warning("塔罗 AI 提示词模板渲染失败，使用默认提示词: %s", exc)
            return fallback.format(**kwargs)

    def _normalize_display_name(self, display_name: str) -> str:
        normalized = str(display_name or "").strip()
        if not normalized or normalized == "用户" or QQ_ID_PATTERN.fullmatch(normalized):
            return ""
        return normalized


class TarotsPlugin(MaiBotPlugin):
    """麦麦塔罗插件，适配 maibot-plugin-sdk v2。"""

    config_model = TarotsConfig
    config_reload_subscriptions = ("bot", "model")

    def __init__(self) -> None:
        super().__init__()
        self._runtime: TarotRuntime | None = None
        self._pending_tasks: set[asyncio.Task[Any]] = set()
        self._memory_silent_texts: dict[tuple[str, str], tuple[int, float]] = {}
        self._intercepted_message_keys: dict[tuple[str, str], float] = {}
        self._stream_execution_locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._bot_mention_names: tuple[str, ...] = ()
        self._available_llm_task_names: tuple[str, ...] = DEFAULT_LLM_TASK_NAMES

    async def on_load(self) -> None:
        await asyncio.gather(
            self._refresh_bot_mention_names(),
            self._refresh_available_llm_task_names(),
        )
        self._runtime = TarotRuntime(self)
        await self._runtime.reload()
        self.ctx.logger.info("麦麦塔罗插件已加载")

    async def on_unload(self) -> None:
        to_cancel = [task for task in self._pending_tasks if not task.done()]
        for task in to_cancel:
            task.cancel()
        if to_cancel:
            await asyncio.gather(*to_cancel, return_exceptions=True)
        self._pending_tasks.clear()
        self._memory_silent_texts.clear()
        self._intercepted_message_keys.clear()
        self._stream_execution_locks.clear()
        self.ctx.logger.info("麦麦塔罗插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        del config_data, version
        await self._refresh_bot_mention_names()
        if scope == "model":
            await self._refresh_available_llm_task_names()
        if self._runtime is not None:
            if scope == "bot":
                self._runtime._host_persona_context = ""
                self._runtime._host_reply_style = ""
                self._runtime._host_persona_cached_at = 0.0
            await self._runtime.reload()

    def get_webui_config_schema(
        self,
        *,
        plugin_id: str = "",
        plugin_name: str = "",
        plugin_version: str = "",
        plugin_description: str = "",
        plugin_author: str = "",
    ) -> dict[str, Any]:
        schema = super().get_webui_config_schema(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            plugin_description=plugin_description,
            plugin_author=plugin_author,
        )
        sections = schema.get("sections")
        if not isinstance(sections, dict):
            return schema

        plugin_section = sections.get("plugin")
        if isinstance(plugin_section, dict):
            fields = plugin_section.get("fields")
            if isinstance(fields, dict):
                config_version = fields.get("config_version")
                if isinstance(config_version, dict):
                    config_version["hidden"] = True
                    config_version["disabled"] = True
                    config_version["ui_type"] = "text"
                    config_version["input_type"] = "text"

        components_section = sections.get("components")
        if isinstance(components_section, dict):
            fields = components_section.get("fields")
            if isinstance(fields, dict):
                enable_tarots = fields.get("enable_tarots")
                if isinstance(enable_tarots, dict):
                    enable_tarots["label"] = "自然语言触发"
                    enable_tarots["hint"] = "开启后会拦截自然语言塔罗请求；未命中拦截时也允许 planner 调用塔罗兜底。"
                    enable_tarots["description"] = str(enable_tarots["hint"])
                    enable_tarots["order"] = 10
                enable_tarots_command = fields.get("enable_tarots_command")
                if isinstance(enable_tarots_command, dict):
                    enable_tarots_command["label"] = "启用 /塔罗 命令"
                    enable_tarots_command["hint"] = "开启后可使用 /塔罗、/tarot 或 /tarots 命令手动触发。"
                    enable_tarots_command["description"] = str(enable_tarots_command["hint"])
                    enable_tarots_command["order"] = 20
                natural_trigger_mode = fields.get("natural_trigger_mode")
                if isinstance(natural_trigger_mode, dict):
                    natural_trigger_mode["choices"] = list(NATURAL_TRIGGER_MODES)
                    natural_trigger_mode["ui_type"] = "select"
                    natural_trigger_mode["label"] = "自然语言触发模式"
                    natural_trigger_mode["hint"] = (
                        "严格是平衡规则的保守子集；平衡识别明确占卜请求；宽松额外识别带占卜主题的看看/算算类请求，"
                        "群聊中可能误触普通咨询，建议谨慎开启。"
                    )
                    natural_trigger_mode["description"] = str(natural_trigger_mode["hint"])
                    natural_trigger_mode["order"] = 11

        cards_section = sections.get("cards")
        if isinstance(cards_section, dict):
            fields = cards_section.get("fields")
            if isinstance(fields, dict):
                using_cards = fields.get("using_cards")
                if isinstance(using_cards, dict):
                    using_cards["choices"] = scan_available_card_sets()
                    using_cards["ui_type"] = "select"
                    using_cards["label"] = "当前牌组"
                    using_cards["hint"] = "只显示 tarot_jsons 下包含 tarots.json 的本地牌组"

        adjustment_section = sections.get("adjustment")
        if isinstance(adjustment_section, dict):
            fields = adjustment_section.get("fields")
            if isinstance(fields, dict):
                nickname_source = fields.get("nickname_source")
                if isinstance(nickname_source, dict):
                    nickname_source["choices"] = ["QQ昵称", "群名片"]
                    nickname_source["ui_type"] = "select"
                    nickname_source["label"] = "称呼来源"
                llm_model = fields.get("llm_model")
                if isinstance(llm_model, dict):
                    configured_task = str(self.config.adjustment.llm_model or "").strip()
                    choices = list(getattr(self, "_available_llm_task_names", DEFAULT_LLM_TASK_NAMES))
                    if configured_task and configured_task not in choices:
                        choices.insert(0, configured_task)
                    llm_model["choices"] = choices
                    llm_model["ui_type"] = "select"
                self._apply_adjustment_field_layout(fields, self.config.adjustment)

        return schema

    @staticmethod
    def _apply_adjustment_field_layout(fields: dict[str, Any], cfg: AdjustmentConfig) -> None:
        field_layout = {
            "nickname_source": {
                "label": "通用 / 称呼来源",
                "hint": "选择占卜回复优先使用 QQ 昵称还是群名片。",
                "order": 1,
                "group": "通用",
            },
            "llm_model": {
                "label": "通用 / AI 模型任务名",
                "hint": "准备台词、解读、延伸评论和 AI 失败提示共同使用的模型任务名。",
                "order": 2,
                "group": "通用",
            },
            "follow_bot_persona": {
                "label": "通用 / 遵循 MaiBot 人格",
                "hint": "开启后，所有 AI 生成文本会读取 MaiBot 当前人格与表达风格，并进行一次风格重写；关闭后只遵循塔罗提示词。",
                "order": 3,
                "group": "通用",
            },
            "send_card_names": {
                "label": "牌名与解读 / 报牌名",
                "hint": "开启后在占卜结果消息中加入“抽到的牌”列表，多张牌会逐行显示。",
                "order": 10,
                "group": "牌名与解读",
            },
            "send_interpretation": {
                "label": "牌名与解读 / 发送解读",
                "hint": "开启后将牌义解读与牌名列表合并为同一条占卜结果消息；关闭后只发送已开启的其它输出。",
                "order": 11,
                "group": "牌名与解读",
            },
            "ai_interpretation": {
                "label": "牌义解读 / AI 生成",
                "hint": "关闭时使用牌组 JSON 中的正逆位牌义文本。",
                "order": 12,
                "group": "牌名与解读",
            },
            "interpretation_prompt": {
                "label": "牌义解读 / AI 提示词",
                "hint": "占位符：{bot_style_context} {target_text} {formation} {cards_info}",
                "order": 13,
                "group": "牌名与解读",
                "ui_type": "textarea",
                "rows": 10,
            },
            "send_preface": {
                "label": "准备台词 / 发送",
                "hint": "关闭后不会发送准备台词，下方准备台词相关选项不生效。",
                "order": 20,
                "group": "准备台词",
            },
            "ai_preface": {
                "label": "准备台词 / AI 生成",
                "hint": "关闭时使用固定准备台词模板。",
                "order": 21,
                "group": "准备台词",
            },
            "contextual_preface": {
                "label": "准备台词 / 参照语境",
                "hint": "仅 AI 生成准备台词时生效，会参考触发语句。",
                "order": 22,
                "group": "准备台词",
            },
            "preface_text": {
                "label": "准备台词 / 固定模板",
                "hint": "AI 生成关闭或失败时使用。占位符：{user} {card_type} {formation}",
                "order": 23,
                "group": "准备台词",
            },
            "preface_prompt": {
                "label": "准备台词 / AI 提示词",
                "hint": "占位符：{bot_style_context} {user_line} {card_type} {formation} {context_line}",
                "order": 24,
                "group": "准备台词",
                "ui_type": "textarea",
                "rows": 10,
            },
            "send_extension_comment": {
                "label": "延伸评论 / 发送",
                "hint": "关闭后不会发送延伸评论，下方延伸评论相关选项不生效。",
                "order": 30,
                "group": "延伸评论",
            },
            "ai_extension_comment": {
                "label": "延伸评论 / AI 生成",
                "hint": "关闭时使用固定延伸评论模板。",
                "order": 31,
                "group": "延伸评论",
            },
            "contextual_extension_comment": {
                "label": "延伸评论 / 参照语境",
                "hint": "仅 AI 生成延伸评论时生效，会结合触发语句和抽牌内容。",
                "order": 32,
                "group": "延伸评论",
            },
            "extension_comment_text": {
                "label": "延伸评论 / 固定模板",
                "hint": "AI 生成关闭或失败时使用。占位符：{user} {formation}",
                "order": 33,
                "group": "延伸评论",
            },
            "extension_comment_prompt": {
                "label": "延伸评论 / AI 提示词",
                "hint": "占位符：{bot_style_context} {user_line} {formation} {context_text} {interpretation}",
                "order": 34,
                "group": "延伸评论",
                "ui_type": "textarea",
                "rows": 10,
            },
            "ai_failure_notice": {
                "label": "失败提示 / AI 生成",
                "hint": "后台占卜异常或超时时尝试生成一句自然提示；AI 不可用或 15 秒内未返回时自动使用固定文案。",
                "order": 40,
                "group": "失败处理",
            },
            "failure_notice_text": {
                "label": "失败提示 / 固定文案",
                "hint": "AI 生成关闭、返回空内容或超时时发送这段文案。",
                "order": 41,
                "group": "失败处理",
            },
            "failure_notice_prompt": {
                "label": "失败提示 / AI 提示词",
                "hint": "占位符：{bot_style_context}",
                "order": 42,
                "group": "失败处理",
                "ui_type": "textarea",
                "rows": 9,
            },
            "delay_preface_seconds": {
                "label": "发送节奏 / 准备台词延迟",
                "hint": "发送准备台词前等待的秒数。",
                "order": 50,
                "group": "发送节奏",
            },
            "delay_image_seconds": {
                "label": "发送节奏 / 图片延迟",
                "hint": "发送每张牌面图片前等待的秒数。",
                "order": 51,
                "group": "发送节奏",
            },
            "delay_text_seconds": {
                "label": "发送节奏 / 文字延迟",
                "hint": "发送牌名和解读前等待的秒数。",
                "order": 52,
                "group": "发送节奏",
            },
            "delay_extension_seconds": {
                "label": "发送节奏 / 延伸评论延迟",
                "hint": "发送延伸评论前等待的秒数。",
                "order": 53,
                "group": "发送节奏",
            },
            "delay_error_seconds": {
                "label": "发送节奏 / 错误提示延迟",
                "hint": "发送普通错误提示前等待的秒数。",
                "order": 54,
                "group": "发送节奏",
            },
        }

        for field_name, layout in field_layout.items():
            field = fields.get(field_name)
            if isinstance(field, dict):
                field.update(layout)
                field["description"] = str(layout.get("hint", ""))

    def _runtime_or_create(self) -> TarotRuntime:
        if self._runtime is None:
            self._runtime = TarotRuntime(self)
        return self._runtime

    async def _refresh_available_llm_task_names(self) -> None:
        try:
            available = await self.ctx.llm.get_available_models()
        except Exception as exc:
            self.ctx.logger.warning("塔罗插件读取可用 AI 模型任务失败，使用默认选项: %s", exc)
            return

        task_names = sorted(
            {
                str(task_name or "").strip()
                for task_name in available
                if str(task_name or "").strip()
            }
        )
        if task_names:
            self._available_llm_task_names = tuple(task_names)
        else:
            self.ctx.logger.warning("塔罗插件未取得可用 AI 模型任务，使用默认选项")

    async def _refresh_bot_mention_names(self) -> None:
        try:
            nickname, aliases, qq_account = await asyncio.gather(
                self.ctx.config.get("bot.nickname", ""),
                self.ctx.config.get("bot.alias_names", []),
                self.ctx.config.get("bot.qq_account", ""),
            )
        except Exception:
            self._bot_mention_names = ()
            logger_debug = getattr(self.ctx.logger, "debug", None)
            if callable(logger_debug):
                logger_debug("塔罗插件读取 Bot 名称失败，不处理文本形式 At", exc_info=True)
            return

        names: list[str] = []
        for value in (nickname, qq_account):
            clean_value = str(value or "").strip()
            if clean_value:
                names.append(clean_value)
        if isinstance(aliases, (list, tuple, set)):
            names.extend(str(alias or "").strip() for alias in aliases)
        elif aliases:
            names.append(str(aliases).strip())
        self._bot_mention_names = tuple(
            sorted(
                {name for name in names if name},
                key=len,
                reverse=True,
            )
        )

    async def _acquire_stream_execution_lock(self, stream_id: str) -> asyncio.Lock:
        clean_stream_id = str(stream_id or "").strip()
        lock_registry = getattr(self, "_stream_execution_locks", None)
        if lock_registry is None:
            lock_registry = {}
            self._stream_execution_locks = lock_registry

        lock, users = lock_registry.get(clean_stream_id, (asyncio.Lock(), 0))
        lock_registry[clean_stream_id] = (lock, users + 1)
        try:
            await lock.acquire()
        except BaseException:
            self._release_stream_execution_waiter(clean_stream_id, lock)
            raise
        return lock

    def _release_stream_execution_lock(self, stream_id: str, lock: asyncio.Lock) -> None:
        lock.release()
        self._release_stream_execution_waiter(str(stream_id or "").strip(), lock)

    def _release_stream_execution_waiter(self, stream_id: str, lock: asyncio.Lock) -> None:
        lock_registry = getattr(self, "_stream_execution_locks", None)
        if not isinstance(lock_registry, dict):
            return
        current = lock_registry.get(stream_id)
        if current is None or current[0] is not lock:
            return
        users = current[1] - 1
        if users <= 0:
            lock_registry.pop(stream_id, None)
        else:
            lock_registry[stream_id] = (lock, users)

    def _mark_memory_silent_text(self, stream_id: str, text: str) -> None:
        clean_stream_id = str(stream_id or "").strip()
        clean_text = self._normalize_request_text(text)
        if not clean_stream_id or not clean_text:
            return

        now = time.monotonic()
        self._cleanup_memory_silent_texts(now)
        key = (clean_stream_id, clean_text)
        current_count, _ = self._memory_silent_texts.get(key, (0, 0.0))
        if key not in self._memory_silent_texts and len(self._memory_silent_texts) >= MEMORY_SILENT_MAX_ENTRIES:
            oldest_key = min(
                self._memory_silent_texts,
                key=lambda item: self._memory_silent_texts[item][1],
            )
            self._memory_silent_texts.pop(oldest_key, None)
        self._memory_silent_texts[key] = (
            current_count + 1,
            now + MEMORY_SILENT_TTL_SECONDS,
        )

    def _consume_memory_silent_text(self, stream_id: str, text: str) -> bool:
        self._cleanup_memory_silent_texts()
        key = (str(stream_id or "").strip(), self._normalize_request_text(text))
        count, expires_at = self._memory_silent_texts.get(key, (0, 0.0))
        if count <= 0:
            return False
        if count == 1:
            self._memory_silent_texts.pop(key, None)
        else:
            self._memory_silent_texts[key] = (count - 1, expires_at)
        return True

    def _unmark_memory_silent_text(self, stream_id: str, text: str) -> None:
        self._consume_memory_silent_text(stream_id, text)

    def _cleanup_memory_silent_texts(self, now: float | None = None) -> None:
        current_time = time.monotonic() if now is None else now
        expired_keys = [
            key
            for key, (_, expires_at) in self._memory_silent_texts.items()
            if expires_at <= current_time
        ]
        for key in expired_keys:
            self._memory_silent_texts.pop(key, None)

    def _build_message_dedupe_key(self, message: dict | None, stream_id: str, request_text: str) -> tuple[str, str]:
        clean_stream_id = str(stream_id or "").strip()
        if isinstance(message, dict):
            message_info = message.get("message_info")
            if isinstance(message_info, dict):
                for key in ("message_id", "id", "message_seq", "seq"):
                    value = str(message_info.get(key) or "").strip()
                    if value:
                        return clean_stream_id, value
            for key in ("message_id", "id", "message_seq", "seq"):
                value = str(message.get(key) or "").strip()
                if value:
                    return clean_stream_id, value
        return clean_stream_id, self._normalize_request_text(request_text)

    def _mark_intercepted_message(self, message: dict | None, stream_id: str, request_text: str) -> None:
        key = self._build_message_dedupe_key(message, stream_id, request_text)
        if not key[0] or not key[1]:
            return
        self._cleanup_intercepted_message_keys()
        self._intercepted_message_keys[key] = time.monotonic() + 10.0

    def _consume_intercepted_message(self, message: dict | None, stream_id: str, request_text: str) -> bool:
        key = self._build_message_dedupe_key(message, stream_id, request_text)
        expires_at = self._intercepted_message_keys.pop(key, 0.0)
        return expires_at >= time.monotonic()

    def _cleanup_intercepted_message_keys(self) -> None:
        now = time.monotonic()
        expired_keys = [key for key, expires_at in self._intercepted_message_keys.items() if expires_at < now]
        for key in expired_keys:
            self._intercepted_message_keys.pop(key, None)

    @HookHandler(
        "send_service.before_send",
        name="tarots_memory_silent_sender",
        description="将塔罗插件文字消息标记为临时内容且不写库，避免触发长期记忆人物事实写回",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        timeout_ms=3000,
        error_policy=ErrorPolicy.SKIP,
    )
    async def handle_tarots_before_send(
        self,
        message: dict | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        del kwargs
        if not isinstance(message, dict):
            return None
        stream_id = str(message.get("session_id") or "").strip()
        text = self._extract_message_text(message)
        if not self._consume_memory_silent_text(stream_id, text):
            return None

        modified_message = dict(message)
        # 不能设为空：发送服务会在 Hook 后根据真实消息组件重新生成文本。
        # 使用长期记忆明确忽略的短暂标记，并关闭消息入库；平台实际发送内容仍取 raw_message，不受影响。
        modified_message["processed_plain_text"] = MEMORY_SILENT_PLACEHOLDER
        return {
            "modified_kwargs": {
                "message": modified_message,
                "storage_message": False,
            }
        }

    async def _send_background_failure_notice(
        self,
        stream_id: str,
        label: str,
        user_request: str = "",
    ) -> None:
        cfg = self.config.adjustment
        notice = str(getattr(cfg, "failure_notice_text", "") or "").strip() or DEFAULT_FAILURE_NOTICE_TEXT
        if getattr(cfg, "ai_failure_notice", False):
            runtime = self._runtime_or_create()
            ai_style_context = await runtime._build_ai_style_context(user_request)
            prompt = runtime._render_prompt_template(
                getattr(cfg, "failure_notice_prompt", DEFAULT_FAILURE_NOTICE_PROMPT),
                DEFAULT_FAILURE_NOTICE_PROMPT,
                bot_style_context="请严格遵守系统消息中的身份、表达方式与塔罗任务边界。",
            )
            try:
                generated = await asyncio.wait_for(
                    runtime._call_llm(prompt, max_len=80, system_prompt=ai_style_context),
                    timeout=15.0,
                )
            except asyncio.TimeoutError:
                self.ctx.logger.warning("[%s] AI 失败提示生成超时，使用固定文案", label)
            except Exception as exc:
                self.ctx.logger.error("[%s] AI 失败提示生成异常: %s", label, exc, exc_info=True)
            else:
                if generated:
                    notice = generated

        self._mark_memory_silent_text(stream_id, notice)
        try:
            sent = await self.ctx.send.text(notice, stream_id)
        except Exception as exc:
            self._unmark_memory_silent_text(stream_id, notice)
            self.ctx.logger.error("[%s] 后台失败提示发送异常: %s", label, exc, exc_info=True)
            return
        if not sent:
            self._unmark_memory_silent_text(stream_id, notice)
            self.ctx.logger.error("[%s] 后台失败提示发送失败: send.text 返回 False", label)

    def _spawn_background_task(
        self,
        coro: Any,
        label: str,
        timeout: float = 120.0,
        failure_stream_id: str = "",
        failure_user_request: str = "",
    ) -> asyncio.Task[Any]:
        async def _runner() -> None:
            try:
                await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                self.ctx.logger.warning("[%s] 后台任务超时 %.1fs，已取消", label, timeout)
                if failure_stream_id:
                    await self._send_background_failure_notice(
                        failure_stream_id,
                        label,
                        failure_user_request,
                    )
            except Exception:
                self.ctx.logger.exception("[%s] 后台任务异常", label)
                if failure_stream_id:
                    await self._send_background_failure_notice(
                        failure_stream_id,
                        label,
                        failure_user_request,
                    )

        task = asyncio.create_task(_runner())
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        return task

    @HookHandler(
        "chat.receive.before_process",
        name="tarots_before_process_handler",
        description="拦截自然语言塔罗占卜请求并由插件后台执行，避免进入普通回复链路",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        timeout_ms=3000,
        error_policy=ErrorPolicy.SKIP,
    )
    async def handle_tarots_before_process(
        self,
        message: dict | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        del kwargs
        if not self.config.plugin.enabled or not self.config.components.enable_tarots:
            return None
        if not isinstance(message, dict) or bool(message.get("is_command")):
            return None

        request_text = self._normalize_request_text(self._extract_message_text(message))
        if not self._is_tarot_divination_request(request_text, self.config.components.natural_trigger_mode):
            return None

        stream_id = str(message.get("session_id") or "").strip()
        if not stream_id:
            return None

        self._mark_intercepted_message(message, stream_id, request_text)
        self._spawn_background_task(
            self._execute_intercepted_tarots(message, stream_id, request_text),
            "tarots_intercept",
            failure_stream_id=stream_id,
            failure_user_request=request_text,
        )
        return {"action": "abort"}

    async def _execute_intercepted_tarots(self, message: dict, stream_id: str, request_text: str) -> None:
        card_type, formation = self._parse_natural_request_options(request_text)
        target_user = self._extract_message_user_nickname(message)
        runtime = self._runtime_or_create()
        success, result_message = await runtime.execute(
            stream_id,
            card_type,
            formation,
            target_user,
            request_text,
        )
        log_method = self.ctx.logger.info if success else self.ctx.logger.warning
        log_method("塔罗自然语言请求已由插件拦截处理: success=%s result=%s", success, result_message)

    @Tool(
        "tarots",
        description=(
            "进行真实的塔罗牌占卜：随机抽牌，在图片可用时发送牌面，并发送牌名和简短解读。"
            "当用户明确要求现在为其执行塔罗占卜、抽牌、算一卦、测一测、问牌时使用；"
            "不要直接用 reply 编造牌面或占卜结果。"
            "调用时必须填写 stream_id 和 user_request。"
            "用户只是询问塔罗牌知识、牌义、正逆位含义、牌阵说明、某张牌怎么解读时，不应调用本工具。"
            "例如“圣杯7 逆位是什么意思”“恋人正位代表什么”“塔罗有哪些牌阵”这类问题都不是占卜请求。"
            "本工具会自行发送牌面图片、牌名和简短解读，调用后不需要额外解释同一件事。"
            "如果用户要求其它类型的占卜或普通聊天，不应调用本工具。"
        ),
        parameters=[
            ToolParameterInfo(
                name="stream_id",
                param_type=ToolParamType.STRING,
                description="当前聊天流 ID，必须填写。",
                required=True,
            ),
            ToolParameterInfo(
                name="card_type",
                param_type=ToolParamType.STRING,
                description=(
                    "抽牌范围，可选：自动、全部、大阿卡纳、小阿卡纳。"
                    "用户没有明确要求范围时必须填自动；只有用户明确说全部牌时才填全部。"
                ),
                required=False,
                default=AUTO_CARD_TYPE,
                enum_values=[AUTO_CARD_TYPE, "全部", "大阿卡纳", "小阿卡纳"],
            ),
            ToolParameterInfo(
                name="formation",
                param_type=ToolParamType.STRING,
                description="牌阵，可选：单张、圣三角、时间之流、四要素、五牌阵、吉普赛十字、马蹄、六芒星。用户没有明确要求时填单张。",
                required=False,
                default="单张",
            ),
            ToolParameterInfo(
                name="target_user",
                param_type=ToolParamType.STRING,
                description="提出占卜请求的用户昵称。",
                required=False,
                default="用户",
            ),
            ToolParameterInfo(
                name="user_request",
                param_type=ToolParamType.STRING,
                description="用户触发占卜的完整原话或占卜问题，例如“帮我占卜一下我今年还能瘦吗”。必须填写。",
                required=True,
            ),
            ToolParameterInfo(
                name="text",
                param_type=ToolParamType.STRING,
                description="兼容字段：用户消息文本。优先使用 user_request；没有 user_request 时才使用此字段。",
                required=False,
                default="",
            ),
        ],
        timeout_ms=120000,
    )
    async def handle_tarots_tool(
        self,
        stream_id: str = "",
        card_type: str = AUTO_CARD_TYPE,
        formation: str = "单张",
        target_user: str = "用户",
        user_request: str = "",
        text: str = "",
        message: dict | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        if not self.config.components.enable_tarots:
            return {"success": False, "content": "塔罗工具未启用"}
        runtime = self._runtime_or_create()
        nickname = runtime._normalize_display_name(self._extract_message_user_nickname(message) or target_user)
        request_text = self._normalize_request_text(user_request or text or self._extract_message_text(message))
        success, result_message = await runtime.execute(stream_id, card_type, formation, nickname, request_text)
        content = (
            f"{result_message}。插件已发送完整塔罗占卜结果；不要再调用 reply 或 send_emoji，下一步必须 no_action 或 finish，等待新消息。"
            if success
            else result_message
        )
        return {
            "success": success,
            "content": content,
            "metadata": {"pause_execution": success},
        }

    @EventHandler(
        "tarots_message_handler",
        description="自动拦截明确的塔罗占卜请求并执行抽牌，避免普通回复直接编造牌面。",
        event_type=EventType.ON_MESSAGE,
        intercept_message=True,
        weight=50,
    )
    async def handle_tarots_message(
        self,
        message: dict | None = None,
        stream_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        if not self.config.plugin.enabled or not self.config.components.enable_tarots:
            return {"continue_processing": True}
        if not isinstance(message, dict) or bool(message.get("is_command")):
            return {"continue_processing": True}

        request_text = self._normalize_request_text(self._extract_message_text(message))
        if not self._is_tarot_divination_request(request_text, self.config.components.natural_trigger_mode):
            return {"continue_processing": True}

        target_stream_id = stream_id or str(message.get("session_id") or "").strip()
        if not target_stream_id:
            return {"continue_processing": True}
        if self._consume_intercepted_message(message, target_stream_id, request_text):
            return {
                "continue_processing": False,
                "custom_result": {
                    "success": True,
                    "message": "塔罗请求已由 chat.receive.before_process Hook 接管处理",
                },
            }

        card_type, formation = self._parse_natural_request_options(request_text)
        target_user = self._extract_message_user_nickname(message)
        runtime = self._runtime_or_create()
        success, result_message = await runtime.execute(
            target_stream_id,
            card_type,
            formation,
            target_user,
            request_text,
        )
        return {
            "continue_processing": False,
            "custom_result": {
                "success": success,
                "message": result_message,
            },
        }

    @Command(
        "tarots_command",
        description=(
            "手动触发塔罗牌占卜，用法：/塔罗、/tarot 或 /tarots "
            "[全部|大阿卡纳|小阿卡纳] [牌阵]；未填写范围时使用当前牌组原生类别"
        ),
        pattern=r"^(?:/塔罗|/tarot|/tarots)(?:\s+(?P<args>.*))?\s*$",
    )
    async def handle_tarots_command(
        self,
        stream_id: str = "",
        user_nickname: str = "",
        user_id: str = "",
        matched_groups: dict | None = None,
        message: dict | None = None,
        text: str = "",
        **kwargs: Any,
    ) -> tuple[bool, str, bool]:
        del kwargs
        if not self.config.components.enable_tarots_command:
            return False, "塔罗命令未启用", True

        args = str((matched_groups or {}).get("args") or "").strip()
        card_type, formation = self._parse_command_args(args)
        target_user = self._extract_message_user_nickname(message)
        runtime = self._runtime_or_create()
        success, result_message = await runtime.execute(stream_id, card_type, formation, target_user, text or args)
        return success, result_message, True

    def _extract_message_text(self, message: dict | None) -> str:
        if not isinstance(message, dict):
            return ""

        raw_message = message.get("raw_message")
        if isinstance(raw_message, list):
            parts: list[str] = []
            for item in raw_message:
                if not isinstance(item, dict):
                    continue
                data = item.get("data")
                if item.get("type") == "text" and isinstance(data, str):
                    parts.append(data)
                elif item.get("type") == "text" and isinstance(data, dict):
                    text_value = data.get("text") or data.get("content")
                    if isinstance(text_value, str):
                        parts.append(text_value)
            raw_text = "".join(parts)
            if raw_text.strip():
                return raw_text

        for key in ("processed_plain_text", "plain_text", "text"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _normalize_request_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _strip_own_text_mention(self, text: str) -> str:
        normalized = self._normalize_request_text(text)
        if not normalized or normalized[0] not in {"@", "＠"}:
            return normalized
        for name in getattr(self, "_bot_mention_names", ()):
            pattern = rf"^[＠@]\s*{re.escape(name)}(?:\s*[,，:：、]\s*|\s+)"
            stripped = re.sub(pattern, "", normalized, count=1, flags=re.IGNORECASE)
            if stripped != normalized:
                return stripped.strip()
        return normalized

    def _is_tarot_divination_request(self, text: str, mode: str = "平衡") -> bool:
        normalized_text = self._strip_own_text_mention(text)
        if not normalized_text:
            return False

        normalized_mode = mode if mode in NATURAL_TRIGGER_MODES else "平衡"
        if TAROT_KNOWLEDGE_PATTERN.search(normalized_text) or TAROT_DISCUSSION_PATTERN.search(normalized_text):
            return False

        explicit_safe_request = bool(
            TAROT_SHORT_COMMAND_PATTERN.fullmatch(normalized_text)
            or BALANCED_CHINESE_REQUEST_PATTERN.search(normalized_text)
            or BALANCED_ENGLISH_REQUEST_PATTERN.search(normalized_text)
            or BALANCED_TOPIC_REQUEST_PATTERN.search(normalized_text)
        )
        if normalized_mode == "严格":
            return bool(
                STRICT_COMPAT_REQUEST_PATTERN.search(normalized_text)
                and explicit_safe_request
            )
        if normalized_mode == "平衡":
            return explicit_safe_request
        if normalized_mode == "宽松":
            return bool(
                explicit_safe_request
                or (LOOSE_REQUEST_PATTERN.search(normalized_text) and LOOSE_TOPIC_PATTERN.search(normalized_text))
            )
        return explicit_safe_request

    def _parse_natural_request_options(self, text: str) -> tuple[str, str]:
        card_type = AUTO_CARD_TYPE
        for alias, mapped in sorted(
            NATURAL_CARD_TYPE_ALIASES.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if alias and alias in text:
                card_type = mapped
                break

        formation = "单张"
        for alias, mapped in sorted(
            NATURAL_FORMATION_ALIASES.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if alias and alias in text:
                formation = mapped
                break
        return card_type, formation

    def _extract_message_user_nickname(self, message: dict | None) -> str:
        if not isinstance(message, dict):
            return ""

        message_info = message.get("message_info") or {}
        if not isinstance(message_info, dict):
            message_info = {}
        user_info = message_info.get("user_info") or message.get("user_info") or {}
        if not isinstance(user_info, dict):
            user_info = {}

        key_groups = {
            "QQ昵称": (
                (user_info, "user_nickname"),
                (user_info, "nickname"),
                (user_info, "name"),
                (message, "user_nickname"),
                (message, "nickname"),
                (message, "sender_nickname"),
                (user_info, "user_cardname"),
                (message, "user_cardname"),
            ),
            "qq_nickname": (
                (user_info, "user_nickname"),
                (user_info, "nickname"),
                (user_info, "name"),
                (message, "user_nickname"),
                (message, "nickname"),
                (message, "sender_nickname"),
                (user_info, "user_cardname"),
                (message, "user_cardname"),
            ),
            "群名片": (
                (user_info, "user_cardname"),
                (message, "user_cardname"),
                (user_info, "user_nickname"),
                (user_info, "nickname"),
                (user_info, "name"),
                (message, "user_nickname"),
                (message, "nickname"),
                (message, "sender_nickname"),
            ),
            "group_card": (
                (user_info, "user_cardname"),
                (message, "user_cardname"),
                (user_info, "user_nickname"),
                (user_info, "nickname"),
                (user_info, "name"),
                (message, "user_nickname"),
                (message, "nickname"),
                (message, "sender_nickname"),
            ),
        }
        nickname_source = str(self.config.adjustment.nickname_source).strip()
        if nickname_source not in key_groups:
            self.ctx.logger.error("未知称呼来源配置: %s，可选 QQ昵称 或 群名片", nickname_source)
            return ""

        for source, key in key_groups[nickname_source]:
            value = str(source.get(key) or "").strip()
            if value and not QQ_ID_PATTERN.fullmatch(value):
                return value

        return ""

    def _parse_command_args(self, args: str) -> tuple[str, str]:
        card_type = AUTO_CARD_TYPE
        formation = "单张"
        for part in [item.strip() for item in args.split() if item.strip()]:
            mapped_card_type = CARD_TYPE_ALIASES.get(part)
            if mapped_card_type:
                card_type = mapped_card_type
                continue
            mapped_formation = FORMATION_ALIASES.get(part)
            if mapped_formation:
                formation = mapped_formation
        return card_type, formation


def create_plugin() -> TarotsPlugin:
    return TarotsPlugin()
