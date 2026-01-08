# -*- coding: utf-8 -*-
"""
Mem0 API 客户端

封装 Mem0 自托管服务的 HTTP API 调用，提供记忆的增删改查功能。
"""

import requests
import json
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from config import (
    MEM0_BASE_URL,
    MEM0_API_TIMEOUT,
    MEM0_ENABLED,
    MEM0_SEARCH_TOP_K
)


@dataclass
class MemoryItem:
    """记忆条目"""
    id: str
    memory: str
    user_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    score: Optional[float] = None  # 搜索时的相似度分数


class Mem0Client:
    """
    Mem0 API 客户端

    使用示例:
        client = Mem0Client()

        # 添加记忆
        client.add_memory("user123", [
            {"role": "user", "content": "我喜欢吃苹果"},
            {"role": "assistant", "content": "好的，我记住了"}
        ])

        # 搜索记忆
        memories = client.search_memory("user123", "喜欢吃什么")

        # 获取用户所有记忆
        all_memories = client.get_user_memories("user123")
    """

    def __init__(self, base_url: str = None, timeout: int = None):
        """
        初始化客户端

        Args:
            base_url: Mem0 服务地址，默认从配置读取
            timeout: 请求超时时间（秒）
        """
        self.base_url = (base_url or MEM0_BASE_URL).rstrip('/')
        self.timeout = timeout or MEM0_API_TIMEOUT
        self.enabled = MEM0_ENABLED

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            endpoint: API 端点
            **kwargs: requests 参数

        Returns:
            响应 JSON 或 None
        """
        if not self.enabled:
            print("[Mem0] 服务未启用")
            return None

        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('headers', {'Content-Type': 'application/json'})

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.Timeout:
            print(f"[Mem0] 请求超时: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"[Mem0] 连接失败: {self.base_url}")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"[Mem0] HTTP 错误: {e}")
            return None
        except json.JSONDecodeError:
            print(f"[Mem0] 响应解析失败")
            return None

    def health_check(self) -> bool:
        """
        检查服务健康状态

        Returns:
            服务是否可用
        """
        result = self._request('GET', '/health')
        return result is not None

    def add_memory(
        self,
        user_id: str,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        添加记忆

        Args:
            user_id: 用户 ID
            messages: 对话消息列表，格式: [{"role": "user/assistant", "content": "..."}]
            metadata: 可选的元数据

        Returns:
            添加结果
        """
        payload = {
            "messages": messages,
            "user_id": user_id
        }
        if metadata:
            payload["metadata"] = metadata

        result = self._request('POST', '/api/v1/memories/add', json=payload)
        if result:
            print(f"[Mem0] 添加记忆成功: user={user_id}")
        return result

    def search_memory(
        self,
        user_id: str,
        query: str,
        top_k: int = None
    ) -> List[MemoryItem]:
        """
        语义搜索记忆

        Args:
            user_id: 用户 ID
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            匹配的记忆列表
        """
        payload = {
            "query": query,
            "user_id": user_id,
            "top_k": top_k or MEM0_SEARCH_TOP_K
        }

        result = self._request('POST', '/api/v1/memories/search', json=payload)
        if not result:
            return []

        memories = []
        # 适配不同的返回格式
        items = result if isinstance(result, list) else result.get('results', result.get('memories', []))

        for item in items:
            memories.append(MemoryItem(
                id=item.get('id', ''),
                memory=item.get('memory', item.get('content', '')),
                user_id=user_id,
                score=item.get('score', item.get('similarity'))
            ))

        print(f"[Mem0] 搜索到 {len(memories)} 条相关记忆: user={user_id}, query={query[:20]}...")
        return memories

    def get_user_memories(self, user_id: str) -> List[MemoryItem]:
        """
        获取用户的所有记忆

        Args:
            user_id: 用户 ID

        Returns:
            记忆列表
        """
        result = self._request('GET', f'/api/v1/users/{user_id}/memories')
        if not result:
            return []

        memories = []
        items = result if isinstance(result, list) else result.get('memories', [])

        for item in items:
            memories.append(MemoryItem(
                id=item.get('id', ''),
                memory=item.get('memory', item.get('content', '')),
                user_id=user_id,
                created_at=item.get('created_at'),
                updated_at=item.get('updated_at')
            ))

        return memories

    def delete_memory(self, memory_id: str) -> bool:
        """
        删除指定记忆

        Args:
            memory_id: 记忆 ID

        Returns:
            是否删除成功
        """
        payload = {"memory_id": memory_id}
        result = self._request('POST', '/api/v1/memories/delete', json=payload)
        return result is not None

    def update_memory(self, memory_id: str, new_content: str) -> bool:
        """
        更新记忆内容

        Args:
            memory_id: 记忆 ID
            new_content: 新内容

        Returns:
            是否更新成功
        """
        payload = {
            "memory_id": memory_id,
            "data": new_content
        }
        result = self._request('POST', '/api/v1/memories/update', json=payload)
        return result is not None

    @staticmethod
    def generate_temp_user_id() -> str:
        """
        生成临时用户 ID

        Returns:
            临时 ID，格式: temp_<uuid>
        """
        return f"temp_{uuid.uuid4().hex[:8]}"

    def migrate_user_memories(
        self,
        from_user_id: str,
        to_user_id: str
    ) -> int:
        """
        迁移用户记忆（用于临时用户确认身份后）

        注意：Mem0 API 可能不直接支持迁移，这里通过删除+重新添加实现

        Args:
            from_user_id: 原用户 ID
            to_user_id: 目标用户 ID

        Returns:
            迁移的记忆数量
        """
        # 获取原用户的所有记忆
        memories = self.get_user_memories(from_user_id)
        if not memories:
            return 0

        migrated = 0
        for mem in memories:
            # 重新添加到新用户
            result = self.add_memory(
                to_user_id,
                [{"role": "system", "content": mem.memory}]
            )
            if result:
                # 删除原记忆
                self.delete_memory(mem.id)
                migrated += 1

        print(f"[Mem0] 迁移记忆: {from_user_id} -> {to_user_id}, 共 {migrated} 条")
        return migrated


# 全局单例
_mem0_client: Optional[Mem0Client] = None


def get_mem0_client() -> Mem0Client:
    """
    获取 Mem0 客户端单例

    Returns:
        Mem0Client 实例
    """
    global _mem0_client
    if _mem0_client is None:
        _mem0_client = Mem0Client()
    return _mem0_client


if __name__ == "__main__":
    # 测试代码
    client = Mem0Client()

    # 健康检查
    print(f"服务状态: {'正常' if client.health_check() else '异常'}")

    # 测试添加记忆
    test_user = "test_user_001"
    client.add_memory(test_user, [
        {"role": "user", "content": "我叫小明，我喜欢吃苹果"},
        {"role": "assistant", "content": "好的小明，我记住你喜欢吃苹果了"}
    ])

    # 测试搜索
    results = client.search_memory(test_user, "喜欢吃什么水果")
    for mem in results:
        print(f"  - {mem.memory} (score: {mem.score})")

    # 获取所有记忆
    all_mems = client.get_user_memories(test_user)
    print(f"用户 {test_user} 共有 {len(all_mems)} 条记忆")
