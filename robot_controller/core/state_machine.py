# -*- coding: utf-8 -*-
"""
机器人状态机控制器
事件驱动架构，无 GUI 依赖
"""

import asyncio
import signal
from enum import Enum, auto
from typing import Callable, Dict, Optional, Any
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger


class RobotState(Enum):
    """机器人状态枚举"""
    IDLE = auto()           # 待机状态（等待唤醒）
    LISTENING = auto()      # 监听状态（录音中）
    RECOGNIZING = auto()    # 识别状态（ASR处理中）
    THINKING = auto()       # 思考状态（Chat处理中）
    SPEAKING = auto()       # 说话状态（TTS播放中）
    ERROR = auto()          # 错误状态
    SHUTDOWN = auto()       # 关闭状态


class RobotEvent(Enum):
    """机器人事件枚举"""
    # 唤醒事件
    WAKE_WORD_DETECTED = auto()     # 检测到唤醒词
    BUTTON_PRESSED = auto()         # 按键触发

    # 录音事件
    RECORDING_STARTED = auto()      # 开始录音
    SILENCE_DETECTED = auto()       # 检测到静音
    RECORDING_TIMEOUT = auto()      # 录音超时
    RECORDING_STOPPED = auto()      # 录音停止

    # ASR 事件
    ASR_PARTIAL_RESULT = auto()     # ASR 部分结果
    ASR_FINAL_RESULT = auto()       # ASR 最终结果
    ASR_ERROR = auto()              # ASR 错误

    # Chat 事件
    CHAT_CHUNK_RECEIVED = auto()    # Chat 片段接收
    CHAT_COMPLETED = auto()         # Chat 完成
    CHAT_ERROR = auto()             # Chat 错误

    # TTS 事件
    TTS_STARTED = auto()            # TTS 开始播放
    TTS_COMPLETED = auto()          # TTS 播放完成
    TTS_INTERRUPTED = auto()        # TTS 被打断
    TTS_ERROR = auto()              # TTS 错误

    # 系统事件
    INTERRUPT_REQUESTED = auto()    # 请求打断
    SHUTDOWN_REQUESTED = auto()     # 请求关闭
    ERROR_OCCURRED = auto()         # 发生错误


@dataclass
class ConversationContext:
    """对话上下文"""
    user_id: Optional[str] = None           # 当前用户ID
    user_name: Optional[str] = None         # 当前用户名
    audio_buffer: bytes = field(default_factory=bytes)  # 录音缓冲
    recognized_text: str = ""               # 识别文本
    ai_response: str = ""                   # AI回复
    intent: Optional[str] = None            # 识别意图
    memory_context: str = ""                # 记忆上下文
    image_base64: Optional[str] = None      # 拍摄图片（Base64）


