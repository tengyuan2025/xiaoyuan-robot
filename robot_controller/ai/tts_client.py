# -*- coding: utf-8 -*-
"""
语音合成客户端 (TTS)
豆包语音合成模型2.0，WebSocket 流式
"""

import asyncio
import json
import uuid
from typing import Optional, Callable, AsyncGenerator
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

try:
    import websockets
except ImportError:
    websockets = None


@dataclass
class TTSConfig:
    """TTS 配置"""
    ws_url: str = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
    resource_id: str = "seed-tts-2.0"
    appid: str = ""
    access_token: str = ""
    speaker: str = "zh_female_xiaohe_uranus_bigtts"
    audio_format: str = "mp3"  # mp3, ogg_opus, pcm
    sample_rate: int = 24000
    speech_rate: float = 1.0
    loudness_rate: float = 1.0


class TTSClient:
    """
    语音合成客户端

    基于豆包 TTS 2.0 WebSocket 双向流协议

    协议流程：
    1. StartConnection -> ConnectionStarted
    2. StartSession -> SessionStarted
    3. TaskRequest -> TTSResponse (音频数据)
    4. FinishSession -> SessionFinished
    5. FinishConnection -> ConnectionFinished
    """

    # TTS 事件定义
    EVENT_START_CONNECTION = 1
    EVENT_FINISH_CONNECTION = 2
    EVENT_CONNECTION_STARTED = 50
    EVENT_CONNECTION_FAILED = 51
    EVENT_CONNECTION_FINISHED = 52
    EVENT_START_SESSION = 100
    EVENT_CANCEL_SESSION = 101
    EVENT_FINISH_SESSION = 102
    EVENT_SESSION_STARTED = 150
    EVENT_SESSION_CANCELED = 151
    EVENT_SESSION_FINISHED = 152
    EVENT_TASK_REQUEST = 200
    EVENT_TTS_RESPONSE = 250

    def __init__(self, config: TTSConfig):
        self.logger = get_logger()
        self.config = config
        self._websocket = None
        self._connected = False
        self._session_id = None

        # 回调函数
        self._on_audio_chunk: Optional[Callable[[bytes], None]] = None
        self._on_complete: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None

    def set_callbacks(
        self,
        on_audio_chunk: Callable[[bytes], None] = None,
        on_complete: Callable[[], None] = None,
        on_error: Callable[[str], None] = None
    ):
        """设置回调函数"""
        self._on_audio_chunk = on_audio_chunk
        self._on_complete = on_complete
        self._on_error = on_error

    def _build_request(self, event: int, payload: dict = None) -> str:
        """构建请求消息"""
        msg = {"event": event}
        if payload:
            msg.update(payload)
        return json.dumps(msg)

    def _get_audio_params(self) -> dict:
        """获取音频参数"""
        encoding_map = {
            "mp3": "mp3",
            "ogg_opus": "ogg_opus",
            "pcm": "pcm",
            "wav": "wav"
        }

        return {
            "encoding": encoding_map.get(self.config.audio_format, "mp3"),
            "sample_rate": self.config.sample_rate,
            "speech_rate": self.config.speech_rate,
            "loudness_rate": self.config.loudness_rate
        }

    async def synthesize(self, text: str) -> bytes:
        """
        合成语音

        Args:
            text: 要合成的文本

        Returns:
            音频数据
        """
        if websockets is None:
            raise ImportError("websockets 未安装，请运行: pip install websockets")

        if not text.strip():
            return b""

        audio_data = bytearray()

        # 构造请求头
        headers = {
            "X-Api-App-Key": self.config.appid,
            "X-Api-Access-Key": self.config.access_token,
            "X-Api-Resource-Id": self.config.resource_id,
        }

        try:
            async with websockets.connect(
                self.config.ws_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                self._websocket = websocket
                self._connected = True

                # 1. StartConnection
                await websocket.send(self._build_request(
                    self.EVENT_START_CONNECTION,
                    {}
                ))

                # 等待 ConnectionStarted
                response = await websocket.recv()
                res = json.loads(response)
                if res.get("event") != self.EVENT_CONNECTION_STARTED:
                    raise Exception(f"连接启动失败: {res}")

                self.logger.debug("TTS 连接已建立")

                # 2. StartSession
                self._session_id = str(uuid.uuid4())
                await websocket.send(self._build_request(
                    self.EVENT_START_SESSION,
                    {
                        "session_id": self._session_id,
                        "audio": self._get_audio_params(),
                        "speaker": self.config.speaker
                    }
                ))

                # 等待 SessionStarted
                response = await websocket.recv()
                res = json.loads(response)
                if res.get("event") != self.EVENT_SESSION_STARTED:
                    raise Exception(f"会话启动失败: {res}")

                self.logger.debug("TTS 会话已建立")

                # 3. TaskRequest
                await websocket.send(self._build_request(
                    self.EVENT_TASK_REQUEST,
                    {
                        "session_id": self._session_id,
                        "text": text
                    }
                ))

                # 4. 接收音频数据
                while True:
                    response = await websocket.recv()

                    if isinstance(response, bytes):
                        # 二进制音频数据
                        audio_data.extend(response)
                        if self._on_audio_chunk:
                            self._on_audio_chunk(response)
                    else:
                        res = json.loads(response)
                        event = res.get("event")

                        if event == self.EVENT_TTS_RESPONSE:
                            # 音频响应（可能包含 base64 编码的音频）
                            audio_b64 = res.get("audio")
                            if audio_b64:
                                import base64
                                chunk = base64.b64decode(audio_b64)
                                audio_data.extend(chunk)
                                if self._on_audio_chunk:
                                    self._on_audio_chunk(chunk)

                        elif event == self.EVENT_SESSION_FINISHED:
                            self.logger.debug("TTS 会话结束")
                            break

                        elif event in (self.EVENT_SESSION_CANCELED, self.EVENT_CONNECTION_FAILED):
                            error_msg = res.get("message", "TTS 会话失败")
                            self.logger.error(error_msg)
                            if self._on_error:
                                self._on_error(error_msg)
                            break

                # 5. FinishSession
                await websocket.send(self._build_request(
                    self.EVENT_FINISH_SESSION,
                    {"session_id": self._session_id}
                ))

                # 6. FinishConnection
                await websocket.send(self._build_request(
                    self.EVENT_FINISH_CONNECTION,
                    {}
                ))

                if self._on_complete:
                    self._on_complete()

                self.logger.info(f"TTS 合成完成，音频大小: {len(audio_data)} bytes")

        except websockets.exceptions.ConnectionClosed as e:
            error_msg = f"TTS 连接关闭: {e.code}"
            self.logger.error(error_msg)
            if self._on_error:
                self._on_error(error_msg)
        except Exception as e:
            error_msg = f"TTS 合成失败: {str(e)}"
            self.logger.error(error_msg)
            if self._on_error:
                self._on_error(error_msg)
        finally:
            self._connected = False
            self._websocket = None
            self._session_id = None

        return bytes(audio_data)

    async def synthesize_stream(
        self,
        text_generator: AsyncGenerator[str, None]
    ) -> AsyncGenerator[bytes, None]:
        """
        流式合成语音

        Args:
            text_generator: 异步文本生成器

        Yields:
            音频数据块
        """
        if websockets is None:
            raise ImportError("websockets 未安装，请运行: pip install websockets")

        headers = {
            "X-Api-App-Key": self.config.appid,
            "X-Api-Access-Key": self.config.access_token,
            "X-Api-Resource-Id": self.config.resource_id,
        }

        try:
            async with websockets.connect(
                self.config.ws_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                self._websocket = websocket
                self._connected = True

                # StartConnection
                await websocket.send(self._build_request(self.EVENT_START_CONNECTION, {}))
                response = await websocket.recv()
                res = json.loads(response)
                if res.get("event") != self.EVENT_CONNECTION_STARTED:
                    raise Exception(f"连接启动失败: {res}")

                # StartSession
                self._session_id = str(uuid.uuid4())
                await websocket.send(self._build_request(
                    self.EVENT_START_SESSION,
                    {
                        "session_id": self._session_id,
                        "audio": self._get_audio_params(),
                        "speaker": self.config.speaker
                    }
                ))

                response = await websocket.recv()
                res = json.loads(response)
                if res.get("event") != self.EVENT_SESSION_STARTED:
                    raise Exception(f"会话启动失败: {res}")

                # 流式发送文本并接收音频
                text_buffer = ""

                async for text_chunk in text_generator:
                    text_buffer += text_chunk

                    # 按句子分割发送
                    sentences = self._split_sentences(text_buffer)
                    for sentence in sentences[:-1]:
                        if sentence.strip():
                            await websocket.send(self._build_request(
                                self.EVENT_TASK_REQUEST,
                                {
                                    "session_id": self._session_id,
                                    "text": sentence
                                }
                            ))

                            # 接收音频
                            while True:
                                try:
                                    response = await asyncio.wait_for(
                                        websocket.recv(),
                                        timeout=0.1
                                    )
                                    if isinstance(response, bytes):
                                        yield response
                                    else:
                                        res = json.loads(response)
                                        if res.get("event") == self.EVENT_TTS_RESPONSE:
                                            audio_b64 = res.get("audio")
                                            if audio_b64:
                                                import base64
                                                yield base64.b64decode(audio_b64)
                                        elif res.get("event") == self.EVENT_SESSION_FINISHED:
                                            break
                                except asyncio.TimeoutError:
                                    break

                    text_buffer = sentences[-1] if sentences else ""

                # 发送剩余文本
                if text_buffer.strip():
                    await websocket.send(self._build_request(
                        self.EVENT_TASK_REQUEST,
                        {
                            "session_id": self._session_id,
                            "text": text_buffer
                        }
                    ))

                    while True:
                        try:
                            response = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=5.0
                            )
                            if isinstance(response, bytes):
                                yield response
                            else:
                                res = json.loads(response)
                                if res.get("event") == self.EVENT_TTS_RESPONSE:
                                    audio_b64 = res.get("audio")
                                    if audio_b64:
                                        import base64
                                        yield base64.b64decode(audio_b64)
                                elif res.get("event") == self.EVENT_SESSION_FINISHED:
                                    break
                        except asyncio.TimeoutError:
                            break

                # 结束会话
                await websocket.send(self._build_request(
                    self.EVENT_FINISH_SESSION,
                    {"session_id": self._session_id}
                ))
                await websocket.send(self._build_request(
                    self.EVENT_FINISH_CONNECTION,
                    {}
                ))

        except Exception as e:
            self.logger.error(f"TTS 流式合成失败: {e}")
            if self._on_error:
                self._on_error(str(e))
        finally:
            self._connected = False
            self._websocket = None

    def _split_sentences(self, text: str) -> list:
        """按句子分割文本"""
        import re
        # 中英文标点分割
        pattern = r'([。！？.!?])'
        parts = re.split(pattern, text)

        sentences = []
        current = ""
        for part in parts:
            current += part
            if part in '。！？.!?':
                sentences.append(current)
                current = ""

        if current:
            sentences.append(current)

        return sentences

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected

    async def close(self):
        """关闭连接"""
        if self._websocket:
            try:
                await self._websocket.close()
            except:
                pass
            self._websocket = None
        self._connected = False
