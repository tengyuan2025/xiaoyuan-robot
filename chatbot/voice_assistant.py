# -*- coding: utf-8 -*-
"""
豆包语音助手 Demo - 主程序

功能：
1. PyQt6 图形界面，包含麦克风按钮和对话显示区域
2. 语音录制与流式语音识别（豆包流式语音识别模型2.0）
3. 文本对话（Doubao-Seed-1.6）
4. 语音合成与播放（豆包语音合成模型2.0）

作者：Claude Code
日期：2024
"""

import sys
import os
import json
import asyncio
import threading
import queue
import tempfile
import uuid
import struct
import gzip
from typing import Optional, List, Dict

# PyQt6 图形界面
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon

# 网络请求
import requests
import websockets

# 音频处理
import pyaudio
import pygame

# 导入配置
from config import (
    # 语音识别配置
    ASR_APPID, ASR_ACCESS_TOKEN, ASR_WS_URL, ASR_RESOURCE_ID,
    AUDIO_FORMAT, AUDIO_CHANNELS, AUDIO_RATE, AUDIO_CHUNK,
    SILENCE_THRESHOLD, SILENCE_TIMEOUT, FINAL_WAIT_TIMEOUT,
    # 对话模型配置
    CHAT_API_KEY, CHAT_API_URL, CHAT_MODEL_NAME,
    CHAT_MAX_TOKENS, CHAT_TEMPERATURE, CHAT_REASONING_EFFORT,
    # 语音合成配置
    TTS_APPID, TTS_ACCESS_TOKEN, TTS_WS_URL, TTS_RESOURCE_ID,
    TTS_SPEAKER, TTS_FORMAT, TTS_SAMPLE_RATE, TTS_SPEECH_RATE, TTS_LOUDNESS_RATE,
    # 界面配置
    WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, TEMP_AUDIO_PATH,
    # 网络配置
    REQUEST_TIMEOUT, MAX_RETRIES
)


# ==================== 信号类（用于线程间通信） ====================
class WorkerSignals(QObject):
    """工作线程信号类，用于子线程与主线程（UI）通信"""

    # 语音识别相关信号
    asr_text_update = pyqtSignal(str)       # 实时识别文本更新
    asr_finished = pyqtSignal(str)          # 识别完成，传递最终文本
    asr_error = pyqtSignal(str)             # 识别错误

    # 对话模型相关信号
    chat_thinking = pyqtSignal()            # AI 正在思考
    chat_reply = pyqtSignal(str)            # AI 回复完成
    chat_error = pyqtSignal(str)            # 对话错误

    # 语音合成相关信号
    tts_started = pyqtSignal()              # TTS 开始播放
    tts_finished = pyqtSignal()             # TTS 播放完成
    tts_error = pyqtSignal(str)             # TTS 错误

    # 录音状态信号
    recording_started = pyqtSignal()        # 录音开始
    recording_stopped = pyqtSignal()        # 录音停止


# ==================== 语音录制与识别模块 ====================
class AudioRecorder:
    """
    音频录制器
    负责从麦克风采集 PCM 音频数据
    """

    def __init__(self):
        self.p: Optional[pyaudio.PyAudio] = None
        self.stream = None
        self.is_recording = False
        self.audio_queue = queue.Queue()

    def list_devices(self):
        """列出所有可用的音频输入设备"""
        p = pyaudio.PyAudio()
        print("\n[AudioRecorder] 可用的音频输入设备:")
        print("-" * 60)
        input_devices = []
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev['maxInputChannels'] > 0:  # 只显示输入设备
                input_devices.append(i)
                default_mark = " [默认]" if i == p.get_default_input_device_info()['index'] else ""
                print(f"  设备 {i}: {dev['name']}{default_mark}")
                print(f"          输入通道: {dev['maxInputChannels']}, 采样率: {dev['defaultSampleRate']}")
        print("-" * 60)
        p.terminate()
        return input_devices

    def start(self, device_index: int = None) -> bool:
        """
        开始录音

        Args:
            device_index: 指定的音频输入设备索引，None 表示使用默认设备

        Returns:
            bool: 是否成功开始录音
        """
        try:
            self.p = pyaudio.PyAudio()

            # 列出设备信息
            self.list_devices()

            # 获取默认设备信息
            if device_index is None:
                default_dev = self.p.get_default_input_device_info()
                device_index = default_dev['index']
                print(f"[AudioRecorder] 使用默认设备: {device_index} - {default_dev['name']}")
            else:
                dev = self.p.get_device_info_by_index(device_index)
                print(f"[AudioRecorder] 使用指定设备: {device_index} - {dev['name']}")

            self.stream = self.p.open(
                format=pyaudio.paInt16,     # 16-bit 采样
                channels=AUDIO_CHANNELS,     # 单声道
                rate=AUDIO_RATE,             # 16kHz 采样率
                input=True,                  # 输入模式
                input_device_index=device_index,  # 指定输入设备
                frames_per_buffer=AUDIO_CHUNK  # 每帧 320 样本 (20ms)
            )
            self.is_recording = True
            return True
        except Exception as e:
            print(f"[AudioRecorder] 录音启动失败: {e}")
            import traceback
            traceback.print_exc()
            self.cleanup()
            return False

    def read_chunk(self) -> Optional[bytes]:
        """
        读取一帧音频数据

        Returns:
            bytes: 音频数据，如果未在录音则返回 None
        """
        if not self.is_recording or self.stream is None:
            return None
        try:
            data = self.stream.read(AUDIO_CHUNK, exception_on_overflow=False)
            return data
        except Exception as e:
            print(f"[AudioRecorder] 读取音频失败: {e}")
            return None

    def stop(self):
        """停止录音"""
        self.is_recording = False
        self.cleanup()

    def cleanup(self):
        """清理资源"""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
            self.stream = None
        if self.p:
            try:
                self.p.terminate()
            except:
                pass
            self.p = None


