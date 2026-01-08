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

import time
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass
from enum import Enum


class IntentType(Enum):
    """意图类型枚举"""
    SPEAKER_IDENTIFY = "speaker_identify"       # 声纹识别意图（识别当前说话人）
    SPEAKER_IDENTIFY_OTHER = "speaker_identify_other"  # 声纹识别他人意图（两轮对话）
    LOOK = "look"                               # 看相关意图（需要拍照）
    DEFAULT = "default"                         # 默认意图（纯文本对话）


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
    # 声纹识别相关
    speaker_name: Optional[str] = None            # 识别出的说话人名字
    speaker_similarity: float = 0.0               # 声纹相似度
    pending_speaker_embedding: Optional[Any] = None  # 待注册的声纹嵌入向量
    waiting_for_other_speaker: bool = False       # 是否在等待他人说话（两轮对话模式）
    # 耗时统计（毫秒）
    time_camera: float = 0.0                # 拍照耗时
    time_face_detect: float = 0.0           # 人脸检测/识别耗时
    time_object_detect: float = 0.0         # 物体检测耗时
    time_speaker_identify: float = 0.0      # 声纹识别耗时


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

    # 声纹识别触发关键词（识别当前说话人）
    SPEAKER_IDENTIFY_KEYWORDS = [
        "这是谁的声音", "谁在说话", "听出来是谁了吗",
        "识别声音", "这声音是谁", "谁的声音", "辨别声音",
        # 测试用关键词
        "识别声纹", "测试声纹识别", "声纹识别"
    ]

    # 声纹识别他人触发关键词（两轮对话模式：先提示对方说话，再识别）
    SPEAKER_IDENTIFY_OTHER_KEYWORDS = [
        "听听他是谁", "听听她是谁", "听一听他是谁", "听一听她是谁",
        "听听这是谁", "听一听这是谁",
        "让他说几句", "让她说几句",
        "识别他的声音", "识别她的声音"
    ]

    # 看相关意图的触发关键词
    # 注意：避免单字"看"，防止"说说看"等习惯用语被误匹配
    LOOK_KEYWORDS = [
        # 双字及以上的"看"相关词
        "看看", "看一看", "看一下", "瞧瞧", "瞧一瞧",
        "瞅一瞅", "瞅瞅", "瞄一眼", "瞄瞄",
        # 拍照相关
        "拍照", "拍一张", "拍个照", "照相",
        # 询问物体
        "这是什么", "那是什么", "这个是什么", "那个是什么",
        # 明确的看意图
        "帮我看看", "给我看看", "让我看看",
        "前面有什么", "周围有什么", "眼前有什么"
    ]

    def __init__(
        self,
        camera_callback: Optional[Callable[[], Optional[str]]] = None,
        face_recognition_manager: Optional[Any] = None,
        object_detector: Optional[Any] = None,
        speaker_recognition_manager: Optional[Any] = None,
        audio_callback: Optional[Callable[[], Optional[bytes]]] = None
    ):
        """
        初始化意图处理器

        Args:
            camera_callback: 摄像头拍照回调函数，返回图片路径或None
            face_recognition_manager: 人脸识别管理器实例
            object_detector: 物体检测器实例
            speaker_recognition_manager: 声纹识别管理器实例
            audio_callback: 获取当前音频数据的回调函数，返回PCM音频字节或None
        """
        self.camera_callback = camera_callback
        self.face_recognition_manager = face_recognition_manager
        self.object_detector = object_detector
        self.speaker_recognition_manager = speaker_recognition_manager
        self.audio_callback = audio_callback
        self.rules: List[IntentRule] = []
        self._init_default_rules()

    def _init_default_rules(self):
        """初始化默认规则（按优先级顺序）"""
        # 规则1：声纹识别他人意图（两轮对话模式，优先级最高）
        speaker_identify_other_rule = IntentRule(
            name="speaker_identify_other_intent",
            intent_type=IntentType.SPEAKER_IDENTIFY_OTHER,
            keywords=self.SPEAKER_IDENTIFY_OTHER_KEYWORDS,
            description="检测声纹识别他人意图，进入两轮对话模式"
        )
        self.rules.append(speaker_identify_other_rule)

        # 规则2：声纹识别意图（识别当前说话人）
        speaker_identify_rule = IntentRule(
            name="speaker_identify_intent",
            intent_type=IntentType.SPEAKER_IDENTIFY,
            keywords=self.SPEAKER_IDENTIFY_KEYWORDS,
            description="检测声纹识别意图，识别当前说话人"
        )
        self.rules.append(speaker_identify_rule)

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
                if rule.intent_type == IntentType.SPEAKER_IDENTIFY_OTHER:
                    result = self._handle_speaker_identify_other_intent(result)
                elif rule.intent_type == IntentType.SPEAKER_IDENTIFY:
                    result = self._handle_speaker_identify_intent(result)
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
            # 拍照（带计时）
            print("[IntentHandler] 正在调用摄像头拍照（本地识别模式）...")
            camera_start = time.time()
            image_path = self.camera_callback()
            result.time_camera = (time.time() - camera_start) * 1000
            print(f"[计时] 拍照: {result.time_camera:.0f}ms")

            if not image_path:
                result.error_message = "拍照失败"
                print("[IntentHandler] 拍照失败")
                return result

            result.image_path = image_path
            print(f"[IntentHandler] 拍照成功: {image_path}")

            # 人脸识别（带计时）
            if self.face_recognition_manager:
                try:
                    face_start = time.time()
                    recognition_results = self.face_recognition_manager.recognize_faces(image_path)
                    result.time_face_detect = (time.time() - face_start) * 1000
                    print(f"[计时] 人脸识别: {result.time_face_detect:.0f}ms")

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

            # 物体检测（带计时）
            if self.object_detector:
                try:
                    object_start = time.time()
                    detections = self.object_detector.detect(image_path)
                    result.time_object_detect = (time.time() - object_start) * 1000
                    print(f"[计时] 物体检测: {result.time_object_detect:.0f}ms")

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

    def _handle_speaker_identify_other_intent(self, result: IntentResult) -> IntentResult:
        """
        处理声纹识别他人意图（两轮对话模式）

        第一轮：提示用户让对方说话
        第二轮：对对方的语音进行声纹识别

        Args:
            result: 当前意图结果

        Returns:
            更新后的意图结果（设置 waiting_for_other_speaker=True）
        """
        # 设置等待他人说话的标志
        result.waiting_for_other_speaker = True
        print("[IntentHandler] 进入声纹识别他人模式，等待对方说话")
        return result

    def _handle_speaker_identify_intent(
        self,
        result: IntentResult,
        audio_bytes: bytes = None
    ) -> IntentResult:
        """
        处理声纹识别意图：识别当前说话人

        Args:
            result: 当前意图结果
            audio_bytes: 音频数据（如果已有），否则从 audio_callback 获取

        Returns:
            更新后的意图结果（包含识别结果）
        """
        if not self.speaker_recognition_manager:
            print("[IntentHandler] 警告: 未设置声纹识别管理器")
            result.error_message = "声纹识别功能未配置"
            return result

        try:
            # 获取音频数据
            if audio_bytes is None:
                if self.audio_callback:
                    audio_bytes = self.audio_callback()
                else:
                    result.error_message = "无法获取音频数据"
                    print("[IntentHandler] 错误: 未设置音频回调函数")
                    return result

            if not audio_bytes:
                result.error_message = "音频数据为空"
                print("[IntentHandler] 错误: 音频数据为空")
                return result

            # 提取声纹并匹配（带计时）
            print("[IntentHandler] 正在进行声纹识别...")
            identify_start = time.time()

            embedding = self.speaker_recognition_manager.extract_embedding(audio_bytes)
            if embedding is None:
                result.error_message = "无法提取声纹特征（音频可能太短或全是静音）"
                print("[IntentHandler] 无法提取声纹特征")
                return result

            # 匹配声纹
            speaker_name, similarity = self.speaker_recognition_manager.match_speaker(embedding)
            result.time_speaker_identify = (time.time() - identify_start) * 1000
            print(f"[计时] 声纹识别: {result.time_speaker_identify:.0f}ms")

            if speaker_name:
                result.speaker_name = speaker_name
                result.speaker_similarity = similarity
                print(f"[IntentHandler] 声纹识别成功: {speaker_name} (相似度: {similarity:.3f})")
            else:
                result.speaker_similarity = similarity
                print(f"[IntentHandler] 未能识别说话人 (最高相似度: {similarity:.3f})")

        except Exception as e:
            result.error_message = f"声纹识别异常: {str(e)}"
            print(f"[IntentHandler] 声纹识别异常: {e}")

        return result

    def process_with_audio(self, text: str, audio_bytes: bytes = None) -> IntentResult:
        """
        处理用户输入，同时支持音频数据（用于声纹识别）

        Args:
            text: 用户输入文本（语音识别结果）
            audio_bytes: 对应的音频数据（可选）

        Returns:
            IntentResult: 意图判断结果
        """
        result = self.process(text)

        # 如果是声纹识别意图且有音频数据，补充处理
        if result.intent_type == IntentType.SPEAKER_IDENTIFY and audio_bytes:
            result = self._handle_speaker_identify_intent(result, audio_bytes)

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
