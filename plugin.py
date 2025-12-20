from typing import List, Tuple, Type, Any, Dict, Optional
import random
import asyncio
import json
import base64
import toml
import tomlkit
import traceback
from pathlib import Path
import os

# 导入新版插件系统
from src.plugin_system import BasePlugin, register_plugin, ComponentInfo, ActionActivationType
from src.plugin_system.base.config_types import ConfigField
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.apis import llm_api
from src.common.logger import get_logger

logger = get_logger("tarots")

class TarotsAction(BaseAction):
    """塔罗牌占卜动作 - 直接发送图片和简短解读"""
    
    action_name = "tarots"
    
    # 激活配置
    activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["抽一张塔罗牌", "抽张塔罗牌", "塔罗占卜", "塔罗牌", "占卜", "算一卦"]
    keyword_case_sensitive = False

    # 动作描述
    action_description = "执行塔罗牌占卜，立即发送牌面图片并进行简短解读"
    action_parameters = {
        "card_type": "塔罗牌的抽牌范围，必填，只能填一个参数，这里请根据用户的要求填'全部'或'大阿卡纳'或'小阿卡纳'，如果用户的要求并不明确，默认填'全部'",
        "formation": "塔罗牌的抽牌方式，必填，只能填一个参数，这里请根据用户的要求填'单张'或'圣三角'或'时间之流'或'四要素'或'五牌阵'或'吉普赛十字'或'马蹄'或'六芒星'，如果用户的要求并不明确，默认填'单张'",
        "target_user": "提出抽塔罗牌的用户名"
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 初始化基本路径
        self.base_dir = Path(__file__).parent.absolute()

        # 扫描并更新可用牌组
        self.config = self._load_config()
        self._update_available_card_sets()

        # 初始化路径
        self.using_cards = self.config["cards"].get("using_cards", 'bilibili')
        if not self.using_cards:
            self.cache_dir = self.base_dir / "tarots_cache" / "default"
        else:
            self.cache_dir = self.base_dir / "tarots_cache" / self.using_cards
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 加载卡牌数据
        self.card_map: Dict = {}
        self.formation_map: Dict = {}
        self._load_resources()

    def _load_resources(self):
        """同步加载资源文件"""
        try:
            if not self.using_cards:
                logger.info("没有加载到任何可用牌组")
                return
            
            # 加载卡牌数据
            cards_json_path = self.base_dir / f"tarot_jsons/{self.using_cards}/tarots.json"
            if cards_json_path.exists():
                with open(cards_json_path, encoding="utf-8") as f:
                    self.card_map = json.load(f)
            else:
                logger.error(f"卡牌数据文件不存在: {cards_json_path}")
                return
            
            # 加载牌阵配置
            formation_json_path = self.base_dir / "tarot_jsons/formation.json"
            if formation_json_path.exists():
                with open(formation_json_path, encoding="utf-8") as f:
                    self.formation_map = json.load(f)
            else:
                logger.error(f"牌阵配置文件不存在: {formation_json_path}")
                return
                
            logger.info(f"已加载{self.card_map['_meta']['total_cards']}张卡牌和{len(self.formation_map)}种抽牌方式")
        except Exception as e:
            logger.error(f"资源加载失败: {str(e)}")
            raise

    async def execute(self) -> Tuple[bool, str]:
        """执行塔罗牌占卜 - 直接发送图片和简短解读"""
        try:
            if not self.card_map:
                await self.send_text("❌ 没有可用的牌组，无法进行占卜")
                return False, "没有牌组"
            
            logger.info("开始执行塔罗占卜")
            
            # 解析参数
            request_type = self.action_data.get("card_type", "全部")
            formation_name = self.action_data.get("formation", "单张")
            target_user = self.action_data.get("target_user", "用户")
            
            # 参数映射（支持简写）
            request_type = self._map_card_type(request_type)
            formation_name = self._map_formation(formation_name)
            
            logger.info(f"占卜参数: card_type={request_type}, formation={formation_name}, target_user={target_user}")
            
            # 参数校验
            if request_type not in ["全部", "大阿卡纳", "小阿卡纳"]:
                await self.send_text("❌ 不存在的抽牌范围")
                return False, "参数错误"
                
            if formation_name not in self.formation_map:
                await self.send_text("❌ 不存在的抽牌方法")
                return False, "参数错误"
    
            # 获取牌阵配置
            formation = self.formation_map[formation_name]
            cards_num = formation["cards_num"]
            is_cut = formation["is_cut"]
            represent_list = formation["represent"]
    
            # 获取有效卡牌范围
            valid_ids = self._get_card_range(request_type)
            if not valid_ids:
                await self.send_text("❌ 当前牌组配置错误")
                return False, "参数错误"
    
            # 抽牌逻辑
            selected_ids = random.sample(valid_ids, cards_num)
            if is_cut:
                selected_cards = [
                    (cid, random.random() < 0.5)  # 切牌时50%概率逆位
                    for cid in selected_ids
                ]
            else:
                selected_cards = [
                    (cid, False)  # 不切牌时全部正位
                    for cid in selected_ids
                ]
    
            logger.info(f"抽中卡牌: {selected_cards}")
            
            # 1. 立即发送每张牌面图片
            card_details = []
            sent_images = []
            
            for idx, (card_id, is_reverse) in enumerate(selected_cards):
                card_data = self.card_map.get(card_id, {})
                if not card_data:
                    logger.warning(f"卡牌ID不存在: {card_id}")
                    continue
                    
                # 发送图片
                image_sent = await self._send_card_image(card_id, is_reverse)
                if image_sent:
                    sent_images.append(card_id)
                    await asyncio.sleep(0.5)  # 防止消息频率限制
                
                # 收集卡牌信息用于解读
                card_info = card_data.get("info", {})
                pos_name = self._get_position_name(represent_list, idx, formation_name)
                pos_meaning = self._get_position_meaning(represent_list, idx, formation_name)
                
                card_details.append({
                    'position': pos_name,
                    'name': card_data.get('name', '未知'),
                    'is_reverse': is_reverse,
                    'description': card_info.get('reverseDescription' if is_reverse else 'description', '暂无描述'),
                    'position_meaning': pos_meaning
                })

            if not sent_images:
                await self.send_text("❌ 卡牌图片发送失败，无法进行占卜")
                return False, "图片发送失败"

            # 2. 获取聊天上下文 - 从action_reasoning中提取
            chat_context = self._get_chat_context_from_reasoning()
            logger.info(f"聊天上下文: {chat_context}")
            
            # 3. 生成并发送简短文字解读
            await asyncio.sleep(1)  # 给用户一点时间看图片
            
            try:
                short_interpretation = await self._generate_short_interpretation(
                    card_details, formation_name, target_user, chat_context
                )
                # 清理文本，移除空行和多余换行
                cleaned_interpretation = self._clean_text(short_interpretation)
                await self.send_text(cleaned_interpretation)
                    
            except Exception as e:
                logger.error(f"解读生成失败: {e}")
                # 发送最简解读
                card_names = [card['name'] for card in card_details]
                basic_text = f"✨ 为{target_user}抽到了：{'、'.join(card_names)}～愿塔罗牌给你带来好运！"
                await self.send_text(basic_text)

            logger.info("塔罗牌占卜执行成功")
            return True, f"已为{target_user}抽取塔罗牌"
            
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"执行失败: {error_msg}")
            await self.send_text(f"❌ 占卜失败: {str(e)}")
            return False, "执行错误"

    def _get_chat_context_from_reasoning(self) -> Dict[str, Any]:
        """从action_reasoning中提取上下文信息"""
        try:
            context_info = {
                "has_context": False,
                "topic": "",
                "intent": "",
                "related_messages": []
            }
            
            # 获取action_reasoning
            if not hasattr(self, 'action_reasoning'):
                logger.warning("没有action_reasoning属性")
                return context_info
            
            reasoning_text = getattr(self, 'action_reasoning', '')
            if not reasoning_text or not isinstance(reasoning_text, str):
                logger.warning(f"action_reasoning无效: {reasoning_text}")
                return context_info
            
            logger.info(f"action_reasoning: {reasoning_text}")
            
            # 从reasoning中提取关键词
            reasoning_lower = reasoning_text.lower()
            
            # 关键词映射 - 更全面的关键词
            fortune_keywords = {
                "财运": ["财运", "金钱", "投资", "赚钱", "财富", "收入", "经济", "财务", "财政", "钱", "发财", "富贵", "富裕"],
                "爱情": ["爱情", "桃花", "感情", "恋爱", "喜欢", "爱人", "姻缘", "伴侣", "婚姻", "心动", "脱单", "喜欢的人", "恋爱运", "感情运"],
                "事业": ["事业", "工作", "职业", "职场", "升职", "跳槽", "项目", "事业运", "工作运", "职业发展", "工作发展", "事业发展", "事业", "工作", "职场运"],
                "学业": ["学业", "考试", "学习", "成绩", "考试运", "学习运", "功课", "读书", "考试", "复习", "考试成绩", "学习考试", "学业运", "学习", "考试"],
                "健康": ["健康", "身体", "生病", "熬夜", "锻炼", "养生", "健康运", "身体", "健康", "养生", "身体状况", "健康", "身体运"],
                "感情": ["感情", "情感", "关系", "相处", "分手", "复合", "恋爱", "情感", "感情关系", "感情运", "情感运"]
            }
            
            # 检查reasoning中是否包含关键词
            found_intent = ""
            found_keyword = ""
            
            for intent, keywords in fortune_keywords.items():
                for keyword in keywords:
                    if keyword in reasoning_lower:
                        found_intent = intent
                        found_keyword = keyword
                        logger.info(f"从action_reasoning检测到意图: {found_intent}, 关键词: {found_keyword}")
                        break
                if found_intent:
                    break
            
            if found_intent:
                context_info["has_context"] = True
                context_info["intent"] = found_intent
                context_info["topic"] = f"{found_intent}相关"
                context_info["related_messages"].append(f"用户关心：{found_intent}")
            else:
                # 如果没有明确意图，检查是否提到占卜
                if "占卜" in reasoning_lower or "运势" in reasoning_lower or "运气" in reasoning_lower:
                    context_info["has_context"] = True
                    context_info["topic"] = "运势占卜"
                    logger.info("检测到通用占卜请求")
                else:
                    logger.info("未检测到特定意图")
            
            return context_info
            
        except Exception as e:
            logger.warning(f"从action_reasoning提取上下文失败: {e}")
            return {"has_context": False, "topic": "", "intent": "", "related_messages": []}

    def _clean_text(self, text: str) -> str:
        """清理文本，移除空行和多余换行"""
        if not text:
            return ""
        
        # 分割成行
        lines = text.split('\n')
        # 过滤掉空行和只有空格的行
        cleaned_lines = []
        for line in lines:
            stripped_line = line.strip()
            if stripped_line:  # 如果不是空行
                cleaned_lines.append(stripped_line)
        
        # 重新组合成单行文本，用空格分隔
        return ' '.join(cleaned_lines)

    async def _generate_short_interpretation(self, card_details: List[Dict], formation_name: str, user_nickname: str, chat_context: Dict) -> str:
        """生成简短自然的解读（结合上下文）"""
        try:
            # 使用AI生成简短解读
            prompt = self._build_ultra_short_prompt(card_details, formation_name, user_nickname, chat_context)
            
            models = llm_api.get_available_models()
            chat_model_config = models.get("replyer")

            success, thinking_result, _, _ = await llm_api.generate_with_model(
                prompt, model_config=chat_model_config, request_type="tarots_interpretation"
            )

            if success and thinking_result:
                # 清理回复，确保简短且无空行
                clean_result = self._clean_text(thinking_result.strip())
                # 严格控制长度在80字以内
                if len(clean_result) > 80:
                    clean_result = clean_result[:80]
                logger.info(f"AI生成解读: {clean_result}")
                return clean_result
            else:
                # 如果AI回复失败，使用备用简短解读
                fallback_result = self._generate_fallback_ultra_short_interpretation(card_details, formation_name, user_nickname, chat_context)
                logger.info(f"使用备用解读: {fallback_result}")
                return fallback_result
                
        except Exception as e:
            logger.error(f"AI解读生成错误: {e}")
            fallback_result = self._generate_fallback_ultra_short_interpretation(card_details, formation_name, user_nickname, chat_context)
            logger.info(f"出错后使用备用解读: {fallback_result}")
            return fallback_result

    def _build_ultra_short_prompt(self, card_details: List[Dict], formation_name: str, user_nickname: str, chat_context: Dict) -> str:
        """构建超简短解读提示词（控制在80字内）"""
        # 构建卡牌信息
        cards_info = []
        for card in card_details:
            status = "逆位" if card['is_reverse'] else "正位"
            cards_info.append(f"{card['name']}（{status}）")
        
        cards_str = "、".join(cards_info)

        # 基础提示词
        prompt_parts = []
        prompt_parts.append(f"请为{user_nickname}的塔罗牌做超简短解读（最多80字）。")
        prompt_parts.append(f"抽到的牌：{cards_str}")
        prompt_parts.append(f"牌阵：{formation_name}")

        # 添加上下文信息（如果有的话）
        if chat_context.get("has_context", False):
            if chat_context.get("intent"):
                intent = chat_context["intent"]
                prompt_parts.append(f"用户想了解{intent}运势，请将解读重点放在{intent}方面，给出相关的建议。")
                logger.info(f"提示词中包含意图: {intent}")
            else:
                prompt_parts.append(f"用户进行运势占卜，请给出温暖鼓励的解读。")
                logger.info(f"提示词中包含通用占卜意图")
        else:
            logger.info("提示词中无特定意图")
        
        prompt_parts.append("要求：用1-2句话解读，像朋友聊天一样自然温暖。不要用专业术语，不要分段，不要空行。")
        prompt_parts.append("示例：'牌面显示事业运不错～工作上有新机会，主动把握会有好进展哦！'")
        prompt_parts.append("你的解读：")

        full_prompt = "\n".join(prompt_parts)
        logger.info(f"生成的提示词: {full_prompt[:200]}...")
        return full_prompt

    def _generate_fallback_ultra_short_interpretation(self, card_details: List[Dict], formation_name: str, user_nickname: str, chat_context: Dict) -> str:
        """生成备用超简短解读"""
        card_names = []
        reverse_count = 0
        
        for card in card_details:
            status = "逆位" if card['is_reverse'] else "正位"
            card_names.append(f"{card['name']}（{status}）")
            if card['is_reverse']:
                reverse_count += 1
    
        card_list = "、".join(card_names)
        
        logger.info(f"生成备用解读: intent={chat_context.get('intent', '无')}, reverse_count={reverse_count}")
        
        # 如果有上下文意图，添加相关解读
        if chat_context.get("has_context", False) and chat_context.get("intent"):
            intent = chat_context["intent"]
            
            if intent == "爱情":
                interpretations = [
                    f"💖 {user_nickname}抽到{card_list}～感情方面需要多用心经营哦！",
                    f"❤️ {card_list}为你揭示感情～最近多关注彼此感受会有惊喜！",
                    f"🌹 {user_nickname}的感情牌是{card_list}～用心沟通感情会更甜蜜！"
                ]
            elif intent == "财运":
                interpretations = [
                    f"💰 {user_nickname}抽到{card_list}～财运方面需要谨慎决策哦！",
                    f"💵 {card_list}为你揭示财运～稳扎稳打会有好收获！",
                    f"📈 {user_nickname}的财运牌是{card_list}～理性投资会有回报！"
                ]
            elif intent == "事业":
                interpretations = [
                    f"💼 {user_nickname}抽到{card_list}～事业方面需要多些耐心！",
                    f"📋 {card_list}为你揭示事业～踏实工作会有进步！",
                    f"🚀 {user_nickname}的事业牌是{card_list}～专注目标会有突破！"
                ]
            elif intent == "学业":
                interpretations = [
                    f"📚 {user_nickname}抽到{card_list}～学习方面需要更多专注！",
                    f"✏️ {card_list}为你揭示学业～认真复习会有好成绩！",
                    f"🎓 {user_nickname}的学业牌是{card_list}～坚持努力会有收获！"
                ]
            else:
                # 其他意图使用通用解读
                interpretations = self._get_general_interpretations(card_list, user_nickname, reverse_count, len(card_details))
        else:
            # 没有上下文意图，使用通用解读
            interpretations = self._get_general_interpretations(card_list, user_nickname, reverse_count, len(card_details))
        
        return random.choice(interpretations)

    def _get_general_interpretations(self, card_list: str, user_nickname: str, reverse_count: int, total_cards: int) -> List[str]:
        """获取通用解读"""
        if reverse_count == total_cards:
            # 全是逆位
            return [
                f"🌙 {user_nickname}抽到{card_list}～需要放慢脚步调整一下呢！",
                f"🌀 牌面是{card_list}～给自己多点耐心调整状态哦！",
                f"💫 {card_list}显示需要稍作休整～放松心情会有新发现！"
            ]
        elif reverse_count > 0:
            # 有逆位牌
            return [
                f"✨ {user_nickname}抽到{card_list}～牌面有些小波动但问题不大！",
                f"🌟 {card_list}显示需要微调～保持平常心就好！",
                f"🔮 塔罗牌{card_list}～能量有起有伏是正常的！"
            ]
        else:
            # 全是正位
            return [
                f"💖 {user_nickname}抽到{card_list}～牌面能量很棒继续保持！",
                f"⭐ {card_list}都是正位呢～最近运势不错哦！",
                f"🌞 塔罗牌{card_list}～能量很正向放心前进吧！"
            ]

    def _map_card_type(self, card_type: str) -> str:
        """映射卡牌类型参数"""
        mapping = {
            "全": "全部", "全部": "全部",
            "大": "大阿卡纳", "大阿": "大阿卡纳", "大阿卡纳": "大阿卡纳",
            "小": "小阿卡纳", "小阿": "小阿卡纳", "小阿卡纳": "小阿卡纳"
        }
        return mapping.get(card_type, card_type)

    def _map_formation(self, formation: str) -> str:
        """映射牌阵参数"""
        mapping = {
            "单": "单张", "单张": "单张",
            "圣": "圣三角", "圣三角": "圣三角",
            "时": "时间之流", "时间": "时间之流", "时间之流": "时间之流",
            "四": "四要素", "四要素": "四要素",
            "五": "五牌阵", "五牌": "五牌阵", "五牌阵": "五牌阵",
            "吉": "吉普赛十字", "吉普赛": "吉普赛十字", "吉普赛十字": "吉普赛十字",
            "马": "马蹄", "马蹄": "马蹄",
            "六": "六芒星", "六芒": "六芒星", "六芒星": "六芒星"
        }
        return mapping.get(formation, formation)

    async def _send_card_image(self, card_id: str, is_reverse: bool) -> bool:
        """发送卡牌图片"""
        try:
            card_data = self.card_map.get(card_id, {})
            if not card_data:
                logger.error(f"卡牌ID不存在: {card_id}")
                return False
                
            card_name = card_data.get("name", "")
            if not card_name:
                logger.error(f"卡牌名称不存在: {card_id}")
                return False
            
            # 构建本地图片路径
            image_filename = self._get_local_image_filename(card_name, is_reverse)
            image_path = self.base_dir / f"tarot_jsons/{self.using_cards}" / image_filename
            
            if not image_path.exists():
                logger.error(f"本地图片文件不存在: {image_path}")
                return False
                
            # 读取图片文件并转换为base64
            with open(image_path, "rb") as f:
                img_data = f.read()
            
            # 将图片数据转换为base64字符串
            img_base64 = base64.b64encode(img_data).decode('utf-8')
            
            # 发送图片
            await self.send_image(img_base64)
            
            logger.info(f"成功发送本地图片: {image_filename}")
            return True

        except Exception as e:
            logger.error(f"发送本地图片失败: {str(e)}")
            return False

    def _get_local_image_filename(self, card_name: str, is_reverse: bool) -> str:
        """根据卡牌名称和位置构建本地图片文件名"""
        # 处理卡牌名称中的特殊字符和空格
        cleaned_name = card_name.replace("ACE", "王牌").replace("2", "二").replace("3", "三").replace("4", "四").replace("5", "五").replace("6", "六").replace("7", "七").replace("8", "八").replace("9", "九").replace("10", "十")
        
        # 构建文件名
        position = "逆位" if is_reverse else "正位"
        filename = f"{cleaned_name}{position}.jpg"
        
        return filename

    def _get_card_range(self, card_type: str) -> list:
        """获取卡牌范围"""
        if card_type == "大阿卡纳":
            return [str(i) for i in range(22)]
        elif card_type == "小阿卡纳":
            return [str(i) for i in range(22, 78)]
        return [str(i) for i in range(78)]

    def _get_position_name(self, represent_list: List, idx: int, formation_name: str) -> str:
        """安全获取位置名称"""
        try:
            if (isinstance(represent_list, list) and len(represent_list) > 0 and 
                isinstance(represent_list[0], list) and idx < len(represent_list[0])):
                return represent_list[0][idx]
        except (IndexError, TypeError):
            pass
        return f"位置{idx+1}"

    def _get_position_meaning(self, represent_list: List, idx: int, formation_name: str) -> str:
        """安全获取位置含义"""
        try:
            if (isinstance(represent_list, list) and len(represent_list) > 1 and 
                isinstance(represent_list[1], list) and idx < len(represent_list[1])):
                return represent_list[1][idx]
        except (IndexError, TypeError):
            pass
        
        # 根据牌阵类型提供默认含义
        default_meanings = {
            "单张": "当前状况",
            "圣三角": ["过去", "现在", "未来"],
            "时间之流": ["过去", "现在", "未来"],
            "四要素": ["行动", "情感", "思想", "物质"],
            "五牌阵": ["现状", "挑战", "选择", "环境", "结果"],
            "吉普赛十字": ["现状", "障碍", "目标", "过去", "未来"],
            "马蹄": ["过去", "现在", "隐藏", "环境", "期望", "结果"],
            "六芒星": ["过去", "现在", "未来", "原因", "环境", "结果"]
        }
        
        if formation_name in default_meanings:
            meanings = default_meanings[formation_name]
            if isinstance(meanings, list) and idx < len(meanings):
                return meanings[idx]
            elif isinstance(meanings, str):
                return meanings
        
        return "未知"

    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.toml")
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = toml.load(f)
            
            config = {
                "permissions": {
                    "admin_users": config_data.get("permissions", {}).get("admin_users", [])
                },
                "proxy": {
                    "enable_proxy": config_data.get("proxy", {}).get("enable_proxy", False),
                    "proxy_url": config_data.get("proxy", {}).get("proxy_url", "")
                },
                "cards": {
                    "using_cards": config_data.get("cards", {}).get("using_cards", 'bilibili'),
                    "use_cards": config_data.get("cards", {}).get("use_cards", ['bilibili','east'])
                },
                "adjustment": {
                    "enable_original_text": False,
                    "ai_interpretation": True
                }
            }
            return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            # 返回默认配置
            return {
                "permissions": {"admin_users": []},
                "proxy": {"enable_proxy": False, "proxy_url": ""},
                "cards": {"using_cards": "bilibili", "use_cards": ["bilibili", "east"]},
                "adjustment": {
                    "enable_original_text": False,
                    "ai_interpretation": True
                }
            }
        
    def get_available_card_type(self, user_requested_type):
        """获取当前牌组支持的卡牌类型"""
        supported_type = self.card_map.get("_meta", {}).get("card_types", "")
        if supported_type == '全部' or user_requested_type == supported_type:
            return user_requested_type
        else:
            return supported_type
        
    def _update_available_card_sets(self):
        """更新配置文件中的可用牌组列表"""
        try:
            current_using = self.config["cards"].get("using_cards", "")
            available_sets = self._scan_available_card_sets()

            if not current_using or current_using not in available_sets:
                new_using = available_sets[0] if available_sets else ""
                if new_using:
                    logger.warning(f"自动切换牌组至: {new_using}")
                    self.set_card(new_using)

            if available_sets:
                self.set_cards(available_sets)
                logger.info(f"可用牌组: {available_sets}")
            else:
                logger.error("未发现任何可用牌组")
                self.set_card("")
                self.set_cards([])
                
            self.config = self._load_config()
        except Exception as e:
            logger.error(f"更新牌组配置失败: {e}")
        
    def _scan_available_card_sets(self) -> List[str]:
        """扫描可用牌组"""
        try:
            tarot_jsons_dir = self.base_dir / "tarot_jsons"
            available_sets = []
            
            if not tarot_jsons_dir.exists():
                logger.warning(f"tarot_jsons目录不存在: {tarot_jsons_dir}")
                return []
            
            for item in tarot_jsons_dir.iterdir():
                if item.is_dir():
                    tarots_json_path = item / "tarots.json"
                    if tarots_json_path.exists():
                        available_sets.append(item.name)
                        logger.info(f"发现牌组: {item.name}")
            
            return available_sets
        except Exception as e:
            logger.error(f"扫描牌组失败: {e}")
            return []
        
    def set_cards(self, cards: List):
        """更新可用牌组配置"""
        try:
            config_path = self.base_dir / "config.toml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = tomlkit.load(f)
                config_data["cards"]["use_cards"] = tomlkit.array(cards)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                tomlkit.dump(config_data, f)
                
        except Exception as e:
            logger.error(f"更新牌组配置失败: {e}")

    def set_card(self, cards: str):
        """设置当前使用牌组"""
        try:
            config_path = self.base_dir / "config.toml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = tomlkit.load(f)
                config_data["cards"]["using_cards"] = cards
            
            with open(config_path, 'w', encoding='utf-8') as f:
                tomlkit.dump(config_data, f)
                
        except Exception as e:
            logger.error(f"更新使用牌组失败: {e}")

