# -*- coding: utf-8 -*-
"""
语音唤醒模块
支持多种唤醒引擎
"""

import asyncio
import struct
import time
from abc import ABC, abstractmethod
from typing import Optional, Callable, List
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger


@dataclass
class WakeWordConfig:
    """唤醒词配置"""
    engine: str = "energy"  # energy, porcupine, snowboy
    keywords: List[str] = None
    sensitivity: float = 0.5
    audio_device: str = "plughw:2,0"
    sample_rate: int = 16000

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = ["小元"]


class WakeWordDetector(ABC):
    """唤醒词检测器基类"""

    def __init__(self, config: Optional[WakeWordConfig] = None):
        self.logger = get_logger()
        self.config = config or WakeWordConfig()
        self._running = False
        self._on_wake: Optional[Callable] = None

    def set_on_wake(self, callback: Callable):
        """设置唤醒回调"""
        self._on_wake = callback

    @abstractmethod
    async def start(self):
        """启动检测"""
        pass

    @abstractmethod
    async def stop(self):
        """停止检测"""
        pass

    def is_running(self) -> bool:
        """检查是否运行中"""
        return self._running


class EnergyWakeWordDetector(WakeWordDetector):
    """
    基于能量检测的唤醒

    简易方案：检测声音能量超过阈值时触发唤醒
    适用于没有专业唤醒引擎的场景
    """

    def __init__(self, config: Optional[WakeWordConfig] = None):
        super().__init__(config)
        self._process = None
        self._energy_threshold = 1000  # 能量阈值
        self._min_duration = 0.3  # 最小持续时间（秒）
        self._cooldown = 2.0  # 冷却时间（秒）
        self._last_wake_time = 0

    def set_threshold(self, threshold: int):
        """设置能量阈值"""
        self._energy_threshold = threshold

    def _calculate_energy(self, audio_data: bytes) -> float:
        """计算音频能量"""
        if len(audio_data) < 2:
            return 0

        sample_count = len(audio_data) // 2
        if sample_count == 0:
            return 0

        samples = struct.unpack(f"<{sample_count}h", audio_data)
        return sum(abs(s) for s in samples) / sample_count

    async def start(self):
        """启动能量检测"""
        if self._running:
            return

        self._running = True
        self.logger.info("能量唤醒检测启动")

        # 启动 arecord 进程
        cmd = [
            "arecord",
            "-D", self.config.audio_device,
            "-f", "S16_LE",
            "-r", str(self.config.sample_rate),
            "-c", "1",
            "-t", "raw",
            "-q",
            "-"
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            chunk_size = 3200  # 200ms @ 16kHz
            high_energy_start = None

            while self._running:
                try:
                    chunk = await asyncio.wait_for(
                        self._process.stdout.read(chunk_size),
                        timeout=1.0
                    )

                    if not chunk:
                        continue

                    energy = self._calculate_energy(chunk)

                    if energy > self._energy_threshold:
                        if high_energy_start is None:
                            high_energy_start = time.time()
                        elif time.time() - high_energy_start >= self._min_duration:
                            # 检测到持续的高能量
                            if time.time() - self._last_wake_time >= self._cooldown:
                                self._last_wake_time = time.time()
                                self.logger.info(f"检测到唤醒信号 (能量: {energy:.0f})")
                                if self._on_wake:
                                    self._on_wake()
                            high_energy_start = None
                    else:
                        high_energy_start = None

                except asyncio.TimeoutError:
                    continue

        except Exception as e:
            self.logger.error(f"能量检测异常: {e}")

        finally:
            self._running = False

    async def stop(self):
        """停止能量检测"""
        self._running = False

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass
            finally:
                self._process = None

        self.logger.info("能量唤醒检测停止")


class PorcupineWakeWordDetector(WakeWordDetector):
    """
    Porcupine 唤醒词检测器

    使用 Picovoice 的 Porcupine 引擎
    需要申请 API Key: https://picovoice.ai/
    """

    def __init__(self, config: Optional[WakeWordConfig] = None, access_key: str = ""):
        super().__init__(config)
        self._access_key = access_key
        self._porcupine = None
        self._audio_stream = None

    async def start(self):
        """启动 Porcupine 检测"""
        try:
            import pvporcupine
            import pyaudio
        except ImportError:
            self.logger.error("Porcupine 未安装，请运行: pip install pvporcupine pyaudio")
            return

        if not self._access_key:
            self.logger.error("Porcupine 需要 access_key")
            return

        if self._running:
            return

        self._running = True
        self.logger.info("Porcupine 唤醒检测启动")

        try:
            # 创建 Porcupine 实例
            self._porcupine = pvporcupine.create(
                access_key=self._access_key,
                keywords=self.config.keywords,
                sensitivities=[self.config.sensitivity] * len(self.config.keywords)
            )

            # 创建音频流
            pa = pyaudio.PyAudio()
            self._audio_stream = pa.open(
                rate=self._porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self._porcupine.frame_length
            )

            while self._running:
                pcm = self._audio_stream.read(
                    self._porcupine.frame_length,
                    exception_on_overflow=False
                )
                pcm = struct.unpack_from(
                    "h" * self._porcupine.frame_length,
                    pcm
                )

                keyword_index = self._porcupine.process(pcm)

                if keyword_index >= 0:
                    keyword = self.config.keywords[keyword_index]
                    self.logger.info(f"检测到唤醒词: {keyword}")
                    if self._on_wake:
                        self._on_wake()

                await asyncio.sleep(0.01)  # 让出控制权

        except Exception as e:
            self.logger.error(f"Porcupine 检测异常: {e}")

        finally:
            self._running = False

    async def stop(self):
        """停止 Porcupine 检测"""
        self._running = False

        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None

        if self._porcupine:
            try:
                self._porcupine.delete()
            except Exception:
                pass
            self._porcupine = None

        self.logger.info("Porcupine 唤醒检测停止")


class ButtonWakeDetector(WakeWordDetector):
    """
    按键唤醒检测器

    监听 GPIO 按键或键盘输入
    """

    def __init__(self, config: Optional[WakeWordConfig] = None, gpio_pin: int = None):
        super().__init__(config)
        self._gpio_pin = gpio_pin
        self._keyboard_mode = gpio_pin is None

    async def start(self):
        """启动按键检测"""
        if self._running:
            return

        self._running = True

        if self._keyboard_mode:
            await self._start_keyboard_mode()
        else:
            await self._start_gpio_mode()

    async def _start_keyboard_mode(self):
        """键盘模式（用于调试）"""
        self.logger.info("按键唤醒检测启动 (键盘模式，按 Enter 唤醒)")

        import sys
        import select

        while self._running:
            # 非阻塞检测键盘输入
            try:
                if sys.stdin in select.select([sys.stdin], [], [], 0.5)[0]:
                    line = sys.stdin.readline()
                    if line:
                        self.logger.info("检测到键盘唤醒")
                        if self._on_wake:
                            self._on_wake()
            except Exception:
                # Windows 不支持 select on stdin
                await asyncio.sleep(0.5)

    async def _start_gpio_mode(self):
        """GPIO 模式"""
        try:
            import RPi.GPIO as GPIO
        except ImportError:
            self.logger.error("RPi.GPIO 未安装")
            return

        self.logger.info(f"按键唤醒检测启动 (GPIO {self._gpio_pin})")

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        while self._running:
            if GPIO.input(self._gpio_pin) == GPIO.LOW:
                self.logger.info("检测到 GPIO 按键唤醒")
                if self._on_wake:
                    self._on_wake()
                # 防抖
                await asyncio.sleep(0.5)
            await asyncio.sleep(0.1)

        GPIO.cleanup(self._gpio_pin)

    async def stop(self):
        """停止按键检测"""
        self._running = False
        self.logger.info("按键唤醒检测停止")


def create_wake_word_detector(config: WakeWordConfig, **kwargs) -> WakeWordDetector:
    """
    工厂函数：创建唤醒词检测器

    Args:
        config: 唤醒词配置
        **kwargs: 额外参数（如 access_key, gpio_pin）

    Returns:
        唤醒词检测器实例
    """
    engine = config.engine.lower()

    if engine == "energy":
        return EnergyWakeWordDetector(config)
    elif engine == "porcupine":
        access_key = kwargs.get("access_key", "")
        return PorcupineWakeWordDetector(config, access_key)
    elif engine == "button":
        gpio_pin = kwargs.get("gpio_pin")
        return ButtonWakeDetector(config, gpio_pin)
    else:
        raise ValueError(f"不支持的唤醒引擎: {engine}")
