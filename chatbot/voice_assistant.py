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
import time
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
    CHAT_MAX_TOKENS, CHAT_TEMPERATURE, CHAT_STREAM, CHAT_THINKING,
    # Base64图文分析配置
    IMAGE_ANALYSIS_STREAM, IMAGE_ANALYSIS_MAX_TOKENS, IMAGE_ANALYSIS_TEMPERATURE,
    IMAGE_MAX_WIDTH, IMAGE_MAX_HEIGHT, IMAGE_QUALITY,
    TEMP_IMAGE_PATH, IMAGE_ANALYSIS_PROMPT_TEMPLATE,
    # 人脸识别配置
    FACE_ENCODINGS_PATH, FACE_RECOGNITION_TOLERANCE, FACE_RECOGNITION_MODEL,
    FACE_RECOGNITION_PROMPT_TEMPLATE,
    # YOLO 物体检测配置
    YOLO_MODEL_NAME, YOLO_CONFIDENCE_THRESHOLD, YOLO_USE_CHINESE,
    # 声纹识别配置
    VOICEPRINT_DATA_PATH, SPEAKER_SIMILARITY_THRESHOLD, SPEAKER_MIN_AUDIO_DURATION,
    # 语音合成配置
    TTS_APPID, TTS_ACCESS_TOKEN, TTS_WS_URL, TTS_RESOURCE_ID,
    TTS_SPEAKER, TTS_FORMAT, TTS_SAMPLE_RATE, TTS_SPEECH_RATE, TTS_LOUDNESS_RATE,
    # 界面配置
    WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, TEMP_AUDIO_PATH,
    # 网络配置
    REQUEST_TIMEOUT, MAX_RETRIES
)

# 导入意图判断和摄像头模块
from intent_handler import IntentHandler, IntentResult, IntentType
from camera_utils import capture_and_encode, delete_temp_image, image_to_base64

# 导入人脸识别模块
from face_recognition_utils import FaceRecognitionManager, check_face_recognition_available

# 导入物体检测模块
from object_detection_utils import ObjectDetector, check_yolo_available

# 导入声纹识别模块
from speaker_recognition_utils import SpeakerRecognitionManager, check_resemblyzer_available


