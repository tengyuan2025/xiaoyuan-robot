# -*- coding: utf-8 -*-
"""
意图判断模块

功能：
1. 规则化意图匹配
2. 按规则顺序匹配，匹配成功则执行对应动作
3. 未匹配则走默认规则

作者：Claude Code
日期：2024
"""

from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass
from enum import Enum


class IntentType(Enum):
    """意图类型枚举"""
    FACE_REGISTER = "face_register"   # 人脸注册意图（记住某人）
    FACE_RECOGNIZE = "face_recognize" # 人脸识别意图（识别某人）
    LOOK = "look"                     # 看相关意图（需要拍照）
    DEFAULT = "default"               # 默认意图（纯文本对话）


@dataclass
class IntentResult:
    """意图判断结果"""
    intent_type: IntentType
    matched_keyword: Optional[str] = None   # 匹配到的关键词
    image_path: Optional[str] = None        # 拍摄的图片路径（如果有）
    original_text: str = ""                 # 原始识别文本
    error_message: Optional[str] = None     # 错误信息（如摄像头调用失败）
    # 人脸识别相关
    face_results: Optional[List[Dict]] = None     # 人脸识别结果列表
    pending_face_encoding: Optional[Any] = None   # 待注册的人脸编码（追问模式）
    # 物体检测相关
    object_results: Optional[List[Dict]] = None   # 物体检测结果列表


@dataclass
class IntentRule:
    """
    意图规则定义

    Attributes:
        name: 规则名称
        intent_type: 意图类型
        keywords: 触发关键词列表
        action: 匹配成功后执行的动作函数（可选）
        description: 规则描述
    """
    name: str
    intent_type: IntentType
    keywords: List[str]
    action: Optional[Callable[[str], Any]] = None
    description: str = ""