class ASRWorker(QThread):
    """
    流式语音识别工作线程

    负责：
    1. 录制音频
    2. 通过 WebSocket 发送音频帧
    3. 接收并处理识别结果
    """

    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self.signals = signals
        self.recorder = AudioRecorder()
        self.is_running = False
        self.final_text = ""

    def run(self):
        """线程主函数"""
        self.is_running = True
        self.final_text = ""

        # 启动录音
        if not self.recorder.start():
            self.signals.asr_error.emit("麦克风启动失败，请检查设备连接")
            return

        self.signals.recording_started.emit()

        # 运行异步事件循环
        try:
            asyncio.run(self._stream_asr())
        except Exception as e:
            self.signals.asr_error.emit(f"语音识别异常: {str(e)}")
        finally:
            self.recorder.stop()
            self.signals.recording_stopped.emit()

    def _build_header(self, message_type: int, message_type_flags: int,
                       serialization: int, compression: int) -> bytes:
        """
        构建 ASR 二进制协议 header（4字节）

        Args:
            message_type: 消息类型 (4 bits)
            message_type_flags: 消息类型标志 (4 bits)
            serialization: 序列化方法 (4 bits)
            compression: 压缩方法 (4 bits)

        Returns:
            4字节 header
        """
        # Byte 0: Protocol version (0b0001) + Header size (0b0001)
        byte0 = 0x11
        # Byte 1: Message type + Message type specific flags
        byte1 = (message_type << 4) | message_type_flags
        # Byte 2: Serialization method + Compression
        byte2 = (serialization << 4) | compression
        # Byte 3: Reserved
        byte3 = 0x00
        return bytes([byte0, byte1, byte2, byte3])

    def _build_full_client_request(self, payload: dict, use_gzip: bool = True) -> bytes:
        """
        构建 full client request 二进制包

        Args:
            payload: JSON 请求参数
            use_gzip: 是否使用 gzip 压缩

        Returns:
            完整的二进制请求包
        """
        payload_bytes = json.dumps(payload).encode('utf-8')
        if use_gzip:
            payload_bytes = gzip.compress(payload_bytes)

        # message_type=0b0001 (Full client request)
        # message_type_flags=0b0000 (无 sequence number)
        # serialization=0b0001 (JSON)
        # compression=0b0001 (Gzip) 或 0b0000 (无压缩)
        compression = 0b0001 if use_gzip else 0b0000
        header = self._build_header(0b0001, 0b0000, 0b0001, compression)

        # Payload size (4 bytes, big-endian)
        payload_size = struct.pack('>I', len(payload_bytes))

        return header + payload_size + payload_bytes

    def _build_audio_request(self, audio_data: bytes, is_last: bool = False,
                             use_gzip: bool = True) -> bytes:
        """
        构建 audio only request 二进制包

        Args:
            audio_data: 音频数据
            is_last: 是否为最后一包
            use_gzip: 是否使用 gzip 压缩

        Returns:
            完整的二进制请求包
        """
        if use_gzip and audio_data:
            payload_bytes = gzip.compress(audio_data)
        else:
            payload_bytes = audio_data

        # message_type=0b0010 (Audio only request)
        # message_type_flags: 0b0000 (正常包) 或 0b0010 (最后一包)
        message_type_flags = 0b0010 if is_last else 0b0000
        # serialization=0b0000 (Raw)
        # compression=0b0001 (Gzip) 或 0b0000 (无压缩)
        compression = 0b0001 if use_gzip and audio_data else 0b0000
        header = self._build_header(0b0010, message_type_flags, 0b0000, compression)

        # Payload size (4 bytes, big-endian)
        payload_size = struct.pack('>I', len(payload_bytes))

        return header + payload_size + payload_bytes

    def _parse_response(self, data: bytes) -> Optional[dict]:
        """
        解析 ASR 二进制响应

        Args:
            data: 二进制响应数据

        Returns:
            解析后的 JSON 对象，失败返回 None
        """
        if len(data) < 4:
            return None

        # 解析 header
        header = data[:4]
        message_type = (header[1] >> 4) & 0x0F
        message_type_flags = header[1] & 0x0F
        serialization = (header[2] >> 4) & 0x0F
        compression = header[2] & 0x0F

        offset = 4

        # 检查是否有 sequence number
        if message_type_flags in (0b0001, 0b0011):
            offset += 4  # 跳过 sequence number

        # 检查消息类型
        if message_type == 0b1111:
            # 错误消息
            if len(data) < offset + 8:
                return {"error": True, "code": -1, "message": "Invalid error frame"}
            error_code = struct.unpack('>I', data[offset:offset+4])[0]
            error_size = struct.unpack('>I', data[offset+4:offset+8])[0]
            error_msg = data[offset+8:offset+8+error_size].decode('utf-8', errors='ignore')
            return {"error": True, "code": error_code, "message": error_msg}

        if message_type != 0b1001:
            # 非 full server response
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

    async def _stream_asr(self):
        """
        流式语音识别主逻辑

        流程：
        1. 建立 WebSocket 连接（使用正确的 HTTP Header 鉴权）
        2. 发送初始化参数（二进制协议）
        3. 并行发送音频帧和接收识别结果
        """
        try:
            # 构造正确的请求头（根据完整文档）
            connect_id = str(uuid.uuid4())
            headers = {
                "X-Api-App-Key": ASR_APPID,
                "X-Api-Access-Key": ASR_ACCESS_TOKEN,
                "X-Api-Resource-Id": ASR_RESOURCE_ID,
                "X-Api-Connect-Id": connect_id
            }

            async with websockets.connect(
                ASR_WS_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:

                # 构造初始化参数
                init_params = {
                    "user": {
                        "uid": str(uuid.uuid4())[:16]
                    },
                    "audio": {
                        "format": "pcm",
                        "rate": AUDIO_RATE,
                        "bits": 16,
                        "channel": AUDIO_CHANNELS
                    },
                    "request": {
                        "model_name": "bigmodel",
                        "enable_itn": True,
                        "enable_punc": True,
                        "show_utterances": True,  # 启用分句信息
                        "result_type": "full",
                        "enable_accelerate_text": True,  # 加速首字返回
                        "accelerate_score": 15,  # 加速率 0-20，越大越快
                        "end_window_size": 1500,  # 服务端静音判停时间(ms)，默认800，增大避免过早截断
                        "force_to_speech_time": 500  # 强制语音时间(ms)，音频超过此时长后才判停
                    }
                }

                # 发送 full client request（二进制协议）
                request_packet = self._build_full_client_request(init_params)
                await websocket.send(request_packet)

                # 并行任务：发送音频 + 接收结果
                send_task = asyncio.create_task(self._send_audio(websocket))
                recv_task = asyncio.create_task(self._recv_result(websocket))

                # 等待任务完成
                await asyncio.gather(send_task, recv_task, return_exceptions=True)

        except websockets.exceptions.ConnectionClosed as e:
            self.signals.asr_error.emit(f"WebSocket 连接关闭: {e.code}")
        except Exception as e:
            self.signals.asr_error.emit(f"语音识别连接失败: {str(e)}")
        finally:
            # 发送识别完成信号
            self.signals.asr_finished.emit(self.final_text)

    async def _send_audio(self, websocket):
        """
        发送音频帧到服务器（使用二进制协议）

        Args:
            websocket: WebSocket 连接对象
        """
        import time
        import array

        frame_count = 0
        all_audio_data = b""  # 收集所有音频数据用于调试
        max_amplitude = 0
        total_amplitude = 0

        # 静音检测相关
        last_voice_time = time.time()  # 最后检测到声音的时间
        has_detected_voice = False  # 是否已检测到过声音

        try:
            while self.is_running:
                # 读取音频帧
                audio_data = self.recorder.read_chunk()
                if audio_data:
                    # 收集音频数据用于调试
                    all_audio_data += audio_data

                    # 计算音频振幅（检测是否有有效声音）
                    samples = array.array('h', audio_data)  # 16-bit signed samples
                    frame_max = max(abs(s) for s in samples) if samples else 0
                    frame_avg = sum(abs(s) for s in samples) // len(samples) if samples else 0
                    max_amplitude = max(max_amplitude, frame_max)
                    total_amplitude += frame_avg

                    # 静音检测：检查是否有声音
                    if frame_max > SILENCE_THRESHOLD:
                        last_voice_time = time.time()
                        has_detected_voice = True

                    # 静音超时检测：只有在检测到声音后才开始计时
                    if has_detected_voice:
                        silence_duration = time.time() - last_voice_time
                        if silence_duration >= SILENCE_TIMEOUT:
                            print(f"[ASR] 静音超时 {SILENCE_TIMEOUT}秒，自动结束录音")
                            self.is_running = False
                            break

                    # 构建音频请求包（不使用压缩，直接发送原始音频）
                    audio_packet = self._build_audio_request(audio_data, is_last=False, use_gzip=False)
                    await websocket.send(audio_packet)
                    frame_count += 1
                else:
                    await asyncio.sleep(0.01)

            # 发送结束帧（最后一包）
            end_packet = self._build_audio_request(b"", is_last=True, use_gzip=False)
            await websocket.send(end_packet)

            # 打印音频统计信息
            avg_amplitude = total_amplitude // frame_count if frame_count > 0 else 0
            print(f"[ASR] 共发送 {frame_count} 帧音频")
            print(f"[ASR] 音频统计: 最大振幅={max_amplitude}, 平均振幅={avg_amplitude}")
            print(f"[ASR] 总音频大小: {len(all_audio_data)} 字节, 时长约 {len(all_audio_data) / 32000:.2f} 秒")

            # 判断音频是否有效
            if max_amplitude < 500:
                print(f"[ASR] 警告: 音频振幅很低，可能麦克风没有声音或静音！")
            elif max_amplitude < 2000:
                print(f"[ASR] 提示: 音频振幅较低，说话声音可能较小")
            else:
                print(f"[ASR] 音频振幅正常")

            # 保存音频文件用于调试
            debug_audio_path = os.path.join(os.path.dirname(__file__), "debug_audio.pcm")
            with open(debug_audio_path, "wb") as f:
                f.write(all_audio_data)
            print(f"[ASR] 已保存调试音频到: {debug_audio_path}")
            print(f"[ASR] 可使用 ffplay -f s16le -ar 16000 -ac 1 {debug_audio_path} 播放")

        except Exception as e:
            print(f"[ASR] 发送音频异常: {e}")

    async def _recv_result(self, websocket):
        """
        接收并处理识别结果（解析二进制协议响应）

        Args:
            websocket: WebSocket 连接对象
        """
        import time
        wait_start_time = None  # 开始等待最终结果的时间

        try:
            # 持续接收直到识别完成或超时
            while True:
                try:
                    # 设置超时，避免阻塞
                    response = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=0.5  # 缩短超时，提高响应速度
                    )
                    wait_start_time = None  # 收到数据，重置等待时间
                except asyncio.TimeoutError:
                    # 如果录音已停止，开始计时等待最终结果
                    if not self.is_running:
                        if wait_start_time is None:
                            wait_start_time = time.time()
                        elif time.time() - wait_start_time > FINAL_WAIT_TIMEOUT:
                            print(f"[ASR] 等待最终结果超时，退出")
                            break
                    continue

                # 打印原始响应用于调试
                if isinstance(response, bytes):
                    print(f"[ASR] 收到二进制响应: {len(response)} 字节, header: {response[:4].hex() if len(response) >= 4 else 'N/A'}")
                else:
                    print(f"[ASR] 收到文本响应: {response[:200] if len(response) > 200 else response}")

                # 处理二进制响应
                if isinstance(response, bytes):
                    res = self._parse_response(response)
                    if res is None:
                        print(f"[ASR] 解析响应失败")
                        continue

                    print(f"[ASR] 解析结果: {res}")

                    # 检查是否有错误
                    if res.get("error"):
                        error_msg = res.get("message", "未知错误")
                        error_code = res.get("code", -1)
                        print(f"[ASR] 识别错误: {error_code} - {error_msg}")
                        self.signals.asr_error.emit(f"识别错误: {error_msg}")
                        break

                    # 解析识别结果（根据完整文档的响应格式）
                    result = res.get("result", {})
                    text = result.get("text", "")

                    # 检查是否识别完成（通过 utterances 的 definite 字段）
                    utterances = result.get("utterances", [])
                    is_finished = False

                    # 如果有 utterances，尝试从中提取完整文本
                    if utterances:
                        # 合并所有 utterance 的文本
                        full_text = "".join(utt.get("text", "") for utt in utterances)
                        if full_text:
                            text = full_text
                        # 检查是否有 definite 标记
                        for utt in utterances:
                            if utt.get("definite", False):
                                is_finished = True

                    # 更新文本（无论是否完成都要更新）
                    if text and text != self.final_text:
                        self.final_text = text
                        self.signals.asr_text_update.emit(text)
                        print(f"[ASR] 识别文本: {text}")

                    # 检查 message_type_flags 是否为最后一包（通过 header 解析）
                    if len(response) >= 4:
                        message_type_flags = response[1] & 0x0F
                        if message_type_flags in (0b0010, 0b0011):
                            is_finished = True
                            print(f"[ASR] 收到最后一包标志")

                    if is_finished:
                        print(f"[ASR] 识别完成: {self.final_text}")
                        break

                elif isinstance(response, str):
                    # 兼容可能的文本响应
                    try:
                        res = json.loads(response)
                        print(f"[ASR] JSON 响应: {res}")
                        if res.get("code") == 0 or res.get("result"):
                            result = res.get("result", res.get("data", {}))
                            text = result.get("text", "")
                            if text:
                                self.final_text = text
                                self.signals.asr_text_update.emit(text)
                        else:
                            error_msg = res.get("msg", res.get("message", "未知错误"))
                            print(f"[ASR] 识别错误: {res.get('code')} - {error_msg}")
                    except json.JSONDecodeError:
                        pass

        except Exception as e:
            print(f"[ASR] 接收结果异常: {e}")
            import traceback
            traceback.print_exc()

    def stop(self):
        """停止识别"""
        self.is_running = False
        self.recorder.stop()


