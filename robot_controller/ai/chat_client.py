# -*- coding: utf-8 -*-
"""
对话模型客户端 (Chat)
Doubao-Seed-1.6 推理模型，HTTP 流式
"""

import json
import time
from typing import Optional, Callable, List, Dict, AsyncGenerator
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

try:
    import requests
except ImportError:
    requests = None

try:
    import aiohttp
except ImportError:
    aiohttp = None


@dataclass
class ChatConfig:
    """Chat 配置"""
    api_url: str = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    api_key: str = ""
    model_name: str = "doubao-seed-1-6-251015"
    max_tokens: int = 4096
    temperature: float = 0.7
    stream: bool = True
    thinking: Optional[str] = None  # 思考模式类型
    timeout: int = 60
    max_retries: int = 3


@dataclass
class ChatMessage:
    """对话消息"""
    role: str  # system, user, assistant
    content: str


class ChatClient:
    """
    对话模型客户端

    基于 Doubao-Seed-1.6 HTTP API
    支持流式和非流式两种模式
    """

    def __init__(self, config: ChatConfig):
        self.logger = get_logger()
        self.config = config
        self._history: List[Dict[str, str]] = []

        # 回调函数
        self._on_chunk: Optional[Callable[[str], None]] = None
        self._on_complete: Optional[Callable[[str], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None

    def set_callbacks(
        self,
        on_chunk: Callable[[str], None] = None,
        on_complete: Callable[[str], None] = None,
        on_error: Callable[[str], None] = None
    ):
        """设置回调函数"""
        self._on_chunk = on_chunk
        self._on_complete = on_complete
        self._on_error = on_error

    def add_to_history(self, role: str, content: str):
        """添加消息到历史"""
        self._history.append({"role": role, "content": content})

    def clear_history(self):
        """清空历史"""
        self._history.clear()

    def get_history(self) -> List[Dict[str, str]]:
        """获取历史"""
        return self._history.copy()

    def chat(
        self,
        user_input: str,
        system_prompt: Optional[str] = None,
        memory_context: Optional[str] = None,
        image_base64: Optional[str] = None
    ) -> Optional[str]:
        """
        同步对话（流式返回）

        Args:
            user_input: 用户输入
            system_prompt: 系统提示词
            memory_context: 记忆上下文
            image_base64: 图片 Base64 编码（用于图文分析）

        Returns:
            AI 完整回复
        """
        if requests is None:
            raise ImportError("requests 未安装，请运行: pip install requests")

        if not user_input.strip():
            return None

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        # 构建消息列表
        messages = []

        # 系统提示词
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 记忆上下文
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        # 添加历史对话（只保留最近2轮）
        recent_history = self._history[-4:] if len(self._history) > 4 else self._history
        messages.extend(recent_history)

        # 添加当前用户输入
        if image_base64:
            # 图文分析模式
            prompt = self._build_image_prompt(user_input, image_base64)
            messages.append({"role": "user", "content": prompt})
        else:
            messages.append({"role": "user", "content": user_input})

        data = {
            "model": self.config.model_name,
            "messages": messages,
            "max_completion_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": self.config.stream
        }

        if self.config.thinking:
            data["thinking"] = {"type": self.config.thinking}

        # 指数退避重试
        for attempt in range(self.config.max_retries):
            try:
                response = requests.post(
                    self.config.api_url,
                    headers=headers,
                    data=json.dumps(data),
                    timeout=self.config.timeout,
                    stream=self.config.stream
                )

                # 处理 429 限流错误
                if response.status_code == 429:
                    if attempt < self.config.max_retries - 1:
                        delay = 1.0 * (2 ** attempt)
                        self.logger.warning(f"Chat 限流，等待 {delay:.1f}s 后重试...")
                        time.sleep(delay)
                        continue
                    else:
                        self.logger.error("Chat 限流重试次数已达上限")
                        return None

                response.raise_for_status()
                break

            except requests.exceptions.Timeout:
                self.logger.error("Chat 请求超时")
                return None
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Chat 请求异常: {e}")
                return None

        # 处理响应
        try:
            if self.config.stream:
                return self._process_stream_response(response, user_input)
            else:
                return self._process_normal_response(response, user_input)
        except Exception as e:
            self.logger.error(f"Chat 处理响应异常: {e}")
            if self._on_error:
                self._on_error(str(e))
            return None

    def _build_image_prompt(self, user_question: str, image_base64: str) -> str:
        """构建图文分析提示词"""
        return f"""请根据以下图片回答用户的问题。

用户问题：{user_question}

图片数据（Base64编码）：
{image_base64}

请仔细分析图片内容，然后用简洁的语言回答用户的问题。"""

    def _process_stream_response(
        self,
        response,
        user_input: str
    ) -> Optional[str]:
        """处理流式响应"""
        full_reply = ""

        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')

                if not line_str.strip() or line_str.startswith(':'):
                    continue

                if line_str.startswith('data: '):
                    line_str = line_str[6:]

                if line_str.strip() == '[DONE]':
                    break

                try:
                    res = json.loads(line_str)

                    if res.get("error"):
                        error_msg = res.get("error", {}).get("message", "未知错误")
                        self.logger.error(f"Chat 流式响应错误: {error_msg}")
                        continue

                    choices = res.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        chunk = delta.get("content", "")
                        if chunk:
                            full_reply += chunk
                            if self._on_chunk:
                                self._on_chunk(chunk)

                except json.JSONDecodeError:
                    continue

        if full_reply:
            # 更新历史
            self.add_to_history("user", user_input)
            self.add_to_history("assistant", full_reply)

            if self._on_complete:
                self._on_complete(full_reply)

            self.logger.info(f"Chat 完成，回复长度: {len(full_reply)}")

        return full_reply if full_reply else None

    def _process_normal_response(
        self,
        response,
        user_input: str
    ) -> Optional[str]:
        """处理非流式响应"""
        try:
            res = response.json()

            if res.get("error"):
                error_msg = res.get("error", {}).get("message", "未知错误")
                self.logger.error(f"Chat 响应错误: {error_msg}")
                return None

            choices = res.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                if content:
                    # 更新历史
                    self.add_to_history("user", user_input)
                    self.add_to_history("assistant", content)

                    if self._on_chunk:
                        self._on_chunk(content)
                    if self._on_complete:
                        self._on_complete(content)

                    self.logger.info(f"Chat 完成，回复长度: {len(content)}")
                    return content

        except Exception as e:
            self.logger.error(f"Chat 解析响应异常: {e}")

        return None

    async def chat_async(
        self,
        user_input: str,
        system_prompt: Optional[str] = None,
        memory_context: Optional[str] = None
    ) -> Optional[str]:
        """
        异步对话

        Args:
            user_input: 用户输入
            system_prompt: 系统提示词
            memory_context: 记忆上下文

        Returns:
            AI 完整回复
        """
        if aiohttp is None:
            raise ImportError("aiohttp 未安装，请运行: pip install aiohttp")

        if not user_input.strip():
            return None

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        # 构建消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        recent_history = self._history[-4:] if len(self._history) > 4 else self._history
        messages.extend(recent_history)
        messages.append({"role": "user", "content": user_input})

        data = {
            "model": self.config.model_name,
            "messages": messages,
            "max_completion_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": self.config.stream
        }

        full_reply = ""

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.api_url,
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Chat 请求失败: {response.status} - {error_text}")
                    return None

                if self.config.stream:
                    async for line in response.content:
                        line_str = line.decode('utf-8').strip()

                        if not line_str or line_str.startswith(':'):
                            continue

                        if line_str.startswith('data: '):
                            line_str = line_str[6:]

                        if line_str == '[DONE]':
                            break

                        try:
                            res = json.loads(line_str)
                            choices = res.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                chunk = delta.get("content", "")
                                if chunk:
                                    full_reply += chunk
                                    if self._on_chunk:
                                        self._on_chunk(chunk)
                        except json.JSONDecodeError:
                            continue
                else:
                    res = await response.json()
                    choices = res.get("choices", [])
                    if choices:
                        message = choices[0].get("message", {})
                        full_reply = message.get("content", "")

        if full_reply:
            self.add_to_history("user", user_input)
            self.add_to_history("assistant", full_reply)
            if self._on_complete:
                self._on_complete(full_reply)

        return full_reply if full_reply else None
