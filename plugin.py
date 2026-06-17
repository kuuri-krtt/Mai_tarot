from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from maibot_sdk import Action, Command, EventHandler, Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ActivationType, ErrorPolicy, EventType, HookMode, HookOrder

import asyncio
import base64
import json
import random
import re

PLUGIN_DIR = Path(__file__).parent
TAROT_DIR = PLUGIN_DIR / "tarot_jsons"
QQ_ID_PATTERN = re.compile(r"^\d{5,}$")
TAROT_REQUEST_PATTERN = re.compile(
    r"(占卜一下|帮.*?占卜|给.*?占卜|为.*?占卜|塔罗占卜|塔罗一下|塔罗.*?看看|用塔罗.*?看|抽.*?牌|算一卦|算卦|测一测|测测|问牌)"
)
TAROT_TOPIC_PATTERN = re.compile(r"(塔罗|占卜|牌面).{0,20}(能不能|可不可以|会不会|是否|还能|今年|未来|最近|吗|嘛)")
TAROT_KNOWLEDGE_PATTERN = re.compile(r"(是什么|什么意思|含义|牌义|有哪些|说明|介绍|教程|怎么解读|代表什么)")
LOOSE_REQUEST_PATTERN = re.compile(r"(帮.*?看看|帮.*?看|看一下|看看|算算|算一下|测一下|测测)")
LOOSE_TOPIC_PATTERN = re.compile(r"(能不能|可不可以|会不会|是否|还能|今年|未来|最近|今晚|明天|感情|恋爱|工作|运势|结果|发展|有戏|机会|吗|嘛)")
NATURAL_TRIGGER_MODES = ("严格", "平衡", "宽松")


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
    "全": "全部",
    "全部": "全部",
    "阿卡纳": "全部",
    "阿卡那": "全部",
    "阿尔卡纳": "全部",
    "阿尔卡那": "全部",
    "阿尔克那": "全部",
    "大": "大阿卡纳",
    "大阿": "大阿卡纳",
    "大阿卡纳": "大阿卡纳",
    "大阿卡那": "大阿卡纳",
    "大牌": "大阿卡纳",
    "小": "小阿卡纳",
    "小阿": "小阿卡纳",
    "小阿卡纳": "小阿卡纳",
    "小阿卡那": "小阿卡纳",
    "小牌": "小阿卡纳",
}
FORMATION_ALIASES = {
    "单": "单张",
    "单张": "单张",
    "一张": "单张",
    "圣": "圣三角",
    "圣三角": "圣三角",
    "三角": "圣三角",
    "时间": "时间之流",
    "时间之流": "时间之流",
    "四": "四要素",
    "四要素": "四要素",
    "四元素": "四要素",
    "五": "五牌阵",
    "五牌": "五牌阵",
    "五牌阵": "五牌阵",
    "吉": "吉普赛十字",
    "吉普赛": "吉普赛十字",
    "吉普赛十字": "吉普赛十字",
    "马": "马蹄",
    "马蹄": "马蹄",
    "六": "六芒星",
    "六芒": "六芒星",
    "六芒星": "六芒星",
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
        default="1.2.0",
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
        description="严格只拦截明确塔罗/占卜请求；平衡兼顾常见自然语言；宽松会尝试拦截更多看看/算算类请求",
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

    send_card_names: bool = Field(default=True, description="是否发送抽到的牌名列表", json_schema_extra={"label": "报牌名"})
    send_interpretation: bool = Field(default=True, description="是否发送牌义解读", json_schema_extra={"label": "发送牌义解读"})
    ai_interpretation: bool = Field(default=True, description="是否使用 AI 生成塔罗解读", json_schema_extra={"label": "AI 解读"})
    send_preface: bool = Field(default=True, description="占卜前是否发送准备台词", json_schema_extra={"label": "发送准备台词"})
    ai_preface: bool = Field(default=True, description="准备台词是否使用 AI 生成", json_schema_extra={"label": "AI 生成准备台词"})
    contextual_preface: bool = Field(
        default=True,
        description="AI 生成准备台词时是否参考触发语句中的占卜要求和前文语境",
        json_schema_extra={"label": "准备台词参照语境"},
    )
    send_extension_comment: bool = Field(default=True, description="占卜后是否发送延伸评论", json_schema_extra={"label": "发送延伸评论"})
    ai_extension_comment: bool = Field(default=True, description="延伸评论是否使用 AI 生成", json_schema_extra={"label": "AI 生成延伸评论"})
    contextual_extension_comment: bool = Field(
        default=True,
        description="AI 生成延伸评论时是否结合触发语句和抽牌内容",
        json_schema_extra={"label": "延伸评论参照语境"},
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
        self.available_card_sets: list[str] = []
        self.using_cards = ""

    async def reload(self) -> None:
        """重新扫描牌组并加载配置中的牌组。"""

        self.available_card_sets = self._scan_available_card_sets()
        configured = str(self.plugin.config.cards.using_cards or "").strip()
        if configured in self.available_card_sets:
            self.using_cards = configured
        else:
            self.using_cards = self.available_card_sets[0] if self.available_card_sets else ""
            if configured:
                self.plugin.ctx.logger.warning(
                    "配置的塔罗牌组 %s 不可用，临时切换为 %s",
                    configured,
                    self.using_cards or "无可用牌组",
                )

        self.card_map = {}
        self.formation_map = {}
        if not self.using_cards:
            self.plugin.ctx.logger.error("未发现任何可用塔罗牌组")
            return

        cards_json_path = TAROT_DIR / self.using_cards / "tarots.json"
        formation_json_path = TAROT_DIR / "formation.json"
        try:
            self.card_map = json.loads(cards_json_path.read_text(encoding="utf-8"))
            self.formation_map = json.loads(formation_json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.card_map = {}
            self.formation_map = {}
            self.plugin.ctx.logger.error("加载塔罗资源失败: %s", exc, exc_info=True)
            return

        total_cards = self.card_map.get("_meta", {}).get("total_cards", len(self.card_map) - 1)
        self.plugin.ctx.logger.info(
            "塔罗牌组已加载: cards=%s total=%s formations=%s",
            self.using_cards,
            total_cards,
            len(self.formation_map),
        )

    def _scan_available_card_sets(self) -> list[str]:
        return scan_available_card_sets()

    async def execute(
        self,
        stream_id: str,
        card_type: str = "全部",
        formation: str = "单张",
        target_user: str = "",
        user_request: str = "",
    ) -> tuple[bool, str]:
        """执行一次塔罗占卜。"""

        if not self.plugin.config.plugin.enabled:
            return False, "塔罗插件未启用"
        if not stream_id:
            return False, "无法获取聊天流"
        if not self.card_map or not self.formation_map:
            await self.reload()
        if not self.card_map:
            await self._send_after_delay("error", "没有可用的塔罗牌组，无法占卜。", stream_id)
            return False, "没有可用牌组"

        card_type = self._map_card_type(card_type)
        formation = self._map_formation(formation)
        target_user = self._normalize_display_name(target_user)

        if card_type not in {"全部", "大阿卡纳", "小阿卡纳"}:
            await self._send_after_delay("error", "不存在的抽牌范围，可选：全部、大阿卡纳、小阿卡纳。", stream_id)
            return False, "抽牌范围错误"
        if formation not in self.formation_map:
            await self._send_after_delay("error", f"不存在的牌阵：{formation}", stream_id)
            return False, "牌阵错误"

        if self.plugin.config.adjustment.send_preface:
            preface = await self._build_preface(target_user, card_type, formation, user_request)
            if preface:
                await self._send_after_delay("preface", preface, stream_id)
                await asyncio.sleep(0.4)

        selected_cards = self._draw_cards(card_type, formation)
        if not selected_cards:
            await self._send_after_delay("error", "当前牌组数据不完整，无法抽牌。", stream_id)
            return False, "牌组数据不完整"

        card_details: list[dict[str, Any]] = []
        sent_images = 0
        represent_list = self.formation_map[formation].get("represent", [])
        for index, (card_id, is_reverse) in enumerate(selected_cards):
            card_data = self.card_map.get(card_id, {})
            if not isinstance(card_data, dict):
                continue

            await self._delay_before_send("image")
            if await self._send_card_image(card_data, is_reverse, stream_id):
                sent_images += 1
                await asyncio.sleep(0.5)

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

        if not sent_images:
            await self._send_after_delay("error", "塔罗牌图片发送失败，无法继续占卜。", stream_id)
            return False, "图片发送失败"

        await asyncio.sleep(1)
        card_names_text = self._format_card_names(card_details)
        if self.plugin.config.adjustment.send_card_names and card_names_text:
            await self._send_after_delay("text", f"抽到的牌：\n{card_names_text}", stream_id)
            await asyncio.sleep(0.5)

        interpretation = ""
        if self.plugin.config.adjustment.send_interpretation:
            interpretation = await self._generate_interpretation(card_details, formation, target_user)
            await self._send_after_delay("text", interpretation, stream_id)

        if self.plugin.config.adjustment.send_extension_comment:
            extension = await self._build_extension(target_user, formation, interpretation, user_request, card_details)
            if extension:
                await self._send_after_delay("extension", extension, stream_id)

        if target_user:
            return True, f"已为{target_user}抽取塔罗牌"
        return True, "已抽取塔罗牌"

    def _draw_cards(self, card_type: str, formation_name: str) -> list[tuple[str, bool]]:
        formation = self.formation_map.get(formation_name, {})
        cards_num = int(formation.get("cards_num", 1))
        valid_ids = self._get_card_range(card_type)
        valid_ids = [card_id for card_id in valid_ids if card_id in self.card_map]
        if len(valid_ids) < cards_num:
            return []

        selected_ids = random.sample(valid_ids, cards_num)
        is_cut = bool(formation.get("is_cut", False))
        return [(card_id, is_cut and random.random() < 0.5) for card_id in selected_ids]

    async def _send_card_image(self, card_data: dict[str, Any], is_reverse: bool, stream_id: str) -> bool:
        card_name = str(card_data.get("name") or "").strip()
        if not card_name:
            return False

        image_path = self._find_card_image_path(card_name, is_reverse)
        if image_path is None:
            self.plugin.ctx.logger.error("塔罗牌图片不存在: cards=%s name=%s reverse=%s", self.using_cards, card_name, is_reverse)
            return False

        try:
            img_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
            await self.plugin.ctx.send.image(img_base64, stream_id)
            return True
        except Exception as exc:
            self.plugin.ctx.logger.error("发送塔罗牌图片失败: %s", exc, exc_info=True)
            return False

    async def _send_after_delay(self, stage: str, text: str, stream_id: str) -> None:
        await self._delay_before_send(stage)
        self.plugin._mark_memory_silent_text(stream_id, text)
        await self.plugin.ctx.send.text(text, stream_id)

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
        """构建插件内置的对外发言风格要求。"""

        return "\n".join(
            [
                "【塔罗回复风格】",
                "你正在作为麦麦塔罗插件生成对外发送的文本。",
                "请使用简体中文，语气自然、简短、温和，不要自称专业占卜师。",
                "不要编造没有抽到的牌面，也不要输出与本次塔罗结果无关的内容。",
            ]
        )

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
            bot_style_context = self._build_bot_style_context()
            prompt = (
                f"{bot_style_context}\n\n"
                "你是塔罗占卜助手，请生成一句占卜前的准备台词。\n"
                "要求：只输出一句话，10-30字，自然亲切，不透露具体牌面。"
                "如果没有用户昵称，就用“好的”“知道了”“明白了”这类无称呼开头。\n\n"
                f"{user_line}\n抽牌范围：{card_type}\n牌阵：{formation}\n{context_line}\n\n"
                "准备台词："
            )
            generated = await self._call_llm(prompt, max_len=80)
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
            bot_style_context = self._build_bot_style_context()
            prompt = (
                f"{bot_style_context}\n\n"
                "你是塔罗占卜助手，请生成一句占卜后的延伸评论。\n"
                "要求：只输出一句话，字数不限，温和自然，不复述牌面。"
                "如果没有用户昵称，就不要称呼用户。\n\n"
                f"{user_line}\n牌阵：{formation}\n{context_text}\n上文解读：{interpretation}\n\n"
                "延伸评论："
            )
            generated = await self._call_llm(prompt, max_len=60)
            if generated:
                return generated
        if not user and "{user}" in template:
            return random.choice(("先把这句记心里，慢慢来就好。", "整体先别急，按自己的节奏走。", "放轻松，接下来顺着感觉调整就好。"))
        return self._render_template(template, user=user, formation=formation)

    async def _generate_interpretation(self, card_details: list[dict[str, Any]], formation: str, user: str) -> str:
        if self.plugin.config.adjustment.ai_interpretation:
            cards_info = self._format_cards_for_prompt(card_details)
            target_text = f"为{user}解读塔罗牌" if user else "解读塔罗牌，不要称呼用户"
            bot_style_context = self._build_bot_style_context()
            prompt = (
                f"{bot_style_context}\n\n"
                f"请用轻松自然的语气{target_text}，保持非常简短（2-3句话）。\n\n"
                f"牌阵：{formation}\n抽到的牌：{cards_info}\n\n"
                "请用1句话总结牌面意思，再用1句话给出实用建议。不要用专业术语，不要讲大道理。\n"
                "你的解读（50字以内）："
            )
            generated = await self._call_llm(prompt, max_len=100)
            if generated:
                return generated
        return self._generate_fallback_interpretation(card_details, user)

    def _format_cards_for_prompt(self, card_details: list[dict[str, Any]]) -> str:
        return "；".join(
            f"{card['position']}：{card['name']}（{'逆位' if card['is_reverse'] else '正位'}，{card['description']}）"
            for card in card_details
        )

    async def _call_llm(self, prompt: str, max_len: int) -> str:
        try:
            result = await self.plugin.ctx.llm.generate(
                prompt=prompt,
                model=self.plugin.config.adjustment.llm_model or "replyer",
                temperature=0.7,
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

        reply = reply.replace("\n", " ").strip(" \"'")
        if 0 < len(reply) <= max_len:
            return reply
        return ""

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
        return CARD_TYPE_ALIASES.get(str(card_type or "").strip(), str(card_type or "").strip() or "全部")

    def _map_formation(self, formation: str) -> str:
        return FORMATION_ALIASES.get(str(formation or "").strip(), str(formation or "").strip() or "单张")

    def _get_card_range(self, card_type: str) -> list[str]:
        if card_type == "大阿卡纳":
            return [str(i) for i in range(22)]
        if card_type == "小阿卡纳":
            return [str(i) for i in range(22, 78)]
        return [str(i) for i in range(78)]

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

    def _find_card_image_path(self, card_name: str, is_reverse: bool) -> Path | None:
        deck_dir = TAROT_DIR / self.using_cards
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

    def _normalize_display_name(self, display_name: str) -> str:
        normalized = str(display_name or "").strip()
        if not normalized or normalized == "用户" or QQ_ID_PATTERN.fullmatch(normalized):
            return ""
        return normalized


class TarotsPlugin(MaiBotPlugin):
    """麦麦塔罗插件，适配 maibot-plugin-sdk v2。"""

    config_model = TarotsConfig

    def __init__(self) -> None:
        super().__init__()
        self._runtime: TarotRuntime | None = None
        self._pending_tasks: set[asyncio.Task[Any]] = set()
        self._memory_silent_texts: dict[tuple[str, str], int] = {}

    async def on_load(self) -> None:
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
        self.ctx.logger.info("麦麦塔罗插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        del scope, config_data, version
        if self._runtime is not None:
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
                        "严格只拦截明确塔罗/占卜请求；平衡兼顾常见自然语言；宽松会尝试拦截更多看看/算算类请求。"
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
                self._apply_adjustment_field_layout(fields, self.config.adjustment)

        return schema

    @staticmethod
    def _apply_adjustment_field_layout(fields: dict[str, Any], cfg: AdjustmentConfig) -> None:
        field_layout = {
            "send_card_names": {
                "label": "报牌名",
                "hint": "开启后发送“抽到的牌”列表，多张牌会逐行显示。",
                "order": 10,
            },
            "send_interpretation": {
                "label": "发送牌义解读",
                "hint": "开启后发送牌义解读；关闭后只发送牌面图片和已开启的其它输出。",
                "order": 11,
            },
            "ai_interpretation": {
                "label": "牌义解读 / AI 生成",
                "hint": "关闭时使用牌组 JSON 中的正逆位牌义文本。",
                "order": 12,
            },
            "send_preface": {
                "label": "发送准备台词",
                "hint": "关闭后不会发送准备台词，下方准备台词相关选项不生效。",
                "order": 20,
            },
            "ai_preface": {
                "label": "准备台词 / AI 生成",
                "hint": "关闭时使用固定准备台词模板。",
                "order": 21,
            },
            "contextual_preface": {
                "label": "准备台词 / 参照语境",
                "hint": "仅 AI 生成准备台词时生效，会参考触发语句。",
                "order": 22,
            },
            "send_extension_comment": {
                "label": "发送延伸评论",
                "hint": "关闭后不会发送延伸评论，下方延伸评论相关选项不生效。",
                "order": 40,
            },
            "ai_extension_comment": {
                "label": "延伸评论 / AI 生成",
                "hint": "关闭时使用固定延伸评论模板。",
                "order": 41,
            },
            "contextual_extension_comment": {
                "label": "延伸评论 / 参照语境",
                "hint": "仅 AI 生成延伸评论时生效，会结合触发语句和抽牌内容。",
                "order": 42,
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

    def _mark_memory_silent_text(self, stream_id: str, text: str) -> None:
        clean_stream_id = str(stream_id or "").strip()
        clean_text = self._normalize_request_text(text)
        if not clean_stream_id or not clean_text:
            return
        key = (clean_stream_id, clean_text)
        self._memory_silent_texts[key] = self._memory_silent_texts.get(key, 0) + 1

    def _consume_memory_silent_text(self, stream_id: str, text: str) -> bool:
        key = (str(stream_id or "").strip(), self._normalize_request_text(text))
        count = self._memory_silent_texts.get(key, 0)
        if count <= 0:
            return False
        if count == 1:
            self._memory_silent_texts.pop(key, None)
        else:
            self._memory_silent_texts[key] = count - 1
        return True

    @HookHandler(
        "send_service.before_send",
        name="tarots_memory_silent_sender",
        description="清空塔罗插件文字消息的 processed_plain_text，避免触发长期记忆人物事实写回",
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
        modified_message["processed_plain_text"] = ""
        return {"modified_kwargs": {"message": modified_message}}

    def _spawn_background_task(self, coro: Any, label: str, timeout: float = 120.0) -> asyncio.Task[Any]:
        async def _runner() -> None:
            try:
                await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                self.ctx.logger.warning("[%s] 后台任务超时 %.1fs，已取消", label, timeout)
            except Exception:
                self.ctx.logger.exception("[%s] 后台任务异常", label)

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

        self._spawn_background_task(
            self._execute_intercepted_tarots(message, stream_id, request_text),
            "tarots_intercept",
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

    @Action(
        "tarots",
        description=(
            "进行真实的塔罗牌占卜：抽取本地塔罗牌图片，发送牌名，并生成简短解读。"
            "用户明确要求占卜、塔罗、抽牌、算一卦、测一测时必须优先调用本动作，"
            "不要直接用 reply 编造牌面或占卜结果。"
        ),
        activation_type=ActivationType.ALWAYS,
        visibility="visible",
        action_parameters={
            "card_type": "抽牌范围：全部、大阿卡纳、小阿卡纳。用户没有明确要求时填全部。",
            "formation": "牌阵：单张、圣三角、时间之流、四要素、五牌阵、吉普赛十字、马蹄、六芒星。用户没有明确要求时填单张。",
            "target_user": "提出占卜请求的用户昵称。",
            "user_request": "用户触发占卜的完整原话或占卜问题，例如“帮我占卜一下我今年还能瘦吗”。必须填写，用于结合语境生成准备台词和延伸评论。",
        },
        action_require=[
            "当用户明确要求现在为其执行塔罗占卜、抽牌、算一卦、测一测、问牌时，必须调用本动作，不要直接 reply 生成占卜内容。",
            "调用本动作时必须把用户原始占卜请求填入 user_request，不要留空。",
            "用户只是询问塔罗牌知识、牌义、正逆位含义、牌阵说明、某张牌怎么解读时，不应调用本动作。",
            "例如“圣杯7 逆位是什么意思”“恋人正位代表什么”“塔罗有哪些牌阵”这类问题都不是占卜请求，不应调用本动作。",
            "本动作会自行发送牌面图片、牌名和简短解读，调用后不需要额外解释同一件事。",
            "如果用户要求其它类型的占卜或普通聊天，不应调用本动作。",
        ],
        associated_types=["image", "text"],
        parallel_action=False,
        timeout_ms=120000,
    )
    async def handle_tarots_action(
        self,
        stream_id: str = "",
        card_type: str = "全部",
        formation: str = "单张",
        target_user: str = "用户",
        user_request: str = "",
        text: str = "",
        message: dict | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        del kwargs
        if not self.config.components.enable_tarots:
            return False, "塔罗 Action 未启用"
        runtime = self._runtime_or_create()
        nickname = self._normalize_display_name(self._extract_message_user_nickname(message) or target_user)
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
        description="手动触发塔罗牌占卜，用法：/塔罗、/tarot 或 /tarots [全部|大阿卡纳|小阿卡纳] [牌阵]",
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
        for key in ("processed_plain_text", "plain_text", "text"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value
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
            return "".join(parts)
        return ""

    def _normalize_request_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _is_tarot_divination_request(self, text: str, mode: str = "平衡") -> bool:
        if not text:
            return False
        if TAROT_KNOWLEDGE_PATTERN.search(text) and not TAROT_REQUEST_PATTERN.search(text):
            return False

        normalized_mode = mode if mode in NATURAL_TRIGGER_MODES else "平衡"
        if normalized_mode == "严格":
            return bool(TAROT_REQUEST_PATTERN.search(text))
        if normalized_mode == "宽松":
            return bool(
                TAROT_REQUEST_PATTERN.search(text)
                or TAROT_TOPIC_PATTERN.search(text)
                or (LOOSE_REQUEST_PATTERN.search(text) and LOOSE_TOPIC_PATTERN.search(text))
            )
        return bool(TAROT_REQUEST_PATTERN.search(text) or TAROT_TOPIC_PATTERN.search(text))

    def _parse_natural_request_options(self, text: str) -> tuple[str, str]:
        card_type = "全部"
        for alias, mapped in CARD_TYPE_ALIASES.items():
            if alias and alias in text:
                card_type = mapped
                break

        formation = "单张"
        for alias, mapped in FORMATION_ALIASES.items():
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
        card_type = "全部"
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
