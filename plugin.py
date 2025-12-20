from typing import List, Tuple, Type, Any, Dict, Optional
import random
import asyncio
import json
import base64
import toml
import traceback
from pathlib import Path
import os

# 导入插件系统
from src.plugin_system import BasePlugin, register_plugin, ComponentInfo
from src.plugin_system import BaseAction, ActionActivationType
from src.plugin_system import ConfigField
from src.plugin_system.apis import llm_api
from src.common.logger import get_logger

logger = get_logger("tarots")

class TarotsAction(BaseAction):
    """塔罗牌占卜动作 - 按原始版本逻辑重构"""
    
    # === Action配置 ===
    action_name = "tarots_draw_action"
    
    # 激活配置
    activation_type = ActionActivationType.KEYWORD
    activation_keywords = ["塔罗牌", "抽塔罗", "占卜", "算卦", "抽张塔罗牌", "抽塔罗牌"]
    keyword_case_sensitive = False
    activation_require_all = False

    # 动作描述
    action_description = "为用户抽取塔罗牌并进行LLM解读"
    action_parameters = {
        "user_query": "用户的原始问题和请求"
    }
    action_require = ["用户要求抽取塔罗牌时", "用户要进行占卜时", "用户想算一卦时"]
    associated_types = ["text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_dir = Path(__file__).parent.absolute()
        self.using_cards = self._load_card_setting()
        self.card_map = {}
        self.formation_map = {}
        
        # 立即加载资源
        self._load_resources()
        logger.info(f"塔罗牌Action初始化完成，使用牌组: {self.using_cards}")

    def _load_card_setting(self) -> str:
        """加载牌组设置"""
        try:
            config_path = self.base_dir / "config.toml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = toml.load(f)
                return config.get("cards", {}).get("using_cards", "bilibili")
        except Exception as e:
            logger.error(f"加载牌组设置失败: {e}")
        return "bilibili"

    def _load_resources(self):
        """加载资源文件"""
        try:
            # 加载卡牌数据
            cards_path = self.base_dir / f"tarot_jsons/{self.using_cards}/tarots.json"
            if cards_path.exists():
                with open(cards_path, encoding="utf-8") as f:
                    self.card_map = json.load(f)
                logger.info(f"加载卡牌数据: {len(self.card_map)}张")
            
            # 加载牌阵配置
            formation_path = self.base_dir / "tarot_jsons/formation.json"
            if formation_path.exists():
                with open(formation_path, encoding="utf-8") as f:
                    self.formation_map = json.load(f)
                logger.info(f"加载牌阵配置: {len(self.formation_map)}种")
                
        except Exception as e:
            logger.error(f"资源加载失败: {e}")

    async def execute(self) -> Tuple[bool, str]:
        """执行塔罗牌占卜 - 按原始版本逻辑"""
        try:
            logger.info("=== 塔罗牌Action开始执行 ===")
            
            # 1. 获取用户原始消息
            user_message = await self._get_user_message()
            logger.info(f"获取到用户消息: {user_message}")
            
            if not user_message:
                await self.send_text("❌ 无法获取您的消息")
                return False, "无用户消息"
            
            # 2. 检查数据是否加载
            if not self.card_map or not self.formation_map:
                await self.send_text("❌ 塔罗牌数据加载失败，请检查配置")
                return False, "数据未加载"
            
            # 3. 按原始版本逻辑：先检测牌阵，再检测范围，最后提取查询
            # 先检测牌阵关键词（原始版本逻辑）
            formation_name = self._detect_formation(user_message)
            
            # 再检测范围关键词（原始版本逻辑）
            card_type = self._detect_card_type(user_message)
            
            # 最后提取用户查询
            user_query = self._extract_user_query(user_message)
            
            logger.info(f"原始版本逻辑解析: formation={formation_name}, card_type={card_type}, query={user_query}")
            
            # 4. 参数映射和校验
            card_type = self._map_card_type(card_type)
            formation_name = self._map_formation(formation_name)
            
            # 参数校验
            if card_type not in ["全部", "大阿卡纳", "小阿卡纳"]:
                await self.send_text("❌ 不支持的抽牌范围")
                return False, "参数错误"
                
            if formation_name not in self.formation_map:
                await self.send_text("❌ 不支持的抽牌方法")
                return False, "参数错误"
            
            # 5. 获取牌阵配置
            formation = self.formation_map[formation_name]
            cards_num = formation["cards_num"]
            is_cut = formation["is_cut"]
            represent_list = formation["represent"]
            
            logger.info(f"牌阵配置: {formation_name}, 需要{cards_num}张牌")
    
            # 6. 获取有效卡牌范围并抽牌
            valid_ids = self._get_card_range(card_type)
            if not valid_ids:
                await self.send_text("❌ 当前牌组配置错误")
                return False, "参数错误"
            
            # 确保有足够的卡牌
            if len(valid_ids) < cards_num:
                await self.send_text(f"❌ 可用卡牌不足，需要{cards_num}张但只有{len(valid_ids)}张")
                return False, "卡牌不足"
            
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
            
            # 7. 发送每张牌面图片并收集卡牌信息
            card_details = []
            for idx, (card_id, is_reverse) in enumerate(selected_cards):
                card_data = self.card_map.get(card_id, {})
                if not card_data:
                    logger.warning(f"卡牌ID不存在: {card_id}")
                    continue
                    
                # 发送图片
                image_sent = await self._send_card_image(card_id, is_reverse)
                if image_sent:
                    await asyncio.sleep(0.5)  # 防止消息频率限制
                
                # 收集卡牌信息用于解读
                card_info = card_data.get("info", {})
                pos_name = self._get_position_name(represent_list, idx, formation_name)
                pos_meaning = self._get_position_meaning(represent_list, idx, formation_name)
                
                card_details.append({
                    'position': pos_name,
                    'position_meaning': pos_meaning,
                    'name': card_data.get('name', '未知'),
                    'is_reverse': is_reverse,
                    'description': card_info.get('reverseDescription' if is_reverse else 'description', '暂无描述'),
                })
            
            if not card_details:
                await self.send_text("❌ 卡牌图片发送失败，无法进行占卜")
                return False, "图片发送失败"
            
            # 8. 生成LLM解读（等待用户看完图片）
            await asyncio.sleep(1)
            
            llm_interpretation = await self._generate_llm_interpretation(
                card_details, formation_name, card_type, user_query, user_message
            )
            
            await self.send_text(llm_interpretation)
            
            logger.info("=== 塔罗牌Action执行成功 ===")
            return True, "塔罗占卜完成"
            
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"执行失败: {error_msg}")
            await self.send_text("❌ 占卜过程出现错误，请稍后再试")
            return False, f"执行错误: {str(e)}"

    def _detect_formation(self, user_message: str) -> str:
        """按原始版本逻辑检测牌阵类型"""
        if not user_message:
            return "单张"  # 默认单张
        
        user_message_lower = user_message.lower()
        
        # 原始版本支持的牌阵关键词
        formation_keywords = {
            # 关键词 -> 牌阵名称
            "圣三角": "圣三角",
            "三角": "圣三角",
            "时间之流": "时间之流",
            "时间流": "时间之流",
            "时间": "时间之流",
            "四要素": "四要素",
            "四张": "四要素",
            "五牌阵": "五牌阵",
            "五张": "五牌阵",
            "五牌": "五牌阵",
            "吉普赛十字": "吉普赛十字",
            "吉普赛": "吉普赛十字",
            "十字": "吉普赛十字",
            "马蹄": "马蹄",
            "六芒星": "六芒星",
            "六芒": "六芒星",
            "六张": "六芒星",
        }
        
        # 检查用户消息中是否包含牌阵关键词
        for keyword, formation in formation_keywords.items():
            if keyword in user_message_lower:
                logger.info(f"检测到牌阵关键词: '{keyword}' -> {formation}")
                return formation
        
        # 如果没有检测到任何牌阵关键词，则使用默认单张（原始版本逻辑）
        logger.info("未检测到牌阵关键词，使用默认单张牌阵")
        return "单张"

    def _detect_card_type(self, user_message: str) -> str:
        """按原始版本逻辑检测卡牌范围"""
        if not user_message:
            return "全部"  # 默认全部
        
        user_message_lower = user_message.lower()
        
        # 原始版本支持的范围关键词
        card_type_keywords = {
            # 关键词 -> 范围类型
            "大阿卡纳": "大阿卡纳",
            "大阿": "大阿卡纳",
            "大牌": "大阿卡纳",
            "小阿卡纳": "小阿卡纳",
            "小阿": "小阿卡纳",
            "小牌": "小阿卡纳",
            "全部": "全部",
            "所有": "全部",
            "全牌": "全部",
        }
        
        # 检查用户消息中是否包含范围关键词
        for keyword, card_type in card_type_keywords.items():
            if keyword in user_message_lower:
                logger.info(f"检测到范围关键词: '{keyword}' -> {card_type}")
                return card_type
        
        # 如果没有检测到任何范围关键词，则使用默认全部（原始版本逻辑）
        logger.info("未检测到范围关键词，使用默认全部卡牌")
        return "全部"

    def _extract_user_query(self, user_message: str) -> str:
        """提取用户查询内容，移除关键词（按原始版本逻辑）"""
        if not user_message:
            return "运势"
        
        # 原始版本中需要移除的关键词（包括牌阵和范围关键词）
        keywords_to_remove = self.activation_keywords + [
            "抽张", "抽", "牌", "看看", "怎么样", "如何",
            # 牌阵关键词
            "圣三角", "三角", "时间之流", "时间流", "时间",
            "四要素", "四张", "五牌阵", "五张", "五牌",
            "吉普赛十字", "吉普赛", "十字", "马蹄", "六芒星", "六芒", "六张",
            # 范围关键词
            "大阿卡纳", "大阿", "大牌", "小阿卡纳", "小阿", "小牌", "全部", "所有", "全牌"
        ]
        
        query = user_message
        for kw in keywords_to_remove:
            if kw in query:
                query = query.replace(kw, "")
        
        # 清理多余空格
        query = ' '.join(query.split()).strip()
        
        # 如果清理后为空，检查主题
        if not query:
            themes = {
                "爱情": ["爱情", "恋爱", "感情", "姻缘", "桃花"],
                "事业": ["事业", "工作", "职业", "职场", "升职"],
                "财运": ["财运", "金钱", "财富", "投资", "赚钱"],
                "学习": ["学习", "考试", "学业", "读书", "成绩"],
                "健康": ["健康", "身体", "生病", "医疗"],
            }
            
            for theme, keywords in themes.items():
                for kw in keywords:
                    if kw in user_message:
                        return f"{theme}运势"
            
            return "近期运势"
        
        return query

    def _map_card_type(self, card_type: str) -> str:
        """映射卡牌类型参数"""
        mapping = {
            "全": "全部", "全部": "全部", "所有": "全部",
            "大": "大阿卡纳", "大阿": "大阿卡纳", "大阿卡纳": "大阿卡纳", "大牌": "大阿卡纳",
            "小": "小阿卡纳", "小阿": "小阿卡纳", "小阿卡纳": "小阿卡纳", "小牌": "小阿卡纳"
        }
        return mapping.get(card_type, card_type)

    def _map_formation(self, formation: str) -> str:
        """映射牌阵参数"""
        mapping = {
            "单": "单张", "单张": "单张", "一张": "单张",
            "圣": "圣三角", "圣三角": "圣三角", "三角": "圣三角",
            "时": "时间之流", "时间": "时间之流", "时间之流": "时间之流", "时间流": "时间之流",
            "四": "四要素", "四要素": "四要素", "四张": "四要素",
            "五": "五牌阵", "五牌": "五牌阵", "五牌阵": "五牌阵", "五张": "五牌阵",
            "吉": "吉普赛十字", "吉普赛": "吉普赛十字", "吉普赛十字": "吉普赛十字", "十字": "吉普赛十字",
            "马": "马蹄", "马蹄": "马蹄",
            "六": "六芒星", "六芒": "六芒星", "六芒星": "六芒星", "六张": "六芒星"
        }
        return mapping.get(formation, formation)

    async def _get_user_message(self) -> str:
        """获取用户原始消息"""
        try:
            # 方法1: 从message对象获取
            if hasattr(self, 'message') and self.message:
                for attr in ['plain_text', 'raw_message', 'content', 'text']:
                    if hasattr(self.message, attr):
                        value = getattr(self.message, attr)
                        if value and str(value).strip():
                            msg = str(value).strip()
                            logger.debug(f"从message.{attr}获取消息: {msg[:50]}...")
                            return msg
            
            # 方法2: 从action_data获取
            action_data = getattr(self, 'action_data', {})
            if isinstance(action_data, dict):
                for key in ['user_query', 'query', 'question', 'message', 'content', 'text']:
                    if key in action_data and action_data[key]:
                        msg = str(action_data[key]).strip()
                        logger.debug(f"从action_data.{key}获取消息: {msg[:50]}...")
                        return msg
            
            logger.warning("未能获取用户消息")
            return ""
            
        except Exception as e:
            logger.error(f"获取用户消息失败: {e}")
            return ""

    def _get_card_range(self, card_type: str) -> list:
        """获取卡牌范围"""
        valid_ids = []
        
        # 收集所有数字ID
        for key in self.card_map.keys():
            if key != "_meta" and key.isdigit():
                try:
                    card_id = int(key)
                    valid_ids.append(str(card_id))
                except ValueError:
                    continue
        
        # 按范围过滤
        if card_type == "大阿卡纳":
            return [cid for cid in valid_ids if 0 <= int(cid) < 22]
        elif card_type == "小阿卡纳":
            return [cid for cid in valid_ids if 22 <= int(cid) < 78]
        else:  # 全部
            return valid_ids

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
        
        return ""

    async def _generate_llm_interpretation(self, card_details: List[Dict], formation_name: str, 
                                         card_type: str, user_query: str, user_message: str) -> str:
        """使用LLM生成个性化解读"""
        try:
            # 构建完整的牌阵信息
            formation_info = self._build_formation_info(card_details, formation_name, card_type)
            
            # 判断是单张牌还是复杂牌阵
            is_single = len(card_details) == 1
            
            # 构建提示词
            prompt = self._build_interpretation_prompt(
                formation_info, formation_name, card_type, user_query, user_message, is_single
            )
            
            logger.info(f"生成LLM提示词，长度: {len(prompt)}")
            
            # 调用LLM API
            models = llm_api.get_available_models()
            if not models:
                logger.warning("无法获取模型配置，使用备用解读")
                return self._get_fallback_interpretation(card_details, formation_name, user_query, is_single)
            
            chat_model_config = models.get("replyer") or models.get("default")
            if not chat_model_config:
                logger.warning("无法获取回复模型，使用备用解读")
                return self._get_fallback_interpretation(card_details, formation_name, user_query, is_single)
            
            success, result, _, _ = await llm_api.generate_with_model(
                prompt, 
                model_config=chat_model_config, 
                request_type="tarots_interpretation"
            )
            
            if success and result and len(result.strip()) > 10:
                interpretation = result.strip()
                # 清理结果
                interpretation = self._clean_interpretation(interpretation, formation_name, is_single)
                return interpretation
            else:
                logger.warning(f"LLM生成失败: success={success}, result_length={len(str(result))}")
                return self._get_fallback_interpretation(card_details, formation_name, user_query, is_single)
                
        except Exception as e:
            logger.error(f"LLM解读生成失败: {e}")
            traceback.print_exc()
            return self._get_fallback_interpretation(card_details, formation_name, user_query, len(card_details) == 1)

    def _build_formation_info(self, card_details: List[Dict], formation_name: str, card_type: str) -> str:
        """构建牌阵信息字符串"""
        info_lines = []
        
        # 添加牌阵概述
        info_lines.append(f"牌阵：{formation_name}（{card_type}）")
        info_lines.append(f"牌数：{len(card_details)}张")
        info_lines.append("")
        
        # 添加每张牌的详细信息
        for i, card in enumerate(card_details):
            status = "逆位" if card['is_reverse'] else "正位"
            position_info = f"{card['position']}（{card['position_meaning']}）" if card['position_meaning'] else card['position']
            
            line = f"{i+1}. {card['name']} {status} - {position_info}"
            if card['description'] and card['description'] != "暂无描述":
                desc = card['description'][:50] + "..." if len(card['description']) > 50 else card['description']
                line += f"\n   含义：{desc}"
            
            info_lines.append(line)
        
        return "\n".join(info_lines)

    def _build_interpretation_prompt(self, formation_info: str, formation_name: str, 
                                   card_type: str, user_query: str, user_message: str, is_single: bool) -> str:
        """构建LLM提示词"""
        
        # 根据是否单张牌设置不同的要求
        if is_single:
            length_limit = "2-3句话，不超过60字"
            per_card_instruction = ""
        else:
            card_count = formation_info.count("张牌")
            length_limit = f"每张牌1-1.5句，句子内容要简洁明了,所有解牌内容总共不超过{card_count * 30}字"
            per_card_instruction = "请为每张牌分别提供简短解读，整体保持连贯。"
        
        prompt = f"""请为{user_query}的塔罗牌占卜提供简短解读。

{formation_info}

用户问题：{user_query}
抽牌范围：{card_type}
牌阵类型：{formation_name}

要求：
1. 直接回应用户关于{user_query}的问题
2. {per_card_instruction}
3. 像朋友聊天一样自然亲切,不要有太多包袱
4. {length_limit}
5. 语气温暖，根据结果给出实用的建议
6. 结合每张牌在牌阵中的位置含义
7. 不要用专业术语，保持口语化

解读："""
        
        return prompt

    def _clean_interpretation(self, interpretation: str, formation_name: str, is_single: bool) -> str:
        """清理和截断解读文本"""
        # 移除多余空行和空格
        lines = [line.strip() for line in interpretation.split('\n') if line.strip()]
        text = ' '.join(lines)
        
        # 限制长度
        if is_single:
            # 单张牌：不超过60字
            if len(text) > 60:
                for i in range(55, 60):
                    if i < len(text) and text[i] in '。！？.?!':
                        text = text[:i+1]
                        break
                else:
                    text = text[:57] + "..."
        else:
            # 复杂牌阵：根据牌数决定最大长度
            # 计算牌数（根据formation_name判断）
            formation_card_count = {
                "圣三角": 3,
                "时间之流": 3,
                "四要素": 4,
                "五牌阵": 5,
                "吉普赛十字": 5,
                "马蹄": 6,
                "六芒星": 6
            }
            
            card_count = formation_card_count.get(formation_name, 3)  # 默认3张
            max_chars = card_count * 85  # 每张牌85字，比提示词要求更宽松
            
            if len(text) > max_chars:
                # 在标点处优雅截断
                for i in range(max_chars - 20, max_chars):
                    if i < len(text) and text[i] in '。！？.?!，,;；':
                        text = text[:i+1]
                        break
                else:
                    # 没有找到合适标点，在完整句子后加省略号
                    text = text[:max_chars-3] + "..."
        
        # 添加牌阵前缀
        if not text.startswith(formation_name):
            text = f"🔮 {formation_name}解读：{text}"
        
        return text

    def _get_fallback_interpretation(self, card_details: List[Dict], formation_name: str, 
                                   user_query: str, is_single: bool) -> str:
        """备用解读方案"""
        if is_single:
            # 单张牌的备用解读
            card = card_details[0]
            status = "逆位" if card['is_reverse'] else "正位"
            interpretations = [
                f"✨ {card['name']}{status}说：关于{user_query}，放轻松就好～",
                f"💫 {card['name']}{status}在讲：{user_query}方面，相信自己直觉哦。",
                f"🌟 {card['name']}{status}表示：{user_query}的话，保持平常心啦。",
            ]
        else:
            # 复杂牌阵的备用解读
            card_names = [f"{card['name']}{'逆位' if card['is_reverse'] else '正位'}" for card in card_details]
            card_list = "、".join(card_names)
            
            interpretations = [
                f"🔮 {formation_name}抽到{card_list}～关于{user_query}，整体能量还不错，保持信心！",
                f"✨ {formation_name}牌阵{card_list}，{user_query}方面需要平衡各因素，别太担心～",
                f"💫 {formation_name}的{card_list}在为{user_query}提供指引，耐心观察会有收获。",
            ]
        
        return random.choice(interpretations)

    async def _send_card_image(self, card_id: str, is_reverse: bool) -> bool:
        """发送卡牌图片"""
        try:
            card_data = self.card_map.get(card_id, {})
            if not card_data:
                logger.error(f"卡牌数据不存在: {card_id}")
                return False
                
            card_name = card_data.get("name", "")
            if not card_name:
                logger.error(f"卡牌名称不存在: {card_id}")
                return False
            
            # 构建图片文件名
            position = "逆位" if is_reverse else "正位"
            
            # 尝试多种可能的文件名格式
            possible_filenames = [
                f"{card_name}{position}.jpg",
                f"{card_name}{position}.png",
                f"{card_name}.jpg",
                f"{card_name}.png",
                f"{card_name.replace('ACE', '王牌').replace('2', '二').replace('3', '三').replace('4', '四').replace('5', '五').replace('6', '六').replace('7', '七').replace('8', '八').replace('9', '九').replace('10', '十')}{position}.jpg",
            ]
            
            img_path = None
            for filename in possible_filenames:
                path = self.base_dir / f"tarot_jsons/{self.using_cards}/{filename}"
                if path.exists():
                    img_path = path
                    logger.info(f"找到图片文件: {path}")
                    break
            
            if not img_path:
                logger.error(f"图片文件不存在，尝试的文件名: {possible_filenames}")
                return False
            
            # 读取并发送图片
            with open(img_path, "rb") as f:
                img_data = f.read()
            
            img_base64 = base64.b64encode(img_data).decode('utf-8')
            await self.send_image(img_base64)
            
            logger.info(f"成功发送图片: {img_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"发送图片失败: {str(e)}")
            traceback.print_exc()
            return False

@register_plugin
class TarotsPlugin(BasePlugin):
    """塔罗牌插件"""
    
    plugin_name = "tarots_plugin"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = []

    plugin_description = "提供高版本塔罗牌占卜功能，牌面为BiliBili幻星集"
    plugin_version = "4.1.0"
    plugin_author = "KArabella"

    config_section_descriptions = {
        "plugin": "插件基本配置",
        "components": "组件启用控制",
        "cards": "牌组配置"
    }

    config_schema = {
        "plugin": {
            "config_version": ConfigField(type=str, default="4.1.0", description="配置文件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        "components": {
            "enable_tarots": ConfigField(type=bool, default=True, description="启用塔罗牌占卜功能"),
        },
        "cards": {
            "using_cards": ConfigField(type=str, default='bilibili', description="当前使用牌组"),
            "use_cards": ConfigField(type=list, default=['bilibili','east'], description="可用牌组列表")
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件"""
        components = []
        if self.get_config("components.enable_tarots", True):
            components.append((TarotsAction.get_action_info(), TarotsAction))
        
        logger.info(f"注册塔罗牌Action组件: {len(components)}个")
        return components