@register_plugin
class TarotsPlugin(BasePlugin):
    """塔罗牌插件 - 支持多种牌阵和卡牌类型的占卜功能"""

    plugin_name = "tarots_plugin"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["Pillow", "aiohttp", "tomlkit"]

    plugin_description = "塔罗牌占卜插件，支持多种牌阵和卡牌类型，提供简短自然解读"
    plugin_version = "2.2.1"
    plugin_author = "升级版 - 简短解读"

    config_section_descriptions = {
        "plugin": "插件基本配置",
        "components": "组件启用控制",
        "proxy": "代理设置",
        "cards": "牌组配置",
        "adjustment": "功能调整",
        "permissions": "权限管理",
    }

    config_schema = {
        "plugin": {
            "config_version": ConfigField(type=str, default="2.2.1", description="配置文件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        "components": {
            "enable_tarots": ConfigField(type=bool, default=True, description="启用塔罗牌占卜功能"),
        },
        "proxy": {
            "enable_proxy": ConfigField(type=bool, default=False, description="是否启用代理"),
            "proxy_url": ConfigField(type=str, default="", description="代理服务器地址")
        },
        "cards": {
            "using_cards": ConfigField(type=str, default='bilibili', description="当前使用牌组"),
            "use_cards": ConfigField(type=list, default=['bilibili','east'], description="可用牌组列表")
        },
        "adjustment": {
            "enable_original_text": ConfigField(type=bool, default=False, description="启用原始文本显示"),
            "ai_interpretation": ConfigField(type=bool, default=True, description="启用AI智能解读")
        },
        "permissions": {
            "admin_users": ConfigField(type=list, default=["123456789"], description="管理员用户ID列表")
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件"""
        components = []

        if self.get_config("components.enable_tarots", True):
            components.append((TarotsAction.get_action_info(), TarotsAction))

        return components