# ==================== 文本对话模块 ====================
class ChatWorker(QThread):
    """
    文本对话工作线程

    负责调用 Doubao-Seed-1.6 模型进行对话
    """

    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self.signals = signals
        self.user_input = ""
        self.history: List[Dict[str, str]] = []

    def set_input(self, text: str, history: List[Dict[str, str]] = None):
        """
        设置用户输入和对话历史

        Args:
            text: 用户输入文本
            history: 对话历史（可选）
        """
        self.user_input = text
        self.history = history or []

    def run(self):
        """线程主函数"""
        if not self.user_input.strip():
            self.signals.chat_error.emit("输入文本为空")
            return

        # 发送"正在思考"信号
        self.signals.chat_thinking.emit()

        # 调用对话模型
        reply = self._call_chat_api()

        if reply:
            self.signals.chat_reply.emit(reply)
        else:
            self.signals.chat_error.emit("对话模型调用失败")

    def _call_chat_api(self) -> Optional[str]:
        """
        调用 Doubao-Seed-1.6 对话 API

        Returns:
            str: AI 回复文本，失败返回 None
        """
        headers = {
            "Authorization": f"Bearer {CHAT_API_KEY}",
            "Content-Type": "application/json"
        }

        # 构造请求体
        messages = self.history + [{"role": "user", "content": self.user_input}]
        data = {
            "model": CHAT_MODEL_NAME,
            "messages": messages,
            "reasoning_effort": CHAT_REASONING_EFFORT,
            "max_completion_tokens": CHAT_MAX_TOKENS,
            "temperature": CHAT_TEMPERATURE
        }

        # 重试机制
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    CHAT_API_URL,
                    headers=headers,
                    data=json.dumps(data),
                    timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()

                res_json = response.json()

                # 检查响应格式（兼容 OpenAI 格式）
                if "choices" in res_json:
                    # OpenAI 兼容格式
                    reply = res_json["choices"][0]["message"]["content"]
                    return reply
                elif res_json.get("code") == 0:
                    # 豆包原生格式
                    reply = res_json["data"]["choices"][0]["message"]["content"]
                    return reply
                else:
                    error_msg = res_json.get("msg", res_json.get("error", {}).get("message", "未知错误"))
                    print(f"[Chat] 对话错误: {res_json.get('code', 'N/A')} - {error_msg}")

            except requests.exceptions.Timeout:
                print(f"[Chat] 请求超时，重试 {attempt + 1}/{MAX_RETRIES}")
            except requests.exceptions.RequestException as e:
                print(f"[Chat] 请求异常: {e}")
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                print(f"[Chat] 解析响应失败: {e}")
                break

        return None