class IntentHandler:
    """
    意图判断处理器

    按规则顺序匹配用户输入，返回匹配结果
    """

    # 人脸注册触发关键词（优先级最高）
    FACE_REGISTER_KEYWORDS = [
        "记住我", "记住他", "记住她", "记住这个人",
        "记住这张脸", "保存人脸", "保存脸", "注册人脸",
        "记一下", "记下来"
    ]

    # 人脸识别触发关键词（优先级次高）
    FACE_RECOGNIZE_KEYWORDS = [
        "这是谁", "他是谁", "她是谁", "这个人是谁",
        "认识这个人吗", "你认识他吗", "你认识她吗",
        "认识吗", "识别一下", "看看是谁"
    ]

    # 看相关意图的触发关键词
    LOOK_KEYWORDS = [
        "看", "瞧瞧", "看看", "瞅一瞅", "瞄一眼",
        "瞧一瞧", "看一看", "看一下", "瞅瞅", "瞄瞄",
        "拍照", "拍一张", "拍个照", "照相",
        "这是什么", "那是什么", "这个是什么", "那个是什么",
        "帮我看", "给我看", "让我看"
    ]

    def __init__(
        self,
        camera_callback: Optional[Callable[[], Optional[str]]] = None,
        face_recognition_manager: Optional[Any] = None,
        object_detector: Optional[Any] = None
    ):
        """
        初始化意图处理器

        Args:
            camera_callback: 摄像头拍照回调函数，返回图片路径或None
            face_recognition_manager: 人脸识别管理器实例
            object_detector: 物体检测器实例
        """
        self.camera_callback = camera_callback
        self.face_recognition_manager = face_recognition_manager
        self.object_detector = object_detector
        self.rules: List[IntentRule] = []
        self._init_default_rules()

    def _init_default_rules(self):
        """初始化默认规则（按优先级顺序）"""
        # 规则1：人脸注册意图（优先级最高）
        face_register_rule = IntentRule(
            name="face_register_intent",
            intent_type=IntentType.FACE_REGISTER,
            keywords=self.FACE_REGISTER_KEYWORDS,
            description="检测人脸注册意图，拍照并追问人名"
        )
        self.rules.append(face_register_rule)

        # 规则2：人脸识别意图
        face_recognize_rule = IntentRule(
            name="face_recognize_intent",
            intent_type=IntentType.FACE_RECOGNIZE,
            keywords=self.FACE_RECOGNIZE_KEYWORDS,
            description="检测人脸识别意图，拍照并识别人脸"
        )
        self.rules.append(face_recognize_rule)

        # 规则3：看相关意图
        look_rule = IntentRule(
            name="look_intent",
            intent_type=IntentType.LOOK,
            keywords=self.LOOK_KEYWORDS,
            description="检测看相关意图，触发摄像头拍照"
        )
        self.rules.append(look_rule)

    def add_rule(self, rule: IntentRule, index: Optional[int] = None):
        """
        添加新规则

        Args:
            rule: 意图规则
            index: 插入位置（None表示添加到末尾）
        """
        if index is None:
            self.rules.append(rule)
        else:
            self.rules.insert(index, rule)

    def remove_rule(self, rule_name: str) -> bool:
        """
        移除规则

        Args:
            rule_name: 规则名称

        Returns:
            是否成功移除
        """
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                return True
        return False

    def _match_keywords(self, text: str, keywords: List[str]) -> Optional[str]:
        """
        检查文本是否包含关键词

        Args:
            text: 待检查文本
            keywords: 关键词列表

        Returns:
            匹配到的关键词，未匹配返回None
        """
        for keyword in keywords:
            if keyword in text:
                return keyword
        return None

    def process(self, text: str) -> IntentResult:
        """
        处理用户输入，判断意图

        Args:
            text: 用户输入文本（语音识别结果）

        Returns:
            IntentResult: 意图判断结果
        """
        if not text or not text.strip():
            return IntentResult(
                intent_type=IntentType.DEFAULT,
                original_text=text
            )

        # 按规则顺序匹配
        for rule in self.rules:
            matched_keyword = self._match_keywords(text, rule.keywords)
            if matched_keyword:
                print(f"[IntentHandler] 匹配规则: {rule.name}, 关键词: {matched_keyword}")

                result = IntentResult(
                    intent_type=rule.intent_type,
                    matched_keyword=matched_keyword,
                    original_text=text
                )

                # 根据意图类型处理
                if rule.intent_type == IntentType.FACE_REGISTER:
                    result = self._handle_face_register_intent(result)
                elif rule.intent_type == IntentType.FACE_RECOGNIZE:
                    result = self._handle_face_recognize_intent(result)
                elif rule.intent_type == IntentType.LOOK:
                    result = self._handle_look_intent(result)

                # 执行规则自定义动作（如果有）
                if rule.action:
                    try:
                        rule.action(text)
                    except Exception as e:
                        print(f"[IntentHandler] 规则动作执行失败: {e}")

                return result

        # 未匹配任何规则，返回默认意图
        print("[IntentHandler] 未匹配任何规则，使用默认意图")
        return IntentResult(
            intent_type=IntentType.DEFAULT,
            original_text=text
        )

    def _handle_look_intent(self, result: IntentResult) -> IntentResult:
        """
        处理看相关意图：拍照 + 人脸识别 + 物体检测

        Args:
            result: 当前意图结果

        Returns:
            更新后的意图结果（包含识别结果）
        """
        if not self.camera_callback:
            print("[IntentHandler] 警告: 未设置摄像头回调函数")
            result.error_message = "摄像头功能未配置"
            return result

        try:
            print("[IntentHandler] 正在调用摄像头拍照（本地识别模式）...")
            image_path = self.camera_callback()

            if not image_path:
                result.error_message = "拍照失败"
                print("[IntentHandler] 拍照失败")
                return result

            result.image_path = image_path
            print(f"[IntentHandler] 拍照成功: {image_path}")

            # 人脸识别
            if self.face_recognition_manager:
                try:
                    recognition_results = self.face_recognition_manager.recognize_faces(image_path)
                    if recognition_results:
                        result.face_results = [
                            {
                                "name": r.name,
                                "confidence": r.confidence,
                                "location": r.location
                            }
                            for r in recognition_results
                        ]
                        names = [r.name for r in recognition_results]
                        print(f"[IntentHandler] 人脸识别完成: {names}")
                    else:
                        # 检查是否检测到人脸但无法识别
                        face_locations = self.face_recognition_manager.detect_faces(image_path)
                        if face_locations:
                            result.face_results = [{"name": "unknown", "confidence": 0.0} for _ in face_locations]
                            print(f"[IntentHandler] 检测到 {len(face_locations)} 张未知人脸")
                except Exception as e:
                    print(f"[IntentHandler] 人脸识别异常: {e}")

            # 物体检测
            if self.object_detector:
                try:
                    detections = self.object_detector.detect(image_path)
                    if detections:
                        result.object_results = [
                            {
                                "class_name": d.class_name,
                                "confidence": d.confidence,
                                "bbox": d.bbox
                            }
                            for d in detections
                        ]
                        objects = [d.class_name for d in detections]
                        print(f"[IntentHandler] 物体检测完成: {objects}")
                except Exception as e:
                    print(f"[IntentHandler] 物体检测异常: {e}")

        except Exception as e:
            result.error_message = f"本地识别异常: {str(e)}"
            print(f"[IntentHandler] 本地识别异常: {e}")

        return result

    def _handle_face_register_intent(self, result: IntentResult) -> IntentResult:
        """
        处理人脸注册意图：拍照并提取人脸编码

        Args:
            result: 当前意图结果

        Returns:
            更新后的意图结果（包含待注册的人脸编码）
        """
        if not self.camera_callback:
            print("[IntentHandler] 警告: 未设置摄像头回调函数")
            result.error_message = "摄像头功能未配置"
            return result

        if not self.face_recognition_manager:
            print("[IntentHandler] 警告: 未设置人脸识别管理器")
            result.error_message = "人脸识别功能未配置"
            return result

        try:
            print("[IntentHandler] 正在调用摄像头拍照（人脸注册）...")
            image_path = self.camera_callback()

            if not image_path:
                result.error_message = "拍照失败"
                print("[IntentHandler] 拍照失败")
                return result

            result.image_path = image_path

            # 提取人脸编码
            encoding = self.face_recognition_manager.encode_face(image_path)
            if encoding is not None:
                result.pending_face_encoding = encoding
                print("[IntentHandler] 人脸编码提取成功，等待用户提供人名")
            else:
                result.error_message = "未检测到人脸，请确保脸部清晰可见"
                print("[IntentHandler] 未检测到人脸")

        except Exception as e:
            result.error_message = f"人脸注册异常: {str(e)}"
            print(f"[IntentHandler] 人脸注册异常: {e}")

        return result

    def _handle_face_recognize_intent(self, result: IntentResult) -> IntentResult:
        """
        处理人脸识别意图：拍照并识别人脸

        Args:
            result: 当前意图结果

        Returns:
            更新后的意图结果（包含识别结果）
        """
        if not self.camera_callback:
            print("[IntentHandler] 警告: 未设置摄像头回调函数")
            result.error_message = "摄像头功能未配置"
            return result

        if not self.face_recognition_manager:
            print("[IntentHandler] 警告: 未设置人脸识别管理器")
            result.error_message = "人脸识别功能未配置"
            return result

        try:
            print("[IntentHandler] 正在调用摄像头拍照（人脸识别）...")
            image_path = self.camera_callback()

            if not image_path:
                result.error_message = "拍照失败"
                print("[IntentHandler] 拍照失败")
                return result

            result.image_path = image_path

            # 识别人脸
            recognition_results = self.face_recognition_manager.recognize_faces(image_path)
            if recognition_results:
                result.face_results = [
                    {
                        "name": r.name,
                        "confidence": r.confidence,
                        "location": r.location
                    }
                    for r in recognition_results
                ]
                names = [r.name for r in recognition_results]
                print(f"[IntentHandler] 人脸识别完成: {names}")
            else:
                # 检查是否检测到人脸但未识别
                face_locations = self.face_recognition_manager.detect_faces(image_path)
                if face_locations:
                    result.face_results = [{"name": "unknown", "confidence": 0.0}]
                    print("[IntentHandler] 检测到人脸但无法识别")
                else:
                    result.error_message = "未检测到人脸"
                    print("[IntentHandler] 未检测到人脸")

        except Exception as e:
            result.error_message = f"人脸识别异常: {str(e)}"
            print(f"[IntentHandler] 人脸识别异常: {e}")

        return result


# 便捷函数：检查是否为看相关意图
def is_look_intent(text: str) -> bool:
    """
    快速检查文本是否包含看相关意图

    Args:
        text: 待检查文本

    Returns:
        是否为看相关意图
    """
    for keyword in IntentHandler.LOOK_KEYWORDS:
        if keyword in text:
            return True
    return False
