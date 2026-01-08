#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
嵌入式陪伴机器人主程序
RK3568 平台，无 GUI，事件驱动架构

功能：
1. 语音唤醒或按键触发
2. 流式语音识别 (ASR)
3. 调用大模型对话 (Chat)
4. 流式语音合成并播放 (TTS)
5. 静音检测自动结束录音
"""

import asyncio
import signal
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    AUDIO_CONFIG,
    ASR_CONFIG,
    CHAT_CONFIG,
    TTS_CONFIG,
    MEM0_CONFIG,
    WAKE_WORD_CONFIG,
    SYSTEM_CONFIG,
    SYSTEM_PROMPT
)

from utils.logger import setup_logger, get_logger
from core.state_machine import (
    RobotStateMachine,
    RobotState,
    RobotEvent,
    ConversationContext
)
from core.audio_recorder import AudioRecorder, AudioConfig
from core.audio_player import AudioPlayer, PlaybackConfig
from core.wake_word import (
    WakeWordConfig,
    create_wake_word_detector,
    EnergyWakeWordDetector
)
from ai.asr_client import ASRClient, ASRConfig
from ai.chat_client import ChatClient, ChatConfig
from ai.tts_client import TTSClient, TTSConfig
from ai.mem0_client import Mem0Client, Mem0Config


class VoiceAssistantRobot:
    """
    语音助手机器人

    整合所有模块，实现完整的语音交互流程
    """

    def __init__(self):
        # 初始化日志
        self.logger = setup_logger(
            name="robot",
            level=SYSTEM_CONFIG["log_level"],
            log_file=SYSTEM_CONFIG.get("log_file")
        )
        self.logger.info("=" * 50)
        self.logger.info("嵌入式陪伴机器人启动")
        self.logger.info("=" * 50)

        # 初始化状态机
        self.state_machine = RobotStateMachine()

        # 初始化音频模块
        self.audio_recorder = AudioRecorder(AudioConfig(
            device=AUDIO_CONFIG["device"],
            sample_rate=AUDIO_CONFIG["sample_rate"],
            channels=AUDIO_CONFIG["channels"],
            chunk_size=AUDIO_CONFIG["chunk_size"]
        ))

        self.audio_player = AudioPlayer(PlaybackConfig(
            device=AUDIO_CONFIG["device"],
            sample_rate=TTS_CONFIG.get("sample_rate", 24000)
        ))

        # 初始化唤醒模块
        self.wake_detector = create_wake_word_detector(
            WakeWordConfig(
                engine=WAKE_WORD_CONFIG.get("engine", "energy"),
                audio_device=AUDIO_CONFIG["device"],
                sample_rate=AUDIO_CONFIG["sample_rate"]
            )
        )

        # 初始化 AI 服务
        self.asr_client = ASRClient(ASRConfig(
            ws_url=ASR_CONFIG["ws_url"],
            resource_id=ASR_CONFIG["resource_id"],
            appid=self._get_secret("ASR_APPID"),
            access_token=self._get_secret("ASR_ACCESS_TOKEN"),
            sample_rate=AUDIO_CONFIG["sample_rate"]
        ))

        self.chat_client = ChatClient(ChatConfig(
            api_url=CHAT_CONFIG["api_url"],
            api_key=self._get_secret("CHAT_API_KEY"),
            model_name=CHAT_CONFIG["model_name"],
            max_tokens=CHAT_CONFIG["max_tokens"],
            temperature=CHAT_CONFIG["temperature"]
        ))

        self.tts_client = TTSClient(TTSConfig(
            ws_url=TTS_CONFIG["ws_url"],
            resource_id=TTS_CONFIG["resource_id"],
            appid=self._get_secret("TTS_APPID"),
            access_token=self._get_secret("TTS_ACCESS_TOKEN"),
            speaker=TTS_CONFIG["speaker"],
            audio_format=TTS_CONFIG["audio_format"],
            sample_rate=TTS_CONFIG["sample_rate"]
        ))

        self.mem0_client = Mem0Client(Mem0Config(
            base_url=MEM0_CONFIG["base_url"],
            enabled=MEM0_CONFIG["enabled"]
        ))

        # 注册状态回调
        self._register_callbacks()

        # 运行标志
        self._running = False

    def _get_secret(self, key: str) -> str:
        """获取 API 密钥"""
        try:
            from api_secrets import (
                ASR_APPID, ASR_ACCESS_TOKEN,
                CHAT_API_KEY,
                TTS_APPID, TTS_ACCESS_TOKEN
            )
            secrets = {
                "ASR_APPID": ASR_APPID,
                "ASR_ACCESS_TOKEN": ASR_ACCESS_TOKEN,
                "CHAT_API_KEY": CHAT_API_KEY,
                "TTS_APPID": TTS_APPID,
                "TTS_ACCESS_TOKEN": TTS_ACCESS_TOKEN,
            }
            return secrets.get(key, "")
        except ImportError:
            self.logger.warning(f"api_secrets.py 未找到，请创建该文件")
            return os.environ.get(key, "")

    def _register_callbacks(self):
        """注册状态机回调"""
        # 状态进入回调
        self.state_machine.register_state_callback(
            RobotState.LISTENING,
            self._on_enter_listening
        )
        self.state_machine.register_state_callback(
            RobotState.RECOGNIZING,
            self._on_enter_recognizing
        )
        self.state_machine.register_state_callback(
            RobotState.THINKING,
            self._on_enter_thinking
        )
        self.state_machine.register_state_callback(
            RobotState.SPEAKING,
            self._on_enter_speaking
        )
        self.state_machine.register_state_callback(
            RobotState.IDLE,
            self._on_enter_idle
        )
        self.state_machine.register_state_callback(
            RobotState.ERROR,
            self._on_enter_error
        )

    async def _on_enter_listening(self, context: ConversationContext):
        """进入监听状态"""
        self.logger.info("开始录音...")
        context.audio_buffer = b""

        # 启动录音
        if await self.audio_recorder.start():
            # 收集音频数据
            async for chunk in self.audio_recorder.stream_audio(
                max_duration=SYSTEM_CONFIG["max_record_duration"]
            ):
                context.audio_buffer += chunk

            # 停止录音并发送识别事件
            await self.audio_recorder.stop()
            await self.state_machine.emit_event(RobotEvent.SILENCE_DETECTED)
        else:
            await self.state_machine.emit_event(
                RobotEvent.ASR_ERROR,
                "录音启动失败"
            )

    async def _on_enter_recognizing(self, context: ConversationContext):
        """进入识别状态"""
        self.logger.info("语音识别中...")

        if not context.audio_buffer:
            self.logger.warning("没有录音数据")
            await self.state_machine.emit_event(RobotEvent.ASR_ERROR, "没有录音数据")
            return

        # 创建音频生成器
        async def audio_generator():
            chunk_size = AUDIO_CONFIG["chunk_size"]
            data = context.audio_buffer
            for i in range(0, len(data), chunk_size):
                yield data[i:i+chunk_size]

        # 执行语音识别
        def on_partial(text):
            self.logger.info(f"[ASR] 识别中: {text}")

        def on_final(text):
            context.recognized_text = text
            self.logger.info(f"[ASR] 识别完成: {text}")

        self.asr_client.set_callbacks(on_partial=on_partial, on_final=on_final)

        try:
            text = await self.asr_client.recognize_stream(audio_generator())
            if text:
                context.recognized_text = text
                await self.state_machine.emit_event(
                    RobotEvent.ASR_FINAL_RESULT,
                    text
                )
            else:
                await self.state_machine.emit_event(
                    RobotEvent.ASR_ERROR,
                    "识别结果为空"
                )
        except Exception as e:
            self.logger.error(f"ASR 异常: {e}")
            await self.state_machine.emit_event(RobotEvent.ASR_ERROR, str(e))

    async def _on_enter_thinking(self, context: ConversationContext):
        """进入思考状态"""
        self.logger.info("AI 思考中...")

        user_input = context.recognized_text
        if not user_input:
            await self.state_machine.emit_event(RobotEvent.CHAT_ERROR, "输入为空")
            return

        # 搜索相关记忆
        memory_context = ""
        if self.mem0_client.config.enabled and context.user_id:
            memory_context = self.mem0_client.build_context(
                context.user_id,
                user_input
            )
            if memory_context:
                self.logger.info(f"注入记忆上下文: {len(memory_context)} 字符")

        # 调用对话模型
        def on_chunk(chunk):
            context.ai_response += chunk
            self.logger.debug(f"[Chat] {chunk}")

        self.chat_client.set_callbacks(on_chunk=on_chunk)

        try:
            response = self.chat_client.chat(
                user_input,
                system_prompt=SYSTEM_PROMPT,
                memory_context=memory_context
            )

            if response:
                context.ai_response = response
                self.logger.info(f"[Chat] 回复: {response[:50]}...")
                await self.state_machine.emit_event(
                    RobotEvent.CHAT_COMPLETED,
                    response
                )
            else:
                await self.state_machine.emit_event(
                    RobotEvent.CHAT_ERROR,
                    "对话模型无回复"
                )

        except Exception as e:
            self.logger.error(f"Chat 异常: {e}")
            await self.state_machine.emit_event(RobotEvent.CHAT_ERROR, str(e))

    async def _on_enter_speaking(self, context: ConversationContext):
        """进入说话状态"""
        self.logger.info("语音合成中...")

        text = context.ai_response
        if not text:
            await self.state_machine.emit_event(RobotEvent.TTS_ERROR, "没有回复文本")
            return

        try:
            # 合成语音
            audio_data = await self.tts_client.synthesize(text)

            if audio_data:
                self.logger.info(f"TTS 合成完成，播放音频...")

                # 播放音频
                audio_format = TTS_CONFIG.get("audio_format", "mp3")
                if audio_format == "mp3":
                    await self.audio_player.play_mp3(audio_data)
                else:
                    await self.audio_player.play_pcm(
                        audio_data,
                        sample_rate=TTS_CONFIG["sample_rate"]
                    )

                await self.state_machine.emit_event(RobotEvent.TTS_COMPLETED)
            else:
                await self.state_machine.emit_event(
                    RobotEvent.TTS_ERROR,
                    "语音合成失败"
                )

        except Exception as e:
            self.logger.error(f"TTS 异常: {e}")
            await self.state_machine.emit_event(RobotEvent.TTS_ERROR, str(e))

    async def _on_enter_idle(self, context: ConversationContext):
        """进入待机状态"""
        self.logger.info("待机中，等待唤醒...")

        # 存储记忆（如果有用户和对话内容）
        if (self.mem0_client.config.enabled and
            context.user_id and
            context.recognized_text and
            context.ai_response):
            try:
                self.mem0_client.add_memory(
                    context.user_id,
                    [
                        {"role": "user", "content": context.recognized_text},
                        {"role": "assistant", "content": context.ai_response}
                    ]
                )
            except Exception as e:
                self.logger.warning(f"存储记忆失败: {e}")

        # 重置上下文
        self.state_machine.reset_context()

    async def _on_enter_error(self, context: ConversationContext):
        """进入错误状态"""
        self.logger.error("发生错误，等待恢复...")
        await asyncio.sleep(2)
        # 自动恢复到待机状态
        self.state_machine._state = RobotState.IDLE
        await self._on_enter_idle(context)

    async def _wake_word_callback(self):
        """唤醒词检测回调"""
        self.logger.info("检测到唤醒信号！")
        await self.state_machine.emit_event(RobotEvent.WAKE_WORD_DETECTED)

    async def run(self):
        """运行主循环"""
        self._running = True

        # 设置信号处理
        def signal_handler(sig, frame):
            self.logger.info("收到退出信号")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self.logger.info("机器人启动完成，开始监听唤醒词...")

        # 设置唤醒回调
        def on_wake():
            asyncio.create_task(
                self.state_machine.emit_event(RobotEvent.WAKE_WORD_DETECTED)
            )

        self.wake_detector.set_on_wake(on_wake)

        # 启动唤醒检测
        wake_task = asyncio.create_task(self.wake_detector.start())

        # 启动状态机
        state_machine_task = asyncio.create_task(self.state_machine.start())

        try:
            # 等待任务
            await asyncio.gather(wake_task, state_machine_task)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        """关闭机器人"""
        self.logger.info("正在关闭机器人...")
        self._running = False

        # 停止各模块
        await self.wake_detector.stop()
        await self.audio_recorder.stop()
        await self.audio_player.stop()
        await self.state_machine.stop()

        self.logger.info("机器人已关闭")


async def main():
    """主函数"""
    robot = VoiceAssistantRobot()

    try:
        await robot.run()
    except KeyboardInterrupt:
        pass
    finally:
        await robot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