# ==================== 语音合成与播放模块 ====================
class TTSWorker(QThread):
    """
    语音合成工作线程（使用 WebSocket 双向流式接口）

    负责：
    1. 通过 WebSocket 调用豆包 TTS 双向流式 API 合成语音
    2. 播放合成的音频

    协议流程：
    1. StartConnection → ConnectionStarted
    2. StartSession → SessionStarted
    3. TaskRequest → TTSResponse (音频数据)
    4. FinishSession → SessionFinished
    5. FinishConnection → ConnectionFinished
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
    EVENT_SESSION_FAILED = 153
    EVENT_TASK_REQUEST = 200
    EVENT_TTS_SENTENCE_START = 350
    EVENT_TTS_SENTENCE_END = 351
    EVENT_TTS_RESPONSE = 352

    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self.signals = signals
        self.text = ""
        self.audio_path = TEMP_AUDIO_PATH
        self.session_id = ""
        self.audio_data = b""
        self.is_running = True  # 用于控制播放中断

    def stop(self):
        """停止 TTS 播放"""
        self.is_running = False
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except:
            pass

    def set_text(self, text: str):
        """
        设置待合成文本

        Args:
            text: 待合成的文本
        """
        self.text = text

    def run(self):
        """线程主函数"""
        if not self.text.strip():
            self.signals.tts_error.emit("合成文本为空")
            return

        # 通过 WebSocket 合成语音
        try:
            asyncio.run(self._stream_tts())
        except Exception as e:
            self.signals.tts_error.emit(f"语音合成异常: {str(e)}")
            return

        if self.audio_data:
            # 保存音频文件
            try:
                with open(self.audio_path, "wb") as f:
                    f.write(self.audio_data)

                # 播放音频
                self.signals.tts_started.emit()
                self._play_audio()
                self.signals.tts_finished.emit()

            except Exception as e:
                self.signals.tts_error.emit(f"音频保存/播放失败: {e}")
        else:
            self.signals.tts_error.emit("语音合成失败")

    def _build_tts_header(self, message_type: int, message_type_flags: int,
                          serialization: int, compression: int) -> bytes:
        """
        构建 TTS 二进制协议 header（4字节）
        """
        byte0 = 0x11  # Protocol version (0b0001) + Header size (0b0001)
        byte1 = (message_type << 4) | message_type_flags
        byte2 = (serialization << 4) | compression
        byte3 = 0x00  # Reserved
        return bytes([byte0, byte1, byte2, byte3])

    def _build_event_request(self, event: int, session_id: str = "",
                             payload: dict = None) -> bytes:
        """
        构建带事件的请求包

        Args:
            event: 事件类型
            session_id: 会话 ID（仅 Session 类事件需要）
            payload: JSON 负载

        Returns:
            完整的二进制请求包
        """
        # message_type=0b0001 (Full client request)
        # message_type_flags=0b0100 (with event number)
        # serialization=0b0001 (JSON)
        # compression=0b0000 (无压缩)
        header = self._build_tts_header(0b0001, 0b0100, 0b0001, 0b0000)

        # Event number (4 bytes, big-endian)
        event_bytes = struct.pack('>I', event)

        result = header + event_bytes

        # Session ID（仅 Session 类事件需要）
        if event in (self.EVENT_START_SESSION, self.EVENT_FINISH_SESSION,
                     self.EVENT_CANCEL_SESSION, self.EVENT_TASK_REQUEST):
            session_id_bytes = session_id.encode('utf-8')
            session_id_size = struct.pack('>I', len(session_id_bytes))
            result += session_id_size + session_id_bytes

        # Payload
        if payload is None:
            payload = {}
        payload_bytes = json.dumps(payload).encode('utf-8')
        payload_size = struct.pack('>I', len(payload_bytes))
        result += payload_size + payload_bytes

        return result

    def _parse_tts_response(self, data: bytes) -> dict:
        """
        解析 TTS 二进制响应

        Args:
            data: 二进制响应数据

        Returns:
            解析后的响应对象
        """
        if len(data) < 4:
            return {"error": True, "message": "响应数据过短"}

        # 解析 header
        header = data[:4]
        message_type = (header[1] >> 4) & 0x0F
        message_type_flags = header[1] & 0x0F
        serialization = (header[2] >> 4) & 0x0F
        compression = header[2] & 0x0F

        offset = 4

        # 检查错误帧
        if message_type == 0b1111:
            if len(data) < offset + 4:
                return {"error": True, "message": "错误帧格式无效"}
            error_code = struct.unpack('>I', data[offset:offset+4])[0]
            offset += 4
            if len(data) >= offset + 4:
                payload_size = struct.unpack('>I', data[offset:offset+4])[0]
                offset += 4
                if len(data) >= offset + payload_size:
                    try:
                        error_payload = json.loads(data[offset:offset+payload_size].decode('utf-8'))
                        return {"error": True, "code": error_code, "payload": error_payload}
                    except:
                        pass
            return {"error": True, "code": error_code}

        result = {"message_type": message_type, "flags": message_type_flags}

        # 解析事件号（如果有）
        if message_type_flags == 0b0100:
            if len(data) < offset + 4:
                return {"error": True, "message": "缺少事件号"}
            event = struct.unpack('>I', data[offset:offset+4])[0]
            result["event"] = event
            offset += 4

        # 音频响应 (Audio-only response)
        if message_type == 0b1011:
            # 解析 session_id
            if len(data) >= offset + 4:
                session_id_size = struct.unpack('>I', data[offset:offset+4])[0]
                offset += 4
                if len(data) >= offset + session_id_size:
                    result["session_id"] = data[offset:offset+session_id_size].decode('utf-8')
                    offset += session_id_size

            # 解析音频数据
            if len(data) >= offset + 4:
                audio_size = struct.unpack('>I', data[offset:offset+4])[0]
                offset += 4
                if len(data) >= offset + audio_size:
                    result["audio"] = data[offset:offset+audio_size]
            return result

        # Full server response
        if message_type == 0b1001:
            # Session 类事件需要解析 session_id
            event = result.get("event", 0)
            if event in (self.EVENT_SESSION_STARTED, self.EVENT_SESSION_FINISHED,
                         self.EVENT_SESSION_FAILED, self.EVENT_SESSION_CANCELED,
                         self.EVENT_TTS_SENTENCE_START, self.EVENT_TTS_SENTENCE_END):
                if len(data) >= offset + 4:
                    session_id_size = struct.unpack('>I', data[offset:offset+4])[0]
                    offset += 4
                    if len(data) >= offset + session_id_size:
                        result["session_id"] = data[offset:offset+session_id_size].decode('utf-8')
                        offset += session_id_size

            # Connection 类事件需要解析 connection_id
            elif event in (self.EVENT_CONNECTION_STARTED, self.EVENT_CONNECTION_FAILED,
                           self.EVENT_CONNECTION_FINISHED):
                if len(data) >= offset + 4:
                    conn_id_size = struct.unpack('>I', data[offset:offset+4])[0]
                    offset += 4
                    if len(data) >= offset + conn_id_size:
                        result["connection_id"] = data[offset:offset+conn_id_size].decode('utf-8')
                        offset += conn_id_size

            # 解析 payload
            if len(data) >= offset + 4:
                payload_size = struct.unpack('>I', data[offset:offset+4])[0]
                offset += 4
                if len(data) >= offset + payload_size:
                    payload_bytes = data[offset:offset+payload_size]
                    if compression == 0b0001:
                        try:
                            payload_bytes = gzip.decompress(payload_bytes)
                        except:
                            pass
                    try:
                        result["payload"] = json.loads(payload_bytes.decode('utf-8'))
                    except:
                        result["payload"] = {}

        return result

    async def _stream_tts(self):
        """
        WebSocket 双向流式 TTS 主逻辑
        """
        try:
            # 构造请求头
            connect_id = str(uuid.uuid4())
            headers = {
                "X-Api-App-Key": TTS_APPID,
                "X-Api-Access-Key": TTS_ACCESS_TOKEN,
                "X-Api-Resource-Id": TTS_RESOURCE_ID,
                "X-Api-Connect-Id": connect_id
            }

            async with websockets.connect(
                TTS_WS_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:

                # 1. 发送 StartConnection
                start_conn_packet = self._build_event_request(self.EVENT_START_CONNECTION)
                await websocket.send(start_conn_packet)

                # 等待 ConnectionStarted
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                res = self._parse_tts_response(response)
                if res.get("error") or res.get("event") != self.EVENT_CONNECTION_STARTED:
                    raise Exception(f"连接失败: {res}")
                print("[TTS] 连接已建立")

                # 2. 发送 StartSession
                self.session_id = str(uuid.uuid4())
                session_params = {
                    "user": {"uid": str(uuid.uuid4())[:16]},
                    "event": self.EVENT_START_SESSION,
                    "namespace": "BidirectionalTTS",
                    "req_params": {
                        "text": "",  # 文本在 TaskRequest 中发送
                        "speaker": TTS_SPEAKER,
                        "audio_params": {
                            "format": TTS_FORMAT,
                            "sample_rate": TTS_SAMPLE_RATE,
                            "speech_rate": TTS_SPEECH_RATE,
                            "loudness_rate": TTS_LOUDNESS_RATE
                        }
                    }
                }
                start_session_packet = self._build_event_request(
                    self.EVENT_START_SESSION, self.session_id, session_params
                )
                await websocket.send(start_session_packet)

                # 等待 SessionStarted
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                res = self._parse_tts_response(response)
                if res.get("error") or res.get("event") != self.EVENT_SESSION_STARTED:
                    raise Exception(f"会话启动失败: {res}")
                print("[TTS] 会话已开始")

                # 3. 发送 TaskRequest（包含文本）
                task_params = {
                    "event": self.EVENT_TASK_REQUEST,
                    "req_params": {
                        "text": self.text
                    }
                }
                task_packet = self._build_event_request(
                    self.EVENT_TASK_REQUEST, self.session_id, task_params
                )
                await websocket.send(task_packet)

                # 4. 发送 FinishSession
                finish_session_packet = self._build_event_request(
                    self.EVENT_FINISH_SESSION, self.session_id
                )
                await websocket.send(finish_session_packet)

                # 5. 接收音频数据直到 SessionFinished
                self.audio_data = b""
                while True:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=30)
                        res = self._parse_tts_response(response)

                        if res.get("error"):
                            print(f"[TTS] 错误: {res}")
                            break

                        event = res.get("event", 0)

                        # 接收音频数据
                        if event == self.EVENT_TTS_RESPONSE or res.get("audio"):
                            audio_chunk = res.get("audio", b"")
                            if audio_chunk:
                                self.audio_data += audio_chunk

                        # 会话结束
                        elif event == self.EVENT_SESSION_FINISHED:
                            print(f"[TTS] 会话结束，共收到 {len(self.audio_data)} 字节音频")
                            break

                        elif event == self.EVENT_SESSION_FAILED:
                            raise Exception(f"会话失败: {res.get('payload', {})}")

                    except asyncio.TimeoutError:
                        print("[TTS] 接收超时")
                        break

                # 6. 发送 FinishConnection
                finish_conn_packet = self._build_event_request(self.EVENT_FINISH_CONNECTION)
                await websocket.send(finish_conn_packet)

        except websockets.exceptions.ConnectionClosed as e:
            raise Exception(f"WebSocket 连接关闭: {e.code}")
        except Exception as e:
            raise Exception(f"TTS 错误: {str(e)}")

    def _play_audio(self):
        """播放音频文件"""
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(self.audio_path)
            pygame.mixer.music.play()

            # 等待播放完成，检查是否被中断
            while pygame.mixer.music.get_busy() and self.is_running:
                pygame.time.Clock().tick(10)

            # 如果被中断，停止播放
            if not self.is_running:
                pygame.mixer.music.stop()
                print("[TTS] 播放被打断")

            pygame.mixer.quit()

        except Exception as e:
            print(f"[TTS] 播放音频失败: {e}")
            raise


# ==================== 主界面 ====================
class VoiceAssistantWindow(QMainWindow):
    """
    语音助手主窗口

    界面布局：
    - 顶部：标题
    - 中间：对话显示区域（用户输入 + AI 回复）
    - 底部：麦克风按钮 + 状态显示
    """

    def __init__(self):
        super().__init__()

        # 初始化信号
        self.signals = WorkerSignals()
        self._connect_signals()

        # 初始化工作线程（延迟创建）
        self.asr_worker: Optional[ASRWorker] = None
        self.chat_worker: Optional[ChatWorker] = None
        self.tts_worker: Optional[TTSWorker] = None

        # 对话历史
        self.chat_history: List[Dict[str, str]] = []

        # 当前状态
        self.is_recording = False
        self.is_tts_playing = False  # TTS 是否正在播放
        self.current_asr_text = ""

        # 初始化界面
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # 主容器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # ========== 标题区域 ==========
        title_label = QLabel("豆包语音助手")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333; padding: 10px;")
        main_layout.addWidget(title_label)

        # ========== 对话显示区域 ==========
        # 用户输入显示
        user_frame = QFrame()
        user_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
        """)
        user_layout = QVBoxLayout(user_frame)

        user_title = QLabel("您说:")
        user_title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        user_title.setStyleSheet("color: #666; border: none;")
        user_layout.addWidget(user_title)

        self.user_text = QTextEdit()
        self.user_text.setReadOnly(True)
        self.user_text.setFont(QFont("Microsoft YaHei", 12))
        self.user_text.setMinimumHeight(80)
        self.user_text.setMaximumHeight(120)
        self.user_text.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #333;
            }
        """)
        user_layout.addWidget(self.user_text)

        main_layout.addWidget(user_frame)

        # AI 回复显示
        ai_frame = QFrame()
        ai_frame.setStyleSheet("""
            QFrame {
                background-color: #e8f4fd;
                border: 1px solid #b8d4e8;
                border-radius: 8px;
            }
        """)
        ai_layout = QVBoxLayout(ai_frame)

        ai_title = QLabel("AI 回复:")
        ai_title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        ai_title.setStyleSheet("color: #1976d2; border: none;")
        ai_layout.addWidget(ai_title)

        self.ai_text = QTextEdit()
        self.ai_text.setReadOnly(True)
        self.ai_text.setFont(QFont("Microsoft YaHei", 12))
        self.ai_text.setMinimumHeight(150)
        self.ai_text.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #333;
            }
        """)
        ai_layout.addWidget(self.ai_text)

        main_layout.addWidget(ai_frame, 1)

        # ========== 底部控制区域 ==========
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(10)

        # 状态显示
        self.status_label = QLabel("点击麦克风按钮开始对话")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Microsoft YaHei", 10))
        self.status_label.setStyleSheet("color: #666;")
        bottom_layout.addWidget(self.status_label)

        # 麦克风按钮
        button_container = QHBoxLayout()
        button_container.addStretch()

        self.mic_button = QPushButton("🎤 点击说话")
        self.mic_button.setFixedSize(150, 60)
        self.mic_button.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.mic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_button_style_normal()
        self.mic_button.clicked.connect(self._on_mic_button_clicked)

        button_container.addWidget(self.mic_button)
        button_container.addStretch()
        bottom_layout.addLayout(button_container)

        main_layout.addLayout(bottom_layout)

    def _set_button_style_normal(self):
        """设置按钮正常状态样式"""
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 30px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)

    def _set_button_style_recording(self):
        """设置按钮录音中状态样式"""
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 30px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)

    def _set_button_style_disabled(self):
        """设置按钮禁用状态样式"""
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: #cccccc;
                color: #666666;
                border: none;
                border-radius: 30px;
            }
        """)

    def _set_button_style_interrupt(self):
        """设置按钮打断状态样式（橙色）"""
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 30px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
        """)

    def _connect_signals(self):
        """连接信号与槽"""
        # 语音识别信号
        self.signals.asr_text_update.connect(self._on_asr_text_update)
        self.signals.asr_finished.connect(self._on_asr_finished)
        self.signals.asr_error.connect(self._on_asr_error)

        # 录音状态信号
        self.signals.recording_started.connect(self._on_recording_started)
        self.signals.recording_stopped.connect(self._on_recording_stopped)

        # 对话模型信号
        self.signals.chat_thinking.connect(self._on_chat_thinking)
        self.signals.chat_reply.connect(self._on_chat_reply)
        self.signals.chat_error.connect(self._on_chat_error)

        # 语音合成信号
        self.signals.tts_started.connect(self._on_tts_started)
        self.signals.tts_finished.connect(self._on_tts_finished)
        self.signals.tts_error.connect(self._on_tts_error)

    def _on_mic_button_clicked(self):
        """麦克风按钮点击事件"""
        if self.is_tts_playing:
            # 打断 TTS 播放，开始新的录音
            self._interrupt_tts()
        elif self.is_recording:
            # 停止录音
            self._stop_recording()
        else:
            # 开始录音
            self._start_recording()

    def _interrupt_tts(self):
        """打断 TTS 播放"""
        print("[UI] 打断 TTS 播放")
        self.is_tts_playing = False

        # 停止 pygame 播放
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception as e:
            print(f"[UI] 停止播放异常: {e}")

        # 停止 TTS 工作线程
        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.stop()

        # 立即开始新的录音
        self._start_recording()

    def _start_recording(self):
        """开始录音"""
        self.is_recording = True
        self.current_asr_text = ""

        # 清空显示
        self.user_text.clear()
        self.ai_text.clear()

        # 更新 UI
        self.mic_button.setText("🔴 正在录音...")
        self._set_button_style_recording()
        self.status_label.setText("正在录音，请说话...")

        # 启动 ASR 工作线程
        self.asr_worker = ASRWorker(self.signals)
        self.asr_worker.start()

    def _stop_recording(self):
        """停止录音"""
        self.is_recording = False

        if self.asr_worker and self.asr_worker.isRunning():
            self.asr_worker.stop()
            # 不要等待，让线程自然结束

        self.status_label.setText("正在处理语音...")

    def _on_recording_started(self):
        """录音开始回调"""
        print("[UI] 录音已开始")
        self.status_label.setText(f"正在聆听...（静音{SILENCE_TIMEOUT}秒后自动结束）")

    def _on_recording_stopped(self):
        """录音停止回调"""
        print("[UI] 录音已停止")
        self.status_label.setText("正在识别...")
        self.mic_button.setText("🎤 处理中...")
        self.mic_button.setEnabled(False)

    def _on_asr_text_update(self, text: str):
        """实时识别文本更新"""
        if text and text != self.current_asr_text:
            self.current_asr_text = text
            self.user_text.setText(text)
            self.status_label.setText(f"识别中: {text[:20]}..." if len(text) > 20 else f"识别中: {text}")
            # 强制刷新 UI，确保实时显示
            self.user_text.repaint()
            self.status_label.repaint()
            QApplication.processEvents()

    def _on_asr_finished(self, final_text: str):
        """语音识别完成"""
        self.current_asr_text = final_text
        self.user_text.setText(final_text)

        # 更新按钮状态
        self.mic_button.setText("🎤 点击说话")
        self._set_button_style_disabled()
        self.mic_button.setEnabled(False)

        if final_text.strip():
            # 调用对话模型
            self._call_chat(final_text)
        else:
            self.status_label.setText("未识别到有效语音，请重试")
            self._reset_button()

    def _on_asr_error(self, error: str):
        """语音识别错误"""
        self.status_label.setText(f"识别错误: {error}")
        self.ai_text.setText(f"语音识别失败: {error}")
        self._reset_button()

    def _call_chat(self, user_input: str):
        """调用对话模型"""
        self.chat_worker = ChatWorker(self.signals)
        self.chat_worker.set_input(user_input, self.chat_history)
        self.chat_worker.start()

    def _on_chat_thinking(self):
        """AI 正在思考"""
        self.status_label.setText("AI 正在思考...")
        self.ai_text.setText("AI 正在思考...")

    def _on_chat_reply(self, reply: str):
        """AI 回复完成"""
        self.ai_text.setText(reply)

        # 更新对话历史
        self.chat_history.append({"role": "user", "content": self.current_asr_text})
        self.chat_history.append({"role": "assistant", "content": reply})

        # 限制历史长度（保留最近 10 轮对话）
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]

        # 调用 TTS
        self._call_tts(reply)

    def _on_chat_error(self, error: str):
        """对话模型错误"""
        self.status_label.setText(f"对话错误: {error}")
        self.ai_text.setText(f"对话失败: {error}")
        self._reset_button()

    def _call_tts(self, text: str):
        """调用语音合成"""
        self.status_label.setText("正在合成语音...")

        self.tts_worker = TTSWorker(self.signals)
        self.tts_worker.set_text(text)
        self.tts_worker.start()

    def _on_tts_started(self):
        """TTS 开始播放"""
        self.is_tts_playing = True
        self.status_label.setText("正在播放语音...（点击打断）")
        # 启用按钮，允许打断
        self.mic_button.setText("⏹️ 点击打断")
        self.mic_button.setEnabled(True)
        self._set_button_style_interrupt()

    def _on_tts_finished(self):
        """TTS 播放完成"""
        self.is_tts_playing = False
        self.status_label.setText("对话完成，点击麦克风继续")
        self._reset_button()

    def _on_tts_error(self, error: str):
        """TTS 错误"""
        self.is_tts_playing = False
        self.status_label.setText(f"语音合成错误: {error}")
        self._reset_button()

    def _reset_button(self):
        """重置按钮状态"""
        self.is_recording = False
        self.is_tts_playing = False
        self.mic_button.setText("🎤 点击说话")
        self._set_button_style_normal()
        self.mic_button.setEnabled(True)

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止所有工作线程
        if self.asr_worker and self.asr_worker.isRunning():
            self.asr_worker.stop()
            self.asr_worker.wait(1000)

        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.wait(1000)

        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.wait(1000)

        # 清理临时文件
        if os.path.exists(TEMP_AUDIO_PATH):
            try:
                os.remove(TEMP_AUDIO_PATH)
            except:
                pass

        event.accept()


# ==================== 主函数 ====================
def main():
    """程序入口"""
    # 检查配置
    if ASR_APPID == "your_appid" or ASR_ACCESS_TOKEN == "your_access_token":
        print("警告: 请在 config.py 中配置 ASR_APPID 和 ASR_ACCESS_TOKEN")
    if CHAT_API_KEY == "your_api_key":
        print("警告: 请在 config.py 中配置 CHAT_API_KEY")
    if TTS_APPID == "your_appid" or TTS_ACCESS_TOKEN == "your_access_token":
        print("警告: 请在 config.py 中配置 TTS_APPID 和 TTS_ACCESS_TOKEN")

    # 创建应用
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle("Fusion")

    # 创建主窗口
    window = VoiceAssistantWindow()
    window.show()

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
