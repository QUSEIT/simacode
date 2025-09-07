"""
TICMaker检测器
用于检测和处理scope为ticmaker的请求，确保能穿透现有的对话检测机制
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class TICMakerDetector:
    """TICMaker请求检测器，支持多种检测方式"""
    
    # TICMaker相关关键词
    TICMAKER_KEYWORDS = [
        "ticmaker", "TICMaker", "互动课堂", "教学活动", "互动教学", 
        "课堂互动", "教育内容", "教学设计", "互动内容", "教学游戏",
        "创建页面", "制作网页", "HTML页面", "网页制作", "互动页面"
    ]
    
    # 教学内容相关模式
    TEACHING_PATTERNS = [
        r"帮我.*(创建|设计|制作).*(课程|教学|活动|页面|网页)",
        r".*(互动|教学).*(内容|活动|游戏|页面)",
        r"如何.*(设计|制作).*(教学|课堂|页面)",
        r".*(创建|生成|制作).*(HTML|网页|页面)",
        r"制作.*教育.*内容",
        r"设计.*互动.*体验"
    ]
    
    @classmethod
    def detect_ticmaker_request(
        cls, 
        message: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        检测是否为TICMaker请求
        
        Args:
            message: 用户消息
            context: 请求上下文
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: (是否为TICMaker请求, 检测原因, 增强的上下文)
        """
        context = context or {}
        original_context = context.copy()
        
        logger.debug(f"检测TICMaker请求 - 消息: {message[:100]}...")
        logger.debug(f"原始上下文: {context}")
        
        # 1. 显式scope检测 - 最高优先级
        if context.get("scope") == "ticmaker":
            logger.info("TICMaker请求检测: 显式scope=ticmaker")
            return True, "explicit_scope_ticmaker", context
        
        # 2. 显式触发标记检测
        if context.get("trigger_ticmaker_tool", False):
            logger.info("TICMaker请求检测: 显式trigger_ticmaker_tool=True")
            return True, "explicit_trigger_flag", context
        
        # 3. CLI TICMaker标记检测
        if context.get("ticmaker_processing", False):
            logger.info("TICMaker请求检测: CLI ticmaker_processing=True")
            return True, "cli_ticmaker_flag", context
        
        # 4. 消息关键词检测
        message_lower = message.lower()
        for keyword in cls.TICMAKER_KEYWORDS:
            if keyword.lower() in message_lower:
                enhanced_context = original_context.copy()
                enhanced_context.update({
                    "scope": "ticmaker",
                    "detected_keyword": keyword,
                    "auto_detected": True,
                    "trigger_ticmaker_tool": True,
                    "detection_method": "keyword"
                })
                logger.info(f"TICMaker请求检测: 关键词匹配 '{keyword}'")
                return True, f"keyword_detected:{keyword}", enhanced_context
        
        # 5. 教学内容模式检测（正则表达式）
        for i, pattern in enumerate(cls.TEACHING_PATTERNS):
            if re.search(pattern, message, re.IGNORECASE):
                enhanced_context = original_context.copy()
                enhanced_context.update({
                    "scope": "ticmaker",
                    "detected_pattern": pattern,
                    "auto_detected": True,
                    "trigger_ticmaker_tool": True,
                    "detection_method": "pattern",
                    "pattern_index": i
                })
                logger.info(f"TICMaker请求检测: 模式匹配 #{i}")
                return True, f"pattern_detected:{i}", enhanced_context
        
        logger.debug("TICMaker请求检测: 未发现TICMaker指标")
        return False, "no_ticmaker_indicators", original_context
    
    @classmethod
    def should_force_react_mode(cls, message: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        判断是否应该强制使用ReAct模式
        
        Args:
            message: 用户消息
            context: 请求上下文
            
        Returns:
            bool: 是否应该强制使用ReAct模式
        """
        is_ticmaker, _, _ = cls.detect_ticmaker_request(message, context)
        return is_ticmaker
    
    @classmethod
    def prepare_ticmaker_tool_input(
        cls,
        message: str,
        context: Dict[str, Any],
        session_id: str,
        source: str = "unknown",
        trigger_reason: str = "auto",
        operation: str = "create"
    ) -> Dict[str, Any]:
        """
        准备TICMaker工具的输入参数
        
        Args:
            message: 用户消息
            context: 请求上下文
            session_id: 会话ID
            source: 请求来源 (CLI/API)
            trigger_reason: 触发原因
            operation: 操作类型 (create/modify)
            
        Returns:
            Dict[str, Any]: 工具输入参数
        """
        # 从上下文中提取文件路径信息
        file_path = context.get("file_path")
        
        # 如果消息中包含修改指令且有文件路径，则为修改操作
        if file_path and any(word in message.lower() for word in ["修改", "更新", "编辑", "改变"]):
            operation = "modify"
        
        tool_input = {
            "message": message,
            "context": context,
            "session_id": session_id,
            "source": source,
            "operation": operation
        }
        
        logger.debug(f"准备TICMaker工具输入: {tool_input}")
        return tool_input
    
    @classmethod
    def extract_html_requirements(cls, message: str) -> Dict[str, Any]:
        """
        从用户消息中提取HTML页面需求信息
        
        Args:
            message: 用户消息
            
        Returns:
            Dict[str, Any]: 提取的需求信息
        """
        requirements = {
            "template": "basic",
            "style": "modern",
            "interactive": False,
            "educational": False
        }
        
        message_lower = message.lower()
        
        # 检测模板类型
        if any(word in message_lower for word in ["互动", "游戏", "点击", "按钮"]):
            requirements["template"] = "interactive"
            requirements["interactive"] = True
        
        if any(word in message_lower for word in ["教学", "教育", "课程", "学习", "课堂"]):
            requirements["educational"] = True
            if requirements["template"] == "basic":
                requirements["template"] = "educational"
        
        # 检测样式要求
        if any(word in message_lower for word in ["现代", "时尚", "简洁"]):
            requirements["style"] = "modern"
        elif any(word in message_lower for word in ["经典", "传统", "正式"]):
            requirements["style"] = "classic"
        elif any(word in message_lower for word in ["活泼", "有趣", "彩色"]):
            requirements["style"] = "colorful"
        
        logger.debug(f"提取的HTML需求: {requirements}")
        return requirements
    
    @classmethod
    def is_modification_request(cls, message: str, context: Dict[str, Any]) -> bool:
        """
        判断是否为修改现有页面的请求
        
        Args:
            message: 用户消息
            context: 请求上下文
            
        Returns:
            bool: 是否为修改请求
        """
        # 如果上下文中有文件路径，可能是修改请求
        has_file_path = bool(context.get("file_path"))
        
        # 检查消息中的修改相关词汇
        modification_keywords = ["修改", "更新", "编辑", "改变", "调整", "优化", "完善"]
        has_modification_keywords = any(
            keyword in message.lower() for keyword in modification_keywords
        )
        
        is_modification = has_file_path and has_modification_keywords
        
        logger.debug(f"修改请求检测: 文件路径={has_file_path}, 修改关键词={has_modification_keywords}, 结果={is_modification}")
        return is_modification
    
    @classmethod 
    def get_debug_info(cls, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取检测过程的调试信息
        
        Args:
            message: 用户消息
            context: 请求上下文
            
        Returns:
            Dict[str, Any]: 调试信息
        """
        is_ticmaker, reason, enhanced_context = cls.detect_ticmaker_request(message, context)
        
        debug_info = {
            "is_ticmaker_request": is_ticmaker,
            "detection_reason": reason,
            "original_context": context,
            "enhanced_context": enhanced_context,
            "should_force_react": cls.should_force_react_mode(message, context),
            "is_modification": cls.is_modification_request(message, enhanced_context),
            "html_requirements": cls.extract_html_requirements(message)
        }
        
        return debug_info