class RobotStateMachine:
    """
    机器人状态机

    使用异步事件驱动架构，替代 PyQt6 的信号槽机制
    """

    # 状态转换规则
    TRANSITIONS: Dict[RobotState, Dict[RobotEvent, RobotState]] = {
        RobotState.IDLE: {
            RobotEvent.WAKE_WORD_DETECTED: RobotState.LISTENING,
            RobotEvent.BUTTON_PRESSED: RobotState.LISTENING,
            RobotEvent.SHUTDOWN_REQUESTED: RobotState.SHUTDOWN,
        },
        RobotState.LISTENING: {
            RobotEvent.SILENCE_DETECTED: RobotState.RECOGNIZING,
            RobotEvent.RECORDING_TIMEOUT: RobotState.RECOGNIZING,
            RobotEvent.RECORDING_STOPPED: RobotState.RECOGNIZING,
            RobotEvent.INTERRUPT_REQUESTED: RobotState.IDLE,
            RobotEvent.ASR_ERROR: RobotState.ERROR,
        },
        RobotState.RECOGNIZING: {
            RobotEvent.ASR_FINAL_RESULT: RobotState.THINKING,
            RobotEvent.ASR_ERROR: RobotState.ERROR,
            RobotEvent.INTERRUPT_REQUESTED: RobotState.IDLE,
        },
        RobotState.THINKING: {
            RobotEvent.CHAT_CHUNK_RECEIVED: RobotState.SPEAKING,
            RobotEvent.CHAT_COMPLETED: RobotState.SPEAKING,
            RobotEvent.CHAT_ERROR: RobotState.ERROR,
            RobotEvent.INTERRUPT_REQUESTED: RobotState.IDLE,
        },
        RobotState.SPEAKING: {
            RobotEvent.TTS_COMPLETED: RobotState.IDLE,
            RobotEvent.TTS_INTERRUPTED: RobotState.IDLE,
            RobotEvent.TTS_ERROR: RobotState.ERROR,
            RobotEvent.INTERRUPT_REQUESTED: RobotState.IDLE,
            # 允许在说话时检测唤醒词来打断
            RobotEvent.WAKE_WORD_DETECTED: RobotState.LISTENING,
        },
        RobotState.ERROR: {
            RobotEvent.WAKE_WORD_DETECTED: RobotState.LISTENING,
            RobotEvent.BUTTON_PRESSED: RobotState.LISTENING,
            RobotEvent.SHUTDOWN_REQUESTED: RobotState.SHUTDOWN,
        },
    }

    def __init__(self):
        self.logger = get_logger()
        self._state = RobotState.IDLE
        self._context = ConversationContext()
        self._running = False

        # 事件队列
        self._event_queue: asyncio.Queue = None

        # 回调函数
        self._state_callbacks: Dict[RobotState, Callable] = {}
        self._event_callbacks: Dict[RobotEvent, Callable] = {}

        # 组件引用（稍后注入）
        self.audio_recorder = None
        self.audio_player = None
        self.asr_client = None
        self.chat_client = None
        self.tts_client = None
        self.wake_word_detector = None
        self.intent_handler = None
        self.mem0_client = None
        self.camera = None
        self.face_recognizer = None
        self.object_detector = None
        self.speaker_recognizer = None

    @property
    def state(self) -> RobotState:
        """当前状态"""
        return self._state

    @property
    def context(self) -> ConversationContext:
        """对话上下文"""
        return self._context

    def register_state_callback(
        self,
        state: RobotState,
        callback: Callable[[ConversationContext], Any]
    ):
        """注册状态进入回调"""
        self._state_callbacks[state] = callback

    def register_event_callback(
        self,
        event: RobotEvent,
        callback: Callable[[Any], Any]
    ):
        """注册事件处理回调"""
        self._event_callbacks[event] = callback

    async def emit_event(self, event: RobotEvent, data: Any = None):
        """发送事件到队列"""
        if self._event_queue:
            await self._event_queue.put((event, data))
            self.logger.debug(f"事件入队: {event.name}")

    def emit_event_sync(self, event: RobotEvent, data: Any = None):
        """同步发送事件（用于回调中）"""
        if self._event_queue:
            asyncio.create_task(self._event_queue.put((event, data)))

    async def _transition(self, event: RobotEvent, data: Any = None):
        """执行状态转换"""
        current_state = self._state
        transitions = self.TRANSITIONS.get(current_state, {})

        if event not in transitions:
            self.logger.warning(
                f"无效的状态转换: {current_state.name} + {event.name}"
            )
            return False

        new_state = transitions[event]
        self._state = new_state

        self.logger.info(
            f"状态转换: {current_state.name} -> {new_state.name} "
            f"(事件: {event.name})"
        )

        # 执行事件回调
        if event in self._event_callbacks:
            try:
                callback = self._event_callbacks[event]
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"事件回调执行失败: {e}")

        # 执行状态进入回调
        if new_state in self._state_callbacks:
            try:
                callback = self._state_callbacks[new_state]
                if asyncio.iscoroutinefunction(callback):
                    await callback(self._context)
                else:
                    callback(self._context)
            except Exception as e:
                self.logger.error(f"状态回调执行失败: {e}")

        return True

    async def _event_loop(self):
        """事件处理主循环"""
        self.logger.info("事件循环启动")

        while self._running and self._state != RobotState.SHUTDOWN:
            try:
                # 等待事件，超时1秒检查运行状态
                try:
                    event, data = await asyncio.wait_for(
                        self._event_queue.get(),
                        timeout=1.0
                    )
                    await self._transition(event, data)
                except asyncio.TimeoutError:
                    continue

            except Exception as e:
                self.logger.error(f"事件处理异常: {e}")
                await self.emit_event(RobotEvent.ERROR_OCCURRED, str(e))

        self.logger.info("事件循环结束")

    def reset_context(self):
        """重置对话上下文"""
        self._context = ConversationContext()

    async def start(self):
        """启动状态机"""
        self.logger.info("机器人状态机启动")
        self._running = True
        self._event_queue = asyncio.Queue()

        # 设置信号处理
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(
                        self.emit_event(RobotEvent.SHUTDOWN_REQUESTED)
                    )
                )
            except NotImplementedError:
                # Windows 不支持 add_signal_handler
                pass

        # 启动事件循环
        await self._event_loop()

    async def stop(self):
        """停止状态机"""
        self.logger.info("机器人状态机停止")
        self._running = False
        await self.emit_event(RobotEvent.SHUTDOWN_REQUESTED)

    def is_running(self) -> bool:
        """检查是否运行中"""
        return self._running and self._state != RobotState.SHUTDOWN
