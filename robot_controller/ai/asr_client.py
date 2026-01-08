# -*- coding: utf-8 -*-
"""
语音识别客户端 (ASR)
豆包流式语音识别模型2.0，WebSocket 双向流
"""

import asyncio
import gzip
import json
import struct
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
class ASRConfig:
    """ASR 配置"""
    ws_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    resource_id: str = "volc.seedasr.sauc.duration"
    appid: str = ""
    access_token: str = ""
    sample_rate: int = 16000
    channels: int = 1
    enable_itn: bool = True
    enable_punc: bool = True
    show_utterances: bool = True


class ASRClient:
    """
    流式语音识别客户端

    基于豆包 ASR 2.0 WebSocket 协议
    """

    def __init__(self, config: ASRConfig):
        self.logger = get_logger()
        self.config = config
        self._websocket = None
        self._connected = False

        # 回调函数
        self._on_partial_result: Optional[Callable[[str], None]] = None
        self._on_final_result: Optional[Callable[[str], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None

    def set_callbacks(
        self,
        on_partial: Callable[[str], None] = None,
        on_final: Callable[[str], None] = None,
        on_error: Callable[[str], None] = None
    ):
        """设置回调函数"""
        self._on_partial_result = on_partial
        self._on_final_result = on_final
        self._on_error = on_error

    def _build_header(
        self,
        message_type: int,
        message_type_flags: int,
        serialization: int,
        compression: int
    ) -> bytes:
        """构建 ASR 二进制协议 header（4字节）"""
        byte0 = 0x11  # Protocol version + Header size
        byte1 = (message_type << 4) | message_type_flags
        byte2 = (serialization << 4) | compression
        byte3 = 0x00  # Reserved
        return bytes([byte0, byte1, byte2, byte3])

    def _build_full_client_request(self, payload: dict, use_gzip: bool = True) -> bytes:
        """构建 full client request 二进制包"""
        payload_bytes = json.dumps(payload).encode('utf-8')
        if use_gzip:
            payload_bytes = gzip.compress(payload_bytes)

        compression = 0b0001 if use_gzip else 0b0000
        header = self._build_header(0b0001, 0b0000, 0b0001, compression)
        payload_size = struct.pack('>I', len(payload_bytes))

        return header + payload_size + payload_bytes

    def _build_audio_request(
        self,
        audio_data: bytes,
        is_last: bool = False,
        use_gzip: bool = False
    ) -> bytes:
        """构建 audio only request 二进制包"""
        if use_gzip and audio_data:
            payload_bytes = gzip.compress(audio_data)
        else:
            payload_bytes = audio_data

        message_type_flags = 0b0010 if is_last else 0b0000
        compression = 0b0001 if use_gzip and audio_data else 0b0000
        header = self._build_header(0b0010, message_type_flags, 0b0000, compression)
        payload_size = struct.pack('>I', len(payload_bytes))

        return header + payload_size + payload_bytes

    def _parse_response(self, data: bytes) -> Optional[dict]:
        """解析 ASR 二进制响应"""
        if len(data) < 4:
            return None

        header = data[:4]
        message_type = (header[1] >> 4) & 0x0F
        message_type_flags = header[1] & 0x0F
        serialization = (header[2] >> 4) & 0x0F
        compression = header[2] & 0x0F

        offset = 4

        # 检查是否有 sequence number
        if message_type_flags in (0b0001, 0b0011):
            offset += 4

        # 错误消息
        if message_type == 0b1111:
            if len(data) < offset + 8:
                return {"error": True, "code": -1, "message": "Invalid error frame"}
            error_code = struct.unpack('>I', data[offset:offset+4])[0]
            error_size = struct.unpack('>I', data[offset+4:offset+8])[0]
            error_msg = data[offset+8:offset+8+error_size].decode('utf-8', errors='ignore')
            return {"error": True, "code": error_code, "message": error_msg}

        # 非 full server response
        if message_type != 0b1001:
            return None

        # 解析 payload
        if len(data) < offset + 4:
            return None

        payload_size = struct.unpack('>I', data[offset:offset+4])[0]
        offset += 4

        if len(data) < offset + payload_size:
            return None

        payload_bytes = data[offset:offset+payload_size]

        # 解压缩
        if compression == 0b0001:
            try:
                payload_bytes = gzip.decompress(payload_bytes)
            except:
                pass

        # 解析 JSON
        if serialization == 0b0001:
            try:
                return json.loads(payload_bytes.decode('utf-8'))
            except:
                return None

        return None

    async def recognize_stream(
        self,
        audio_generator: AsyncGenerator[bytes, None]
    ) -> str:
        """
        流式语音识别

        Args:
            audio_generator: 异步音频数据生成器

        Returns:
            识别的最终文本
        """
        if websockets is None:
            raise ImportError("websockets 未安装，请运行: pip install websockets")

        final_text = ""

        # 构造请求头
        connect_id = str(uuid.uuid4())
        headers = {
            "X-Api-App-Key": self.config.appid,
            "X-Api-Access-Key": self.config.access_token,
            "X-Api-Resource-Id": self.config.resource_id,
            "X-Api-Connect-Id": connect_id
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

                # 发送初始化参数
                init_params = {
                    "user": {"uid": str(uuid.uuid4())[:16]},
                    "audio": {
                        "format": "pcm",
                        "rate": self.config.sample_rate,
                        "bits": 16,
                        "channel": self.config.channels
                    },
                    "request": {
                        "model_name": "bigmodel",
                        "enable_itn": self.config.enable_itn,
                        "enable_punc": self.config.enable_punc,
                        "show_utterances": self.config.show_utterances,
                        "result_type": "full",
                        "enable_accelerate_text": True,
                        "accelerate_score": 20,
                        "end_window_size": 800,
                        "force_to_speech_time": 300
                    }
                }

                request_packet = self._build_full_client_request(init_params)
                await websocket.send(request_packet)

                # 并行发送和接收
                send_task = asyncio.create_task(
                    self._send_audio(websocket, audio_generator)
                )
                recv_task = asyncio.create_task(
                    self._recv_result(websocket)
                )

                # 等待接收任务完成获取结果
                results = await asyncio.gather(send_task, recv_task, return_exceptions=True)

                # 获取识别结果
                if isinstance(results[1], str):
                    final_text = results[1]

        except websockets.exceptions.ConnectionClosed as e:
            error_msg = f"WebSocket 连接关闭: {e.code}"
            self.logger.error(error_msg)
            if self._on_error:
                self._on_error(error_msg)
        except Exception as e:
            error_msg = f"语音识别连接失败: {str(e)}"
            self.logger.error(error_msg)
            if self._on_error:
                self._on_error(error_msg)
        finally:
            self._connected = False
            self._websocket = None

        return final_text

    async def _send_audio(
        self,
        websocket,
        audio_generator: AsyncGenerator[bytes, None]
    ):
        """发送音频帧"""
        frame_count = 0

        try:
            async for audio_data in audio_generator:
                if audio_data:
                    audio_packet = self._build_audio_request(
                        audio_data, is_last=False, use_gzip=False
                    )
                    await websocket.send(audio_packet)
                    frame_count += 1

            # 发送结束帧
            end_packet = self._build_audio_request(b"", is_last=True, use_gzip=False)
            await websocket.send(end_packet)
            self.logger.debug(f"ASR 发送完成，共 {frame_count} 帧")

        except Exception as e:
            self.logger.error(f"ASR 发送音频异常: {e}")

    async def _recv_result(self, websocket) -> str:
        """接收并处理识别结果"""
        final_text = ""

        try:
            while True:
                try:
                    response = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                if isinstance(response, bytes):
                    res = self._parse_response(response)
                    if res is None:
                        continue

                    # 检查错误
                    if res.get("error"):
                        error_msg = res.get("message", "未知错误")
                        self.logger.error(f"ASR 识别错误: {error_msg}")
                        if self._on_error:
                            self._on_error(error_msg)
                        break

                    # 解析识别结果
                    result = res.get("result", {})
                    text = result.get("text", "")
                    utterances = result.get("utterances", [])
                    is_finished = False

                    if utterances:
                        full_text = "".join(utt.get("text", "") for utt in utterances)
                        if full_text:
                            text = full_text
                        for utt in utterances:
                            if utt.get("definite", False):
                                is_finished = True

                    if text and text != final_text:
                        final_text = text
                        if self._on_partial_result:
                            self._on_partial_result(text)

                    # 检查是否为最后一包
                    if len(response) >= 4:
                        message_type_flags = response[1] & 0x0F
                        if message_type_flags in (0b0010, 0b0011):
                            is_finished = True

                    if is_finished:
                        self.logger.info(f"ASR 识别完成: {final_text}")
                        if self._on_final_result:
                            self._on_final_result(final_text)
                        break

        except Exception as e:
            self.logger.error(f"ASR 接收结果异常: {e}")

        return final_text

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
