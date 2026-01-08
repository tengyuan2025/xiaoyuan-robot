# -*- coding: utf-8 -*-
"""
ALSA 音频播放模块
适用于 RK3568 嵌入式平台
"""

import asyncio
import io
import tempfile
import os
from typing import Optional, Callable
from dataclasses import dataclass

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger


@dataclass
class PlaybackConfig:
    """播放配置"""
    device: str = "plughw:2,0"
    sample_rate: int = 24000  # TTS 默认采样率
    channels: int = 1
    bit_depth: int = 16


class AudioPlayer:
    """
    ALSA 音频播放器

    支持 PCM、MP3、OGG 等格式播放
    """

    def __init__(self, config: Optional[PlaybackConfig] = None):
        self.logger = get_logger()
        self.config = config or PlaybackConfig()

        self._playing = False
        self._process: Optional[asyncio.subprocess.Process] = None
        self._on_complete: Optional[Callable] = None
        self._interrupted = False

    async def play_pcm(self, audio_data: bytes, sample_rate: int = 24000) -> bool:
        """
        播放 PCM 音频数据

        Args:
            audio_data: PCM 音频数据
            sample_rate: 采样率

        Returns:
            是否播放成功
        """
        if self._playing:
            self.logger.warning("正在播放中，请先停止")
            return False

        self._playing = True
        self._interrupted = False

        # 使用 aplay 播放 PCM
        cmd = [
            "aplay",
            "-D", self.config.device,
            "-f", "S16_LE",
            "-r", str(sample_rate),
            "-c", str(self.config.channels),
            "-t", "raw",
            "-q",
            "-"
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await self._process.communicate(input=audio_data)
            self.logger.info(f"PCM 播放完成，数据长度: {len(audio_data)} bytes")
            return True

        except Exception as e:
            self.logger.error(f"PCM 播放失败: {e}")
            return False

        finally:
            self._playing = False
            self._process = None
            if self._on_complete and not self._interrupted:
                self._on_complete()

    async def play_mp3(self, audio_data: bytes) -> bool:
        """
        播放 MP3 音频数据

        使用 mpg123 或 ffplay 解码播放

        Args:
            audio_data: MP3 音频数据

        Returns:
            是否播放成功
        """
        if self._playing:
            self.logger.warning("正在播放中，请先停止")
            return False

        self._playing = True
        self._interrupted = False

        # 写入临时文件
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_data)
            temp_file = f.name

        try:
            # 优先使用 mpg123
            cmd = ["mpg123", "-q", "-a", self.config.device, temp_file]

            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await self._process.wait()
                self.logger.info("MP3 播放完成 (mpg123)")
                return True

            except FileNotFoundError:
                # mpg123 不可用，尝试 ffplay
                cmd = [
                    "ffplay",
                    "-nodisp",
                    "-autoexit",
                    "-loglevel", "error",
                    temp_file
                ]

                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await self._process.wait()
                self.logger.info("MP3 播放完成 (ffplay)")
                return True

        except Exception as e:
            self.logger.error(f"MP3 播放失败: {e}")
            return False

        finally:
            self._playing = False
            self._process = None
            # 清理临时文件
            try:
                os.unlink(temp_file)
            except Exception:
                pass
            if self._on_complete and not self._interrupted:
                self._on_complete()

    async def play_file(self, file_path: str) -> bool:
        """
        播放音频文件

        Args:
            file_path: 音频文件路径

        Returns:
            是否播放成功
        """
        if not os.path.exists(file_path):
            self.logger.error(f"文件不存在: {file_path}")
            return False

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".wav":
            cmd = ["aplay", "-D", self.config.device, "-q", file_path]
        elif ext == ".mp3":
            cmd = ["mpg123", "-q", "-a", self.config.device, file_path]
        elif ext in (".ogg", ".opus"):
            cmd = ["ogg123", "-q", "-d", "alsa", "-o", f"dev:{self.config.device}", file_path]
        else:
            # 通用方案使用 ffplay
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", file_path]

        if self._playing:
            self.logger.warning("正在播放中，请先停止")
            return False

        self._playing = True
        self._interrupted = False

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await self._process.wait()
            self.logger.info(f"文件播放完成: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"文件播放失败: {e}")
            return False

        finally:
            self._playing = False
            self._process = None
            if self._on_complete and not self._interrupted:
                self._on_complete()

    async def stop(self):
        """停止播放"""
        self._interrupted = True
        self._playing = False

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception as e:
                self.logger.warning(f"停止播放进程异常: {e}")
            finally:
                self._process = None

        self.logger.info("播放已停止")

    def set_on_complete(self, callback: Callable):
        """设置播放完成回调"""
        self._on_complete = callback

    def is_playing(self) -> bool:
        """检查是否正在播放"""
        return self._playing


class StreamingAudioPlayer:
    """
    流式音频播放器

    支持边接收边播放，适用于 TTS 流式输出
    """

    def __init__(self, config: Optional[PlaybackConfig] = None):
        self.logger = get_logger()
        self.config = config or PlaybackConfig()

        self._playing = False
        self._queue: asyncio.Queue = None
        self._process: Optional[asyncio.subprocess.Process] = None
        self._play_task: Optional[asyncio.Task] = None

    async def start(self, sample_rate: int = 24000):
        """启动流式播放"""
        if self._playing:
            return

        self._playing = True
        self._queue = asyncio.Queue()

        # 启动 aplay 进程
        cmd = [
            "aplay",
            "-D", self.config.device,
            "-f", "S16_LE",
            "-r", str(sample_rate),
            "-c", str(self.config.channels),
            "-t", "raw",
            "-q",
            "-"
        ]

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 启动播放任务
        self._play_task = asyncio.create_task(self._play_loop())
        self.logger.info("流式播放器启动")

    async def _play_loop(self):
        """播放循环"""
        while self._playing:
            try:
                # 等待音频数据
                chunk = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=0.5
                )

                if chunk is None:
                    # 收到结束信号
                    break

                # 写入播放进程
                if self._process and self._process.stdin:
                    self._process.stdin.write(chunk)
                    await self._process.stdin.drain()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"流式播放异常: {e}")
                break

    async def write(self, audio_data: bytes):
        """写入音频数据"""
        if self._queue and self._playing:
            await self._queue.put(audio_data)

    async def stop(self):
        """停止流式播放"""
        self._playing = False

        # 发送结束信号
        if self._queue:
            await self._queue.put(None)

        # 等待播放任务结束
        if self._play_task:
            try:
                await asyncio.wait_for(self._play_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._play_task.cancel()

        # 关闭进程
        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                await asyncio.wait_for(self._process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception as e:
                self.logger.warning(f"停止流式播放异常: {e}")
            finally:
                self._process = None

        self.logger.info("流式播放器停止")

    def is_playing(self) -> bool:
        """检查是否正在播放"""
        return self._playing