# ==================== 信号类（用于线程间通信） ====================
class WorkerSignals(QObject):
    """工作线程信号类，用于子线程与主线程（UI）通信"""

    # 语音识别相关信号
    asr_text_update = pyqtSignal(str)       # 实时识别文本更新
    asr_finished = pyqtSignal(str)          # 识别完成，传递最终文本
    asr_audio_data = pyqtSignal(bytes)      # 原始音频数据（用于声纹识别）
    asr_error = pyqtSignal(str)             # 识别错误

    # 对话模型相关信号
    chat_thinking = pyqtSignal()            # AI 正在思考
    chat_chunk = pyqtSignal(str)            # AI 流式回复片段
    chat_reply = pyqtSignal(str)            # AI 回复完成（完整文本）
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
    负责从麦克风采集 PCM 音频数据，支持缓冲区存储
    """

    def __init__(self):
        self.p: Optional[pyaudio.PyAudio] = None
        self.stream = None
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.audio_buffer: List[bytes] = []  # 音频缓冲区，用于存储连接建立前的音频

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
            self.audio_buffer = []  # 清空缓冲区

            # 获取默认设备信息
            if device_index is None:
                default_dev = self.p.get_default_input_device_info()
                device_index = default_dev['index']

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

    def read_chunk_to_buffer(self) -> Optional[bytes]:
        """
        读取一帧音频数据并存入缓冲区

        Returns:
            bytes: 音频数据，如果未在录音则返回 None
        """
        data = self.read_chunk()
        if data:
            self.audio_buffer.append(data)
        return data

    def get_buffered_audio(self) -> List[bytes]:
        """
        获取并清空缓冲区中的音频数据

        Returns:
            List[bytes]: 缓冲区中的音频帧列表
        """
        buffered = self.audio_buffer
        self.audio_buffer = []
        return buffered

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
        self.audio_chunks: List[bytes] = []  # 缓存原始音频用于声纹识别

    def run(self):
        """线程主函数"""
        self.is_running = True
        self.final_text = ""
        self.audio_chunks = []  # 清空音频缓存
        self.ws_ready = False  # WebSocket 连接是否就绪

        # 先启动录音，不等待连接
        if not self.recorder.start():
            self.signals.asr_error.emit("麦克风启动失败，请检查设备连接")
            return

        self.signals.recording_started.emit()

        # 启动后台线程持续采集音频到缓冲区（在连接建立前）
        def buffer_audio():
            while self.is_running and not self.ws_ready:
                self.recorder.read_chunk_to_buffer()
                time.sleep(0.01)  # 避免CPU占用过高

        buffer_thread = threading.Thread(target=buffer_audio, daemon=True)
        buffer_thread.start()

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
        3. 发送缓冲区中的音频（在连接建立前已录制的）
        4. 并行发送音频帧和接收识别结果
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
                        "accelerate_score": 20,  # 加速率 0-20，越大越快（最大加速）
                        "end_window_size": 800,  # 服务端静音判停时间(ms)，默认800
                        "force_to_speech_time": 300  # 强制语音时间(ms)，音频超过此时长后才判停
                    }
                }

                # 发送 full client request（二进制协议）
                request_packet = self._build_full_client_request(init_params)
                await websocket.send(request_packet)

                # 标记连接就绪，停止缓冲线程
                self.ws_ready = True

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
            # 发送原始音频数据信号（用于声纹识别）
            if self.audio_chunks:
                all_audio = b''.join(self.audio_chunks)
                self.signals.asr_audio_data.emit(all_audio)
                print(f"[ASR] 发送音频数据用于声纹识别: {len(all_audio)} 字节")

            # 发送识别完成信号
            self.signals.asr_finished.emit(self.final_text)

    async def _send_audio(self, websocket):
        """
        发送音频帧到服务器（使用二进制协议）

        Args:
            websocket: WebSocket 连接对象
        """
        import array

        frame_count = 0
        max_amplitude = 0

        # 静音检测相关
        last_voice_time = time.time()  # 最后检测到声音的时间
        has_detected_voice = False  # 是否已检测到过声音

        try:
            # 先发送缓冲区中的音频（在连接建立前已录制的）
            buffered_frames = self.recorder.get_buffered_audio()
            if buffered_frames:
                print(f"[ASR] 发送缓冲区中的 {len(buffered_frames)} 帧音频")
                for audio_data in buffered_frames:
                    self.audio_chunks.append(audio_data)  # 缓存音频用于声纹识别
                    audio_packet = self._build_audio_request(audio_data, is_last=False, use_gzip=False)
                    await websocket.send(audio_packet)
                    frame_count += 1

                    # 检测缓冲区音频中是否有声音
                    samples = array.array('h', audio_data)
                    frame_max = max(abs(s) for s in samples) if samples else 0
                    max_amplitude = max(max_amplitude, frame_max)
                    if frame_max > SILENCE_THRESHOLD:
                        last_voice_time = time.time()
                        has_detected_voice = True

            # 继续发送实时录制的音频
            while self.is_running:
                audio_data = self.recorder.read_chunk()
                if audio_data:
                    self.audio_chunks.append(audio_data)  # 缓存音频用于声纹识别

                    # 计算音频振幅（检测是否有有效声音）
                    samples = array.array('h', audio_data)
                    frame_max = max(abs(s) for s in samples) if samples else 0
                    max_amplitude = max(max_amplitude, frame_max)

                    # 静音检测：检查是否有声音
                    if frame_max > SILENCE_THRESHOLD:
                        last_voice_time = time.time()
                        has_detected_voice = True

                    # 静音超时检测：只有在检测到声音后才开始计时
                    if has_detected_voice:
                        silence_duration = time.time() - last_voice_time
                        if silence_duration >= SILENCE_TIMEOUT:
                            print(f"[ASR] 静音 {SILENCE_TIMEOUT}秒，自动结束")
                            self.is_running = False
                            break

                    # 构建音频请求包
                    audio_packet = self._build_audio_request(audio_data, is_last=False, use_gzip=False)
                    await websocket.send(audio_packet)
                    frame_count += 1
                else:
                    await asyncio.sleep(0.01)

            # 发送结束帧
            end_packet = self._build_audio_request(b"", is_last=True, use_gzip=False)
            await websocket.send(end_packet)
            print(f"[ASR] 共发送 {frame_count} 帧，最大振幅 {max_amplitude}")

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


# ==================== 文本对话模块（支持Base64图文分析） ====================  # MODIFIED
class ChatWorker(QThread):
    """
    文本对话工作线程

    负责调用 Doubao-Seed-1.6 模型进行对话
    支持两种模式：
    1. 纯文本模式：流式调用，实时返回文本片段
    2. 图文分析模式：非流式调用，通过Base64编码+提示词模板传递图片
    """

    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self.signals = signals
        self.user_input = ""
        self.image_base64: Optional[str] = None  # Base64编码的图片
        self.image_path: Optional[str] = None    # 临时图片路径（用于清理）
        self.history: List[Dict[str, str]] = []
        self.is_running = True
        self.use_image_analysis_mode = False     # 强制使用非流式模式

    def set_input(self, text: str, history: List[Dict[str, str]] = None,
                  image_base64: Optional[str] = None,
                  image_path: Optional[str] = None,
                  use_image_analysis_mode: bool = False):
        """
        设置用户输入和对话历史

        Args:
            text: 用户输入文本
            history: 对话历史（可选）
            image_base64: 图片的Base64编码（可选，用于图文分析）
            image_path: 临时图片路径（可选，用于清理）
            use_image_analysis_mode: 强制使用非流式图文分析模式（用于提示词中已包含图片的情况）
        """
        self.user_input = text
        self.history = history or []
        self.image_base64 = image_base64
        self.image_path = image_path
        self.use_image_analysis_mode = use_image_analysis_mode

    def stop(self):
        """停止对话"""
        self.is_running = False

    def run(self):
        """线程主函数"""
        if not self.user_input.strip():
            self.signals.chat_error.emit("输入文本为空")
            return

        self.is_running = True

        # 发送"正在思考"信号
        self.signals.chat_thinking.emit()

        # 判断是否为图文分析模式
        if self.image_base64 or self.use_image_analysis_mode:
            # 图文分析模式：非流式调用
            full_reply = self._call_chat_api_with_image()
        else:
            # 纯文本模式：流式调用
            full_reply = self._call_chat_api_stream()

        if full_reply:
            self.signals.chat_reply.emit(full_reply)
        elif self.is_running:
            self.signals.chat_error.emit("对话模型调用失败")

        # 清理临时图片  # MODIFIED
        if self.image_path:
            delete_temp_image(self.image_path)
            self.image_path = None

    def _build_image_analysis_prompt(self, user_question: str, image_base64: str) -> str:  # NEW
        """
        构建图文分析提示词

        使用配置的模板，将用户问题和Base64图片编码嵌入其中

        Args:
            user_question: 用户的问题
            image_base64: 图片的Base64编码（带格式头）

        Returns:
            完整的提示词
        """
        return IMAGE_ANALYSIS_PROMPT_TEMPLATE.format(
            user_question=user_question,
            image_base64=image_base64
        )

    def _call_chat_api_with_image(self) -> Optional[str]:  # NEW
        """
        图文分析模式：非流式调用 Doubao-Seed-1.6

        通过Base64编码+提示词模板传递图片

        Returns:
            str: AI 完整回复文本，失败返回 None
        """
        headers = {
            "Authorization": f"Bearer {CHAT_API_KEY}",
            "Content-Type": "application/json"
        }

        # 构建提示词
        if self.image_base64:
            # 标准图文分析模式：使用模板构建提示词
            prompt = self._build_image_analysis_prompt(self.user_input, self.image_base64)
        else:
            # 自定义提示词模式：提示词中已包含图片（如人脸识别场景）
            prompt = self.user_input
        print(f"[Chat] 图文分析模式，提示词长度: {len(prompt)} 字符")

        # 图文分析不使用历史记录（避免上下文过长）
        messages = [{"role": "user", "content": prompt}]

        data = {
            "model": CHAT_MODEL_NAME,
            "messages": messages,
            "max_completion_tokens": IMAGE_ANALYSIS_MAX_TOKENS,
            "temperature": IMAGE_ANALYSIS_TEMPERATURE,
            "stream": IMAGE_ANALYSIS_STREAM  # 非流式调用
        }

        print(f"[Chat] 发送图文分析请求: model={CHAT_MODEL_NAME}, stream={IMAGE_ANALYSIS_STREAM}")

        try:
            response = requests.post(
                CHAT_API_URL,
                headers=headers,
                data=json.dumps(data),
                timeout=REQUEST_TIMEOUT * 2  # 图文分析超时时间加倍
            )
            response.raise_for_status()

            res = response.json()

            # 检查错误
            if res.get("error"):
                error_msg = res.get("error", {}).get("message", "未知错误")
                print(f"[Chat] 图文分析错误: {error_msg}")
                return None

            # 提取回复文本
            choices = res.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                if content:
                    print(f"[Chat] 图文分析完成，回复长度: {len(content)}")
                    # 非流式模式，一次性发送完整回复
                    self.signals.chat_chunk.emit(content)
                    return content

            print("[Chat] 图文分析返回为空")
            return None

        except requests.exceptions.Timeout:
            print("[Chat] 图文分析请求超时")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[Chat] 图文分析请求异常: {e}")
            return None
        except Exception as e:
            print(f"[Chat] 图文分析处理异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _call_chat_api_stream(self) -> Optional[str]:
        """
        纯文本模式：流式调用 Doubao-Seed-1.6

        Returns:
            str: AI 完整回复文本，失败返回 None
        """
        headers = {
            "Authorization": f"Bearer {CHAT_API_KEY}",
            "Content-Type": "application/json"
        }

        # 构造请求体（精简历史，只保留最近2轮对话）
        recent_history = self.history[-4:] if len(self.history) > 4 else self.history
        messages = recent_history + [{"role": "user", "content": self.user_input}]

        data = {
            "model": CHAT_MODEL_NAME,
            "messages": messages,
            "max_completion_tokens": CHAT_MAX_TOKENS,
            "temperature": CHAT_TEMPERATURE,
            "stream": CHAT_STREAM
        }

        # 如果配置了 thinking 参数，添加到请求中
        if CHAT_THINKING:
            data["thinking"] = {"type": CHAT_THINKING}

        print(f"[Chat] 发送流式请求: model={CHAT_MODEL_NAME}, stream={CHAT_STREAM}")

        try:
            response = requests.post(
                CHAT_API_URL,
                headers=headers,
                data=json.dumps(data),
                timeout=REQUEST_TIMEOUT,
                stream=True  # 开启流式响应
            )
            response.raise_for_status()

            full_reply = ""

            # 逐行解析流式返回
            for line in response.iter_lines():
                if not self.is_running:
                    print("[Chat] 流式请求被中断")
                    break

                if line:
                    line_str = line.decode('utf-8')

                    # 跳过空行和注释
                    if not line_str.strip() or line_str.startswith(':'):
                        continue

                    # 去掉 "data: " 前缀
                    if line_str.startswith('data: '):
                        line_str = line_str[6:]

                    # 检查是否结束
                    if line_str.strip() == '[DONE]':
                        print("[Chat] 流式传输完成")
                        break

                    try:
                        res = json.loads(line_str)

                        # 检查错误
                        if res.get("error"):
                            error_msg = res.get("error", {}).get("message", "未知错误")
                            print(f"[Chat] 流式响应错误: {error_msg}")
                            continue

                        # 提取片段文本（OpenAI 兼容格式）
                        choices = res.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            chunk = delta.get("content", "")
                            if chunk:
                                full_reply += chunk
                                # 发送流式片段信号
                                self.signals.chat_chunk.emit(chunk)

                    except json.JSONDecodeError:
                        # 非 JSON 行，跳过
                        continue

            return full_reply if full_reply else None

        except requests.exceptions.Timeout:
            print(f"[Chat] 流式请求超时")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[Chat] 流式请求异常: {e}")
            return None
        except Exception as e:
            print(f"[Chat] 流式处理异常: {e}")
            import traceback
            traceback.print_exc()
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


# ==================== 流式TTS模块（分段合成+边说边播） ====================
class StreamingTTSWorker(QThread):
    """
    流式语音合成工作线程

    功能：
    1. 接收文本片段，按标点切分成句子
    2. 每个句子立即调用 TTS 合成
    3. 将合成的音频片段放入队列
    4. 后台线程按顺序无缝播放队列中的音频

    实现"边生成边播放"，大幅减少等待时间
    """

    # 句子分隔符（按这些标点切分）
    SENTENCE_DELIMITERS = ["。", "！", "？", "；", "\n", "!", "?", ";"]

    def __init__(self, signals: WorkerSignals):
        super().__init__()
        self.signals = signals
        self.text_buffer = ""  # 文本缓冲区
        self.audio_queue = queue.Queue()  # 音频片段队列
        self.chunk_id = 0  # 片段序号
        self.is_running = True
        self.is_finished = False  # 标记文本是否全部接收完毕
        self.first_audio_played = False  # 标记是否已播放第一个音频
        self.play_thread: Optional[threading.Thread] = None
        self.tts_threads: List[threading.Thread] = []

        # 复用 TTSWorker 的协议常量
        self.EVENT_START_CONNECTION = 1
        self.EVENT_FINISH_CONNECTION = 2
        self.EVENT_CONNECTION_STARTED = 50
        self.EVENT_START_SESSION = 100
        self.EVENT_FINISH_SESSION = 102
        self.EVENT_SESSION_STARTED = 150
        self.EVENT_SESSION_FINISHED = 152
        self.EVENT_SESSION_FAILED = 153
        self.EVENT_TASK_REQUEST = 200
        self.EVENT_TTS_RESPONSE = 352

    def add_text_chunk(self, chunk: str):
        """
        接收文本片段，累积到缓冲区并尝试切分句子

        Args:
            chunk: 文本片段
        """
        if not self.is_running:
            return

        self.text_buffer += chunk

        # 按标点切分，提取完整的句子
        while True:
            split_idx = -1
            for delim in self.SENTENCE_DELIMITERS:
                idx = self.text_buffer.find(delim)
                if idx != -1:
                    if split_idx == -1 or idx < split_idx:
                        split_idx = idx

            if split_idx == -1:
                break

            # 提取完整句子（包含分隔符）
            sentence = self.text_buffer[:split_idx + 1].strip()
            self.text_buffer = self.text_buffer[split_idx + 1:]

            if sentence:
                # 启动 TTS 合成线程（非阻塞）
                self._start_tts_synthesis(sentence, self.chunk_id)
                self.chunk_id += 1

    def finish_text(self):
        """
        标记文本接收完毕，处理剩余缓冲区
        """
        self.is_finished = True

        # 处理最后剩余的文本
        if self.text_buffer.strip():
            self._start_tts_synthesis(self.text_buffer.strip(), self.chunk_id)
            self.chunk_id += 1
            self.text_buffer = ""

    def _is_valid_tts_text(self, text: str) -> bool:
        """
        检查文本是否适合TTS合成

        过滤掉：纯emoji、纯符号、过短的文本

        Args:
            text: 待检查文本

        Returns:
            bool: 是否有效
        """
        import re
        # 去掉emoji和符号后检查是否还有有效字符
        # 匹配中文、英文、数字
        valid_chars = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
        return len(valid_chars) >= 2  # 至少2个有效字符

    def _start_tts_synthesis(self, text: str, chunk_id: int):
        """
        启动 TTS 合成线程

        Args:
            text: 待合成的文本
            chunk_id: 片段序号
        """
        # 过滤无效文本（纯emoji、纯符号等）
        if not self._is_valid_tts_text(text):
            print(f"[StreamingTTS] 跳过无效片段 {chunk_id}: {text}")
            return

        print(f"[StreamingTTS] 合成片段 {chunk_id}: {text[:30]}...")
        tts_thread = threading.Thread(
            target=self._synthesize_chunk,
            args=(text, chunk_id),
            daemon=True
        )
        self.tts_threads.append(tts_thread)
        tts_thread.start()

    def _synthesize_chunk(self, text: str, chunk_id: int):
        """
        合成单个文本片段的音频

        Args:
            text: 待合成文本
            chunk_id: 片段序号
        """
        try:
            # 使用 asyncio 运行异步合成
            audio_data = asyncio.run(self._tts_async(text))
            if audio_data:
                # 放入队列（带序号保证顺序）
                self.audio_queue.put((chunk_id, audio_data))
                print(f"[StreamingTTS] 片段 {chunk_id} 合成完成，{len(audio_data)} 字节")
            else:
                print(f"[StreamingTTS] 片段 {chunk_id} 合成失败")
        except Exception as e:
            print(f"[StreamingTTS] 片段 {chunk_id} 合成异常: {e}")

    async def _tts_async(self, text: str) -> Optional[bytes]:
        """
        异步调用 TTS WebSocket API

        Args:
            text: 待合成文本

        Returns:
            音频数据，失败返回 None
        """
        try:
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

                # 1. StartConnection
                start_conn = self._build_event_request(self.EVENT_START_CONNECTION)
                await websocket.send(start_conn)
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                res = self._parse_tts_response(response)
                if res.get("error") or res.get("event") != self.EVENT_CONNECTION_STARTED:
                    return None

                # 2. StartSession
                session_id = str(uuid.uuid4())
                session_params = {
                    "user": {"uid": str(uuid.uuid4())[:16]},
                    "event": self.EVENT_START_SESSION,
                    "namespace": "BidirectionalTTS",
                    "req_params": {
                        "text": "",
                        "speaker": TTS_SPEAKER,
                        "audio_params": {
                            "format": TTS_FORMAT,
                            "sample_rate": TTS_SAMPLE_RATE,
                            "speech_rate": TTS_SPEECH_RATE,
                            "loudness_rate": TTS_LOUDNESS_RATE
                        }
                    }
                }
                start_session = self._build_event_request(
                    self.EVENT_START_SESSION, session_id, session_params
                )
                await websocket.send(start_session)
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                res = self._parse_tts_response(response)
                if res.get("error") or res.get("event") != self.EVENT_SESSION_STARTED:
                    return None

                # 3. TaskRequest
                task_params = {
                    "event": self.EVENT_TASK_REQUEST,
                    "req_params": {"text": text}
                }
                task_packet = self._build_event_request(
                    self.EVENT_TASK_REQUEST, session_id, task_params
                )
                await websocket.send(task_packet)

                # 4. FinishSession
                finish_session = self._build_event_request(
                    self.EVENT_FINISH_SESSION, session_id
                )
                await websocket.send(finish_session)

                # 5. 接收音频数据
                audio_data = b""
                while True:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=15)
                        res = self._parse_tts_response(response)

                        if res.get("error"):
                            break

                        if res.get("audio"):
                            audio_data += res["audio"]

                        if res.get("event") == self.EVENT_SESSION_FINISHED:
                            break

                        if res.get("event") == self.EVENT_SESSION_FAILED:
                            break

                    except asyncio.TimeoutError:
                        break

                # 6. FinishConnection
                finish_conn = self._build_event_request(self.EVENT_FINISH_CONNECTION)
                await websocket.send(finish_conn)

                return audio_data if audio_data else None

        except Exception as e:
            print(f"[StreamingTTS] TTS 异步调用异常: {e}")
            return None

    def _build_event_request(self, event: int, session_id: str = "",
                             payload: dict = None) -> bytes:
        """构建 TTS 请求包（复用 TTSWorker 的协议）"""
        byte0 = 0x11
        byte1 = (0b0001 << 4) | 0b0100  # Full client request with event
        byte2 = (0b0001 << 4) | 0b0000  # JSON, no compression
        byte3 = 0x00
        header = bytes([byte0, byte1, byte2, byte3])

        event_bytes = struct.pack('>I', event)
        result = header + event_bytes

        if event in (self.EVENT_START_SESSION, self.EVENT_FINISH_SESSION,
                     self.EVENT_TASK_REQUEST):
            session_id_bytes = session_id.encode('utf-8')
            session_id_size = struct.pack('>I', len(session_id_bytes))
            result += session_id_size + session_id_bytes

        if payload is None:
            payload = {}
        payload_bytes = json.dumps(payload).encode('utf-8')
        payload_size = struct.pack('>I', len(payload_bytes))
        result += payload_size + payload_bytes

        return result

    def _parse_tts_response(self, data: bytes) -> dict:
        """解析 TTS 响应（复用 TTSWorker 的解析逻辑）"""
        if len(data) < 4:
            return {"error": True}

        header = data[:4]
        message_type = (header[1] >> 4) & 0x0F
        message_type_flags = header[1] & 0x0F
        compression = header[2] & 0x0F

        offset = 4
        result = {"message_type": message_type}

        # 错误帧
        if message_type == 0b1111:
            if len(data) >= offset + 4:
                error_code = struct.unpack('>I', data[offset:offset+4])[0]
                return {"error": True, "code": error_code}
            return {"error": True}

        # 解析事件号
        if message_type_flags == 0b0100:
            if len(data) >= offset + 4:
                event = struct.unpack('>I', data[offset:offset+4])[0]
                result["event"] = event
                offset += 4

        # 音频响应
        if message_type == 0b1011:
            if len(data) >= offset + 4:
                session_id_size = struct.unpack('>I', data[offset:offset+4])[0]
                offset += 4 + session_id_size

            if len(data) >= offset + 4:
                audio_size = struct.unpack('>I', data[offset:offset+4])[0]
                offset += 4
                if len(data) >= offset + audio_size:
                    result["audio"] = data[offset:offset+audio_size]
            return result

        # Full server response
        if message_type == 0b1001:
            event = result.get("event", 0)
            if event in (self.EVENT_SESSION_STARTED, self.EVENT_SESSION_FINISHED,
                         self.EVENT_SESSION_FAILED):
                if len(data) >= offset + 4:
                    session_id_size = struct.unpack('>I', data[offset:offset+4])[0]
                    offset += 4 + session_id_size

            elif event == self.EVENT_CONNECTION_STARTED:
                if len(data) >= offset + 4:
                    conn_id_size = struct.unpack('>I', data[offset:offset+4])[0]
                    offset += 4 + conn_id_size

        return result

    def run(self):
        """线程主函数：启动音频播放线程"""
        self.is_running = True
        self.first_audio_played = False  # 标记是否已播放第一个音频

        # 启动播放线程
        self.play_thread = threading.Thread(target=self._play_audio_queue, daemon=True)
        self.play_thread.start()

        # 等待播放完成
        self.play_thread.join()

        if self.is_running:
            self.signals.tts_finished.emit()

    def _play_audio_queue(self):
        """消费音频队列，按顺序无缝播放"""
        import io

        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"[StreamingTTS] pygame 初始化失败: {e}")
            return

        last_chunk_id = -1
        pending_chunks = {}  # 暂存乱序到达的片段
        empty_count = 0
        max_empty_wait = 100  # 最大空等次数（10秒）

        while self.is_running:
            try:
                # 非阻塞获取
                try:
                    chunk_id, audio_data = self.audio_queue.get(timeout=0.1)
                    empty_count = 0

                    # 如果是下一个期望的片段，直接播放
                    if chunk_id == last_chunk_id + 1:
                        self._play_chunk(audio_data)
                        last_chunk_id = chunk_id

                        # 检查暂存区是否有后续片段
                        while last_chunk_id + 1 in pending_chunks:
                            next_audio = pending_chunks.pop(last_chunk_id + 1)
                            self._play_chunk(next_audio)
                            last_chunk_id += 1
                    else:
                        # 乱序到达，暂存
                        pending_chunks[chunk_id] = audio_data

                except queue.Empty:
                    empty_count += 1

                    # 检查是否所有片段都已处理完毕
                    if self.is_finished and self.audio_queue.empty() and not pending_chunks:
                        # 等待所有 TTS 线程完成
                        all_done = True
                        for t in self.tts_threads:
                            if t.is_alive():
                                all_done = False
                                break

                        if all_done and self.audio_queue.empty() and not pending_chunks:
                            print("[StreamingTTS] 所有片段播放完成")
                            break

                    # 超时退出
                    if empty_count > max_empty_wait and self.is_finished:
                        print("[StreamingTTS] 等待超时，退出播放")
                        break

            except Exception as e:
                print(f"[StreamingTTS] 播放队列处理异常: {e}")
                break

        try:
            pygame.mixer.quit()
        except:
            pass

    def _play_chunk(self, audio_data: bytes):
        """播放单个音频片段"""
        import io

        try:
            # 在播放第一个音频片段时发送 tts_started 信号
            if not self.first_audio_played:
                self.first_audio_played = True
                self.signals.tts_started.emit()
                print("[StreamingTTS] 开始播放第一个音频片段")

            audio_file = io.BytesIO(audio_data)
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()

            # 等待播放完成
            while pygame.mixer.music.get_busy() and self.is_running:
                pygame.time.Clock().tick(10)

        except Exception as e:
            print(f"[StreamingTTS] 播放片段失败: {e}")

    def stop(self):
        """停止播放"""
        self.is_running = False
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except:
            pass


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
        self.streaming_tts_worker: Optional[StreamingTTSWorker] = None  # 流式 TTS

        # 初始化人脸识别管理器
        self.face_recognition_manager = FaceRecognitionManager(
            encodings_path=FACE_ENCODINGS_PATH,
            tolerance=FACE_RECOGNITION_TOLERANCE,
            model=FACE_RECOGNITION_MODEL
        )

        # 初始化物体检测器
        self.object_detector = ObjectDetector(
            model_name=YOLO_MODEL_NAME,
            confidence_threshold=YOLO_CONFIDENCE_THRESHOLD,
            use_chinese=YOLO_USE_CHINESE
        )

        # 初始化声纹识别管理器
        self.speaker_recognition_manager = SpeakerRecognitionManager(
            data_path=VOICEPRINT_DATA_PATH,
            similarity_threshold=SPEAKER_SIMILARITY_THRESHOLD,
            min_audio_duration=SPEAKER_MIN_AUDIO_DURATION
        )

        # 初始化意图处理器
        self.intent_handler = IntentHandler(
            camera_callback=self._capture_image_callback,
            face_recognition_manager=self.face_recognition_manager,
            object_detector=self.object_detector
        )

        # 对话历史
        self.chat_history: List[Dict[str, str]] = []

        # 当前状态
        self.is_recording = False
        self.is_tts_playing = False  # TTS 是否正在播放
        self.current_asr_text = ""
        self.current_ai_text = ""  # AI 回复文本（流式累积）
        self.current_image_path: Optional[str] = None   # 当前拍摄的图片路径
        self.current_image_base64: Optional[str] = None # 当前图片的Base64编码

        # 人脸注册状态（追问模式）
        self.waiting_for_face_name = False              # 是否在等待用户说人名
        self.pending_face_encoding = None               # 待注册的人脸编码

        # 声纹识别状态
        self.current_speaker_name: Optional[str] = None  # 当前识别的说话人
        self.pending_speaker_embedding = None            # 待注册的声纹嵌入向量
        self.waiting_for_speaker_name = False            # 是否在等待用户说名字

        # 计时统计（用于性能分析）
        self.time_asr_end = 0.0          # 语音识别完成时间
        self.time_chat_first = 0.0       # Chat第一个chunk到达时间
        self.time_tts_first_synth = 0.0  # TTS第一个片段合成完成时间
        self.time_tts_play_start = 0.0   # TTS开始播放时间
        self.is_first_chunk = True       # 是否第一个chunk

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

        # 耗时统计显示区域
        timing_frame = QFrame()
        timing_frame.setStyleSheet("""
            QFrame {
                background-color: #fff8e1;
                border: 1px solid #ffe082;
                border-radius: 6px;
                padding: 5px;
            }
        """)
        timing_layout = QHBoxLayout(timing_frame)
        timing_layout.setContentsMargins(10, 5, 10, 5)
        timing_layout.setSpacing(20)

        # 各阶段耗时标签
        self.timing_asr_chat = QLabel("ASR→首字: --")
        self.timing_asr_chat.setFont(QFont("Microsoft YaHei", 9))
        self.timing_asr_chat.setStyleSheet("color: #795548; border: none;")
        timing_layout.addWidget(self.timing_asr_chat)

        self.timing_chat_tts = QLabel("首字→播放: --")
        self.timing_chat_tts.setFont(QFont("Microsoft YaHei", 9))
        self.timing_chat_tts.setStyleSheet("color: #795548; border: none;")
        timing_layout.addWidget(self.timing_chat_tts)

        self.timing_total = QLabel("总延时: --")
        self.timing_total.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        self.timing_total.setStyleSheet("color: #e65100; border: none;")
        timing_layout.addWidget(self.timing_total)

        timing_layout.addStretch()
        bottom_layout.addWidget(timing_frame)

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
        self.signals.asr_audio_data.connect(self._on_asr_audio_data)  # 声纹识别
        self.signals.asr_error.connect(self._on_asr_error)

        # 录音状态信号
        self.signals.recording_started.connect(self._on_recording_started)
        self.signals.recording_stopped.connect(self._on_recording_stopped)

        # 对话模型信号
        self.signals.chat_thinking.connect(self._on_chat_thinking)
        self.signals.chat_chunk.connect(self._on_chat_chunk)  # 流式片段
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

        # 停止流式 TTS 工作线程
        if self.streaming_tts_worker and self.streaming_tts_worker.isRunning():
            self.streaming_tts_worker.stop()

        # 停止普通 TTS 工作线程
        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.stop()

        # 停止 Chat 工作线程
        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.stop()

        # 立即开始新的录音
        self._start_recording()

    def _capture_image_callback(self) -> Optional[str]:  # NEW
        """
        摄像头拍照回调函数

        使用配置的参数调用摄像头拍照，并返回图片路径
        同时将图片转换为Base64编码存储

        Returns:
            图片路径，失败返回None
        """
        print("[UI] 正在调用摄像头拍照...")

        # 使用配置的参数拍照并编码
        image_path, image_base64 = capture_and_encode(
            save_path=TEMP_IMAGE_PATH,
            max_width=IMAGE_MAX_WIDTH,
            max_height=IMAGE_MAX_HEIGHT,
            quality=IMAGE_QUALITY
        )

        if image_path and image_base64:
            # 保存Base64编码供后续使用
            self.current_image_base64 = image_base64
            self.current_image_path = image_path
            print(f"[UI] 拍照并编码成功，Base64长度: {len(image_base64)}")
            return image_path
        else:
            self.current_image_base64 = None
            self.current_image_path = None
            print("[UI] 拍照或编码失败")
            return None

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

    def _on_asr_audio_data(self, audio_bytes: bytes):
        """
        处理原始音频数据，提取声纹并匹配

        Args:
            audio_bytes: 原始PCM音频数据
        """
        print(f"[声纹识别] 收到音频数据: {len(audio_bytes)} 字节")

        # 如果正在等待用户说名字，不进行声纹匹配（避免覆盖状态）
        if self.waiting_for_speaker_name:
            print("[声纹识别] 正在等待用户说名字，跳过声纹匹配")
            return

        # 提取声纹嵌入向量
        embedding = self.speaker_recognition_manager.extract_embedding(
            audio_bytes, sample_rate=AUDIO_RATE
        )

        if embedding is None:
            print("[声纹识别] 提取声纹失败（音频太短或无效）")
            self.current_speaker_name = None
            self.pending_speaker_embedding = None
            return

        # 匹配说话人
        name, similarity = self.speaker_recognition_manager.match_speaker(embedding)

        if name:
            # 识别到已知说话人
            self.current_speaker_name = name
            self.pending_speaker_embedding = None
            print(f"[声纹识别] 识别到说话人: {name} (相似度: {similarity:.3f})")
        else:
            # 未知说话人，暂存声纹待注册
            self.current_speaker_name = None
            self.pending_speaker_embedding = embedding
            print(f"[声纹识别] 未知说话人，暂存声纹待注册 (最高相似度: {similarity:.3f})")

    def _extract_name_from_text(self, text: str) -> Optional[str]:
        """
        从文本中提取名字

        Args:
            text: 用户说的文本

        Returns:
            提取的名字，失败返回None
        """
        text = text.strip()
        if not text:
            return None

        # 去掉常见前缀
        prefixes = ["我叫", "我是", "叫我", "我的名字是", "你可以叫我", "我叫做", "我名叫"]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        # 去掉语气词后缀
        suffixes = ["吧", "呀", "啊", "哦", "呢", "嘛", "哈", "了"]
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[:-len(suffix)].strip()

        # 去掉标点符号
        import re
        text = re.sub(r'[，。！？,.!?]', '', text).strip()

        return text if text else None

    def _on_asr_finished(self, final_text: str):
        """语音识别完成"""
        # 记录语音识别完成时间
        self.time_asr_end = time.time()
        self.is_first_chunk = True  # 重置首字标记

        self.current_asr_text = final_text
        self.user_text.setText(final_text)

        # 重置耗时显示
        self.timing_asr_chat.setText("ASR→首字: 计时中...")
        self.timing_chat_tts.setText("首字→播放: --")
        self.timing_total.setText("总延时: --")

        # 更新按钮状态
        self.mic_button.setText("🎤 点击说话")
        self._set_button_style_disabled()
        self.mic_button.setEnabled(False)

        if final_text.strip():
            # ========== 检查是否在等待人名（人脸注册追问模式） ==========
            if self.waiting_for_face_name and self.pending_face_encoding is not None:
                self._complete_face_registration(final_text)
                return

            # ========== 检查是否在等待说话人名字（声纹注册追问模式） ==========
            if self.waiting_for_speaker_name and self.pending_speaker_embedding is not None:
                self._complete_speaker_registration(final_text)
                return

            # ========== 意图判断 ==========
            self.status_label.setText("正在分析意图...")
            QApplication.processEvents()

            intent_result = self.intent_handler.process(final_text)
            print(f"[UI] 意图判断结果: {intent_result.intent_type.value}")

            # 处理意图结果
            if intent_result.intent_type == IntentType.FACE_REGISTER:
                # 人脸注册意图
                self._handle_face_register_result(intent_result, final_text)
            elif intent_result.intent_type == IntentType.FACE_RECOGNIZE:
                # 人脸识别意图
                self._handle_face_recognize_result(intent_result, final_text)
            elif intent_result.intent_type == IntentType.LOOK:
                # 看相关意图 - 本地识别模式（人脸 + YOLO）
                self._handle_look_result(intent_result, final_text)
            else:
                # 默认意图（纯文本）
                self.current_image_path = None
                self.current_image_base64 = None
                self._call_chat(final_text)
        else:
            self.status_label.setText("未识别到有效语音，请重试")
            self._reset_button()

    def _on_asr_error(self, error: str):
        """语音识别错误"""
        self.status_label.setText(f"识别错误: {error}")
        self.ai_text.setText(f"语音识别失败: {error}")
        self._reset_button()

    def _handle_face_register_result(self, intent_result: IntentResult, original_text: str):
        """
        处理人脸注册意图结果

        Args:
            intent_result: 意图判断结果
            original_text: 用户原始输入
        """
        if intent_result.error_message:
            # 拍照或人脸检测失败
            self.status_label.setText(intent_result.error_message)
            self.ai_text.setText(intent_result.error_message)
            print(f"[UI] 人脸注册失败: {intent_result.error_message}")
            self._speak_text(intent_result.error_message)
            return

        if intent_result.pending_face_encoding is not None:
            # 成功检测到人脸，进入追问模式
            self.pending_face_encoding = intent_result.pending_face_encoding
            self.waiting_for_face_name = True

            ask_name_text = "好的，请问这位叫什么名字？"
            self.status_label.setText("等待用户说人名...")
            self.ai_text.setText(ask_name_text)
            print(f"[UI] 人脸编码已保存，等待用户提供人名")

            # 语音追问
            self._speak_text(ask_name_text)
        else:
            # 未检测到人脸
            error_msg = "未检测到人脸，请确保脸部清晰可见"
            self.status_label.setText(error_msg)
            self.ai_text.setText(error_msg)
            self._speak_text(error_msg)

    def _complete_face_registration(self, name_text: str):
        """
        完成人脸注册（用户说出人名后）

        Args:
            name_text: 用户说的人名
        """
        # 清理人名（去除标点符号）
        import re
        name = re.sub(r'[，。！？、；：""''（）【】\s]', '', name_text).strip()

        if not name:
            error_msg = "没有听清名字，请再说一次"
            self.status_label.setText(error_msg)
            self.ai_text.setText(error_msg)
            self._speak_text(error_msg)
            return

        # 注册人脸
        success, message = self.face_recognition_manager.register_face_with_encoding(
            encoding=self.pending_face_encoding,
            name=name
        )

        # 重置状态
        self.waiting_for_face_name = False
        self.pending_face_encoding = None

        if success:
            result_msg = f"好的，我已经记住{name}了"
            self.status_label.setText(f"已注册: {name}")
            print(f"[UI] 人脸注册成功: {name}")
        else:
            result_msg = f"注册失败：{message}"
            self.status_label.setText(result_msg)
            print(f"[UI] 人脸注册失败: {message}")

        self.ai_text.setText(result_msg)
        self._speak_text(result_msg)

    def _handle_look_result(self, intent_result: IntentResult, original_text: str):
        """
        处理看相关意图结果（本地识别模式：人脸 + YOLO）

        Args:
            intent_result: 意图判断结果
            original_text: 用户原始输入
        """
        if intent_result.error_message:
            self.status_label.setText(intent_result.error_message)
            self.ai_text.setText(intent_result.error_message)
            print(f"[UI] 本地识别失败: {intent_result.error_message}")
            self._speak_text(intent_result.error_message)
            return

        # 构建识别结果描述
        descriptions = []
        unknown_count = 0
        recognized_names = []

        # 人脸识别结果
        if intent_result.face_results:
            for face in intent_result.face_results:
                if face.get("name") == "unknown":
                    unknown_count += 1
                else:
                    recognized_names.append(face.get("name", ""))

            if recognized_names:
                descriptions.append(f"人物：{', '.join(recognized_names)}")

        # 物体检测结果（排除"人"类别，因为已经通过人脸识别处理了）
        if intent_result.object_results:
            object_counts = {}
            for obj in intent_result.object_results:
                name = obj.get("class_name", "")
                if name and name != "人":  # 排除人，避免重复
                    object_counts[name] = object_counts.get(name, 0) + 1

            object_descs = []
            for name, count in object_counts.items():
                if count == 1:
                    object_descs.append(name)
                else:
                    object_descs.append(f"{count}个{name}")

            if object_descs:
                descriptions.append(f"物体：{', '.join(object_descs)}")

        # 生成回复
        if descriptions:
            result_text = f"我看到了：{'; '.join(descriptions)}"
        else:
            result_text = ""

        # 如果有未知人脸，追问并进入注册流程
        if unknown_count > 0:
            # 提取人脸编码用于后续注册
            if intent_result.image_path and self.face_recognition_manager:
                encoding = self.face_recognition_manager.encode_face(intent_result.image_path)
                if encoding is not None:
                    self.pending_face_encoding = encoding
                    self.waiting_for_face_name = True

                    if unknown_count == 1:
                        ask_text = "我看到一个人，但我不认识。请问他是谁？"
                    else:
                        ask_text = f"我看到{unknown_count}个人，但我都不认识。请问他们是谁？"

                    if result_text:
                        result_text = f"{result_text}。{ask_text}"
                    else:
                        result_text = ask_text

                    print(f"[UI] 检测到未知人脸，进入注册追问模式")
                    self.status_label.setText("等待用户说人名...")
            else:
                # 无法提取编码，只报告结果
                if unknown_count == 1:
                    descriptions.insert(0, "1个未知人脸")
                else:
                    descriptions.insert(0, f"{unknown_count}个未知人脸")
                result_text = f"我看到了：{'; '.join(descriptions)}"
        elif not result_text:
            result_text = "没有识别到明显的人脸或物体"

        print(f"[UI] 本地识别结果: {result_text}")
        self.ai_text.setText(result_text)

        # 清理临时图片（如果不需要等待注册）
        if intent_result.image_path and not self.waiting_for_face_name:
            delete_temp_image(intent_result.image_path)

        # 语音播报
        self._speak_text(result_text)

    def _handle_face_recognize_result(self, intent_result: IntentResult, original_text: str):
        """
        处理人脸识别意图结果

        Args:
            intent_result: 意图判断结果
            original_text: 用户原始输入
        """
        if intent_result.error_message:
            # 拍照或人脸检测失败
            self.status_label.setText(intent_result.error_message)
            self.ai_text.setText(intent_result.error_message)
            print(f"[UI] 人脸识别失败: {intent_result.error_message}")
            self._speak_text(intent_result.error_message)
            return

        if not intent_result.face_results:
            # 没有已注册的人脸数据
            no_data_msg = "我还没有记住任何人，需要先让我记住一些人"
            self.status_label.setText(no_data_msg)
            self.ai_text.setText(no_data_msg)
            self._speak_text(no_data_msg)
            return

        # 构建识别结果描述
        recognized_names = []
        unknown_count = 0
        for face in intent_result.face_results:
            if face["name"] == "unknown":
                unknown_count += 1
            else:
                recognized_names.append(face["name"])

        # 构建人脸信息描述（用于提示词）
        if recognized_names:
            if unknown_count > 0:
                face_info = f"照片中我认出了{', '.join(recognized_names)}，还有{unknown_count}个我不认识的人"
            else:
                face_info = f"照片中是{', '.join(recognized_names)}"
        else:
            face_info = f"照片中有{unknown_count}个人，但我都不认识"

        print(f"[UI] 人脸识别结果: {face_info}")

        # 获取图片 Base64 编码
        if intent_result.image_path:
            image_base64 = image_to_base64(intent_result.image_path)
            self.current_image_path = intent_result.image_path
            self.current_image_base64 = image_base64
        else:
            image_base64 = None

        # 结合对话模型分析
        if image_base64:
            self.status_label.setText("正在分析...")
            # 使用人脸识别专用提示词模板
            enhanced_prompt = FACE_RECOGNITION_PROMPT_TEMPLATE.format(
                face_info=face_info,
                user_question=original_text,
                image_base64=image_base64
            )
            # 调用对话模型
            self._call_chat_with_custom_prompt(enhanced_prompt, image_path=intent_result.image_path)
        else:
            # 无图片，直接回复识别结果
            self.status_label.setText("识别完成")
            self.ai_text.setText(face_info)
            self._speak_text(face_info)

    def _call_chat_with_custom_prompt(self, prompt: str, image_path: Optional[str] = None):
        """
        使用自定义提示词调用对话模型

        Args:
            prompt: 完整的提示词（已包含图片Base64）
            image_path: 临时图片路径（用于清理）
        """
        self.chat_worker = ChatWorker(self.signals)
        self.chat_worker.set_input(
            prompt,
            [],  # 不使用历史对话
            image_base64=None,  # 提示词中已包含图片
            image_path=image_path,
            use_image_analysis_mode=True  # 使用非流式模式
        )
        self.chat_worker.start()

    def _speak_text(self, text: str):
        """
        语音播报文本

        Args:
            text: 要播报的文本
        """
        # 启动流式 TTS（单次播报）
        self.streaming_tts_worker = StreamingTTSWorker(self.signals)
        self.streaming_tts_worker.start()
        # 发送文本并结束
        self.signals.chat_chunk.emit(text)
        self.signals.chat_reply.emit(text)
        # 重置按钮
        self._reset_button()

    def _call_chat(self, user_input: str,
                   image_base64: Optional[str] = None,
                   image_path: Optional[str] = None):  # MODIFIED
        """
        调用对话模型

        Args:
            user_input: 用户输入文本
            image_base64: 图片的Base64编码（可选，用于图文分析）
            image_path: 临时图片路径（可选，用于清理）
        """
        self.chat_worker = ChatWorker(self.signals)
        self.chat_worker.set_input(
            user_input,
            self.chat_history,
            image_base64=image_base64,
            image_path=image_path
        )
        self.chat_worker.start()

    def _on_chat_thinking(self):
        """AI 正在思考，同时启动流式 TTS"""
        self.status_label.setText("AI 正在思考...")
        self.ai_text.setText("")
        self.current_ai_text = ""

        # 创建并启动流式 TTS 工作线程
        self.streaming_tts_worker = StreamingTTSWorker(self.signals)
        self.streaming_tts_worker.start()
        print("[UI] 流式 TTS 已启动，等待文本片段...")

    def _on_chat_chunk(self, chunk: str):
        """接收 AI 流式回复片段，传给 TTS 并更新 UI"""
        if not chunk:
            return

        # 记录第一个chunk到达时间
        if self.is_first_chunk:
            self.time_chat_first = time.time()
            self.is_first_chunk = False
            # 计算 ASR→首字 耗时
            asr_to_chat = (self.time_chat_first - self.time_asr_end) * 1000
            self.timing_asr_chat.setText(f"ASR→首字: {asr_to_chat:.0f}ms")
            self.timing_chat_tts.setText("首字→播放: 计时中...")
            print(f"[计时] ASR→首字: {asr_to_chat:.0f}ms")

        # 累积文本
        self.current_ai_text += chunk
        self.ai_text.setText(self.current_ai_text)

        # 传给流式 TTS
        if self.streaming_tts_worker and self.streaming_tts_worker.is_running:
            self.streaming_tts_worker.add_text_chunk(chunk)

        # 强制刷新 UI
        self.ai_text.repaint()
        QApplication.processEvents()

    def _on_chat_reply(self, reply: str):
        """AI 回复完成"""
        # 确保显示完整文本
        self.ai_text.setText(reply)

        # 通知流式 TTS 文本已结束
        if self.streaming_tts_worker:
            self.streaming_tts_worker.finish_text()
            print("[UI] 流式 TTS 文本已全部发送")

        # 更新对话历史
        self.chat_history.append({"role": "user", "content": self.current_asr_text})
        self.chat_history.append({"role": "assistant", "content": reply})

        # 限制历史长度（保留最近 10 轮对话）
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]

    def _on_chat_error(self, error: str):
        """对话模型错误"""
        self.status_label.setText(f"对话错误: {error}")
        self.ai_text.setText(f"对话失败: {error}")

        # 停止流式 TTS
        if self.streaming_tts_worker and self.streaming_tts_worker.isRunning():
            self.streaming_tts_worker.stop()

        # 清空待注册的声纹，避免 Chat 失败后仍追问名字
        self.pending_speaker_embedding = None

        self._reset_button()

    def _call_tts(self, text: str):
        """调用语音合成（非流式版本，作为备用）"""
        self.status_label.setText("正在合成语音...")

        self.tts_worker = TTSWorker(self.signals)
        self.tts_worker.set_text(text)
        self.tts_worker.start()

    def _on_tts_started(self):
        """TTS 开始播放"""
        # 记录TTS开始播放时间并计算耗时
        self.time_tts_play_start = time.time()

        # 计算各阶段耗时
        if self.time_chat_first > 0:
            chat_to_tts = (self.time_tts_play_start - self.time_chat_first) * 1000
            self.timing_chat_tts.setText(f"首字→播放: {chat_to_tts:.0f}ms")
            print(f"[计时] 首字→播放: {chat_to_tts:.0f}ms")

        if self.time_asr_end > 0:
            total_delay = (self.time_tts_play_start - self.time_asr_end) * 1000
            self.timing_total.setText(f"总延时: {total_delay:.0f}ms")
            print(f"[计时] 总延时: {total_delay:.0f}ms")

        self.is_tts_playing = True
        self.status_label.setText("正在播放语音...（点击打断）")
        # 启用按钮，允许打断
        self.mic_button.setText("⏹️ 点击打断")
        self.mic_button.setEnabled(True)
        self._set_button_style_interrupt()

    def _on_tts_finished(self):
        """TTS 播放完成"""
        self.is_tts_playing = False

        # 检查是否需要追问说话人名字（有待注册的声纹）
        if self.pending_speaker_embedding is not None and not self.waiting_for_speaker_name:
            self.waiting_for_speaker_name = True
            self.status_label.setText("询问说话人名字...")
            # 播报追问语音
            self._speak_text("对了，我还不知道你的名字，请问怎么称呼你？")
            return

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

    def _complete_speaker_registration(self, text: str):
        """
        完成声纹注册（用户回复名字后调用）

        Args:
            text: 用户说的名字文本
        """
        # 提取名字
        name = self._extract_name_from_text(text)

        if name and self.pending_speaker_embedding is not None:
            # 注册声纹
            success, message = self.speaker_recognition_manager.register_speaker(
                name, self.pending_speaker_embedding
            )

            if success:
                print(f"[声纹识别] 声纹注册成功: {name}")
                self._speak_text(f"好的，{name}，我记住你了！")
            else:
                print(f"[声纹识别] 声纹注册失败: {message}")
                self._speak_text(f"抱歉，注册失败了：{message}")
        else:
            print(f"[声纹识别] 未能提取有效名字: {text}")
            self._speak_text("抱歉，我没有听清你的名字，下次再告诉我吧。")

        # 重置状态
        self.waiting_for_speaker_name = False
        self.pending_speaker_embedding = None

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止所有工作线程
        if self.asr_worker and self.asr_worker.isRunning():
            self.asr_worker.stop()
            self.asr_worker.wait(1000)

        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.stop()
            self.chat_worker.wait(1000)

        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.stop()
            self.tts_worker.wait(1000)

        if self.streaming_tts_worker and self.streaming_tts_worker.isRunning():
            self.streaming_tts_worker.stop()
            self.streaming_tts_worker.wait(1000)

        # 清理临时音频文件
        if os.path.exists(TEMP_AUDIO_PATH):
            try:
                os.remove(TEMP_AUDIO_PATH)
            except:
                pass

        # 清理临时图片文件  # MODIFIED
        if self.current_image_path:
            delete_temp_image(self.current_image_path)
            self.current_image_path = None
        self.current_image_base64 = None  # 清理Base64数据

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
