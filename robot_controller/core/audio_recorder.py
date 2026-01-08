# -*- coding: utf-8 -*-
"""
ALSA 音频录制模块
适用于 RK3568 嵌入式平台
"""

import asyncio
import struct
import time
from typing import Optional, Callable, AsyncGenerator
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger


@dataclass
class AudioConfig:
    """音频配置"""
    device: str = "plughw:2,0"
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    chunk_size: int = 3200  # 200ms @ 16kHz


class AudioRecorder:
    """
    ALSA 音频录制器

    支持异步录音和静音检测
    """

    def __init__(self, config: Optional[AudioConfig] = None):
        self.logger = get_logger()
        self.config = config or AudioConfig()

        self._recording = False
        self._audio_buffer = bytearray()
        self._process: Optional[asyncio.subprocess.Process] = None

        # 静音检测参数
        self._silence_threshold = 500
        self._silence_duration = 1.5  # 秒
        self._last_sound_time = 0

    def set_silence_params(self, threshold: int, duration: float):
        """设置静音检测参数"""
        self._silence_threshold = threshold
        self._silence_duration = duration

    def _calculate_rms(self, audio_data: bytes) -> float:
        """计算音频 RMS（均方根）值"""
        if len(audio_data) < 2:
            return 0

        # 16-bit PCM 数据
        sample_count = len(audio_data) // 2
        if sample_count == 0:
            return 0

        samples = struct.unpack(f"<{sample_count}h", audio_data)
        sum_squares = sum(s * s for s in samples)
        return (sum_squares / sample_count) ** 0.5

    def _is_silence(self, audio_data: bytes) -> bool:
        """检测是否为静音"""
        rms = self._calculate_rms(audio_data)
        return rms < self._silence_threshold

    async def start(self) -> bool:
        """
        启动录音

        使用 arecord 命令进行 ALSA 录音
        """
        if self._recording:
            self.logger.warning("录音已在进行中")
            return False

        self._audio_buffer.clear()
        self._last_sound_time = time.time()

        # 构建 arecord 命令
        cmd = [
            "arecord",
            "-D", self.config.device,
            "-f", "S16_LE",
            "-r", str(self.config.sample_rate),
            "-c", str(self.config.channels),
            "-t", "raw",
            "-q",  # 静默模式
            "-"    # 输出到 stdout
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self._recording = True
            self.logger.info(f"录音启动: {self.config.device}")
            return True

        except Exception as e:
            self.logger.error(f"录音启动失败: {e}")
            return False

    async def stop(self) -> bytes:
        """
        停止录音

        Returns:
            录音数据
        """
        if not self._recording:
            return bytes(self._audio_buffer)

        self._recording = False

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception as e:
                self.logger.warning(f"停止录音进程异常: {e}")
            finally:
                self._process = None

        self.logger.info(f"录音停止，数据长度: {len(self._audio_buffer)} bytes")
        return bytes(self._audio_buffer)

    async def read_chunk(self) -> Optional[bytes]:
        """
        读取一个音频块

        Returns:
            音频数据块，如果录音已停止则返回 None
        """
        if not self._recording or not self._process:
            return None

        try:
            chunk = await asyncio.wait_for(
                self._process.stdout.read(self.config.chunk_size),
                timeout=1.0
            )

            if chunk:
                self._audio_buffer.extend(chunk)

                # 更新静音检测
                if not self._is_silence(chunk):
                    self._last_sound_time = time.time()

                return chunk
            else:
                return None

        except asyncio.TimeoutError:
            return b""
        except Exception as e:
            self.logger.error(f"读取音频块失败: {e}")
            return None

    async def stream_audio(
        self,
        on_silence: Optional[Callable] = None,
        max_duration: float = 30.0
    ) -> AsyncGenerator[bytes, None]:
        """
        流式录音生成器

        Args:
            on_silence: 检测到静音时的回调
            max_duration: 最大录音时长（秒）

        Yields:
            音频数据块
        """
        start_time = time.time()

        while self._recording:
            chunk = await self.read_chunk()

            if chunk is None:
                break

            if len(chunk) > 0:
                yield chunk

            # 检查静音超时
            silence_time = time.time() - self._last_sound_time
            if silence_time > self._silence_duration:
                self.logger.info(f"检测到静音 {silence_time:.1f}s")
                if on_silence:
                    on_silence()
                break

            # 检查最大录音时长
            if time.time() - start_time > max_duration:
                self.logger.warning(f"录音超时 {max_duration}s")
                break

    def get_buffer(self) -> bytes:
        """获取当前录音缓冲"""
        return bytes(self._audio_buffer)

    def is_recording(self) -> bool:
        """检查是否正在录音"""
        return self._recording

    def get_duration(self) -> float:
        """获取录音时长（秒）"""
        bytes_per_sample = self.config.bit_depth // 8
        bytes_per_second = (
            self.config.sample_rate *
            self.config.channels *
            bytes_per_sample
        )
        return len(self._audio_buffer) / bytes_per_second if bytes_per_second > 0 else 0


class PyAudioRecorder:
    """
    PyAudio 音频录制器

    作为 ALSA arecord 的备选方案
    """

    def __init__(self, config: Optional[AudioConfig] = None):
        self.logger = get_logger()
        self.config = config or AudioConfig()

        self._recording = False
        self._audio_buffer = bytearray()
        self._stream = None
        self._audio = None

        # 静音检测参数
        self._silence_threshold = 500
        self._silence_duration = 1.5
        self._last_sound_time = 0

    def set_silence_params(self, threshold: int, duration: float):
        """设置静音检测参数"""
        self._silence_threshold = threshold
        self._silence_duration = duration

    def _calculate_rms(self, audio_data: bytes) -> float:
        """计算音频 RMS 值"""
        if len(audio_data) < 2:
            return 0

        sample_count = len(audio_data) // 2
        if sample_count == 0:
            return 0

        samples = struct.unpack(f"<{sample_count}h", audio_data)
        sum_squares = sum(s * s for s in samples)
        return (sum_squares / sample_count) ** 0.5

    def _is_silence(self, audio_data: bytes) -> bool:
        """检测是否为静音"""
        rms = self._calculate_rms(audio_data)
        return rms < self._silence_threshold

    def start(self, device_index: Optional[int] = None) -> bool:
        """启动录音"""
        try:
            import pyaudio
        except ImportError:
            self.logger.error("PyAudio 未安装")
            return False

        if self._recording:
            self.logger.warning("录音已在进行中")
            return False

        self._audio_buffer.clear()
        self._last_sound_time = time.time()

        try:
            self._audio = pyaudio.PyAudio()
            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.config.chunk_size,
            )
            self._recording = True
            self.logger.info("PyAudio 录音启动")
            return True

        except Exception as e:
            self.logger.error(f"PyAudio 录音启动失败: {e}")
            self.cleanup()
            return False

    def stop(self) -> bytes:
        """停止录音"""
        self._recording = False
        self.cleanup()
        return bytes(self._audio_buffer)

    def cleanup(self):
        """清理资源"""
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._audio:
            try:
                self._audio.terminate()
            except Exception:
                pass
            self._audio = None

    def read_chunk(self) -> Optional[bytes]:
        """读取一个音频块"""
        if not self._recording or not self._stream:
            return None

        try:
            chunk = self._stream.read(
                self.config.chunk_size,
                exception_on_overflow=False
            )
            self._audio_buffer.extend(chunk)

            if not self._is_silence(chunk):
                self._last_sound_time = time.time()

            return chunk

        except Exception as e:
            self.logger.error(f"读取音频块失败: {e}")
            return None

    def get_buffer(self) -> bytes:
        """获取当前录音缓冲"""
        return bytes(self._audio_buffer)

    def is_recording(self) -> bool:
        """检查是否正在录音"""
        return self._recording
