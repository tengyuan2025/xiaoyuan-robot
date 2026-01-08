# -*- coding: utf-8 -*-
"""
Mem0 记忆服务客户端
封装 Mem0 自托管服务的 HTTP API 调用
"""

import json
import uuid
from typing import Optional, List, Dict
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger

try:
    import requests
except ImportError:
    requests = None


@dataclass
class MemoryItem:
    """记忆条目"""
    id: str
    memory: str
    user_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    score: Optional[float] = None


@dataclass
class Mem0Config:
    """Mem0 配置"""
    base_url: str = "http://tenyuan.tech:9000"
    timeout: int = 30
    enabled: bool = True
    search_top_k: int = 5


class Mem0Client:
    """
    Mem0 API 客户端

    提供记忆的增删改查功能
    """

    def __init__(self, config: Mem0Config = None):
        self.logger = get_logger()
        self.config = config or Mem0Config()

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """发送 HTTP 请求"""
        if requests is None:
            self.logger.error("requests 未安装")
            return None

        if not self.config.enabled:
            return None

        url = f"{self.config.base_url.rstrip('/')}{endpoint}"
        kwargs.setdefault('timeout', self.config.timeout)
        kwargs.setdefault('headers', {'Content-Type': 'application/json'})

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.Timeout:
            self.logger.warning(f"Mem0 请求超时: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Mem0 连接失败: {self.config.base_url}")
            return None
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Mem0 HTTP 错误: {e}")
            return None
        except json.JSONDecodeError:
            self.logger.error("Mem0 响应解析失败")
            return None

    def health_check(self) -> bool:
        """检查服务健康状态"""
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
            messages: 对话消息列表
            metadata: 可选的元数据
        """
        payload = {
            "messages": messages,
            "user_id": user_id
        }
        if metadata:
            payload["metadata"] = metadata

        result = self._request('POST', '/api/v1/memories/add', json=payload)
        if result:
            self.logger.debug(f"Mem0 添加记忆成功: user={user_id}")
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
        """
        payload = {
            "query": query,
            "user_id": user_id,
            "top_k": top_k or self.config.search_top_k
        }

        result = self._request('POST', '/api/v1/memories/search', json=payload)
        if not result:
            return []

        memories = []
        items = result if isinstance(result, list) else result.get('results', result.get('memories', []))

        for item in items:
            memories.append(MemoryItem(
                id=item.get('id', ''),
                memory=item.get('memory', item.get('content', '')),
                user_id=user_id,
                score=item.get('score', item.get('similarity'))
            ))

        self.logger.debug(f"Mem0 搜索到 {len(memories)} 条相关记忆")
        return memories

    def get_user_memories(self, user_id: str) -> List[MemoryItem]:
        """获取用户的所有记忆"""
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
        """删除指定记忆"""
        payload = {"memory_id": memory_id}
        result = self._request('POST', '/api/v1/memories/delete', json=payload)
        return result is not None

    def update_memory(self, memory_id: str, new_content: str) -> bool:
        """更新记忆内容"""
        payload = {
            "memory_id": memory_id,
            "data": new_content
        }
        result = self._request('POST', '/api/v1/memories/update', json=payload)
        return result is not None

    @staticmethod
    def generate_temp_user_id() -> str:
        """生成临时用户 ID"""
        return f"temp_{uuid.uuid4().hex[:8]}"

    def migrate_user_memories(
        self,
        from_user_id: str,
        to_user_id: str
    ) -> int:
        """迁移用户记忆（用于临时用户确认身份后）"""
        memories = self.get_user_memories(from_user_id)
        if not memories:
            return 0

        migrated = 0
        for mem in memories:
            result = self.add_memory(
                to_user_id,
                [{"role": "system", "content": mem.memory}]
            )
            if result:
                self.delete_memory(mem.id)
                migrated += 1

        self.logger.info(f"Mem0 迁移记忆: {from_user_id} -> {to_user_id}, 共 {migrated} 条")
        return migrated

    def build_context(
        self,
        user_id: str,
        query: str,
        threshold: float = 0.3
    ) -> str:
        """
        构建记忆上下文

        Args:
            user_id: 用户 ID
            query: 当前用户输入
            threshold: 相似度阈值

        Returns:
            格式化的记忆上下文
        """
        memories = self.search_memory(user_id, query)

        # 过滤低相似度记忆
        relevant = [m for m in memories if m.score and m.score >= threshold]

        if not relevant:
            return ""

        context_parts = ["以下是关于该用户的一些记忆信息："]
        for mem in relevant:
            context_parts.append(f"- {mem.memory}")

        return "\n".join(context_parts)


# 全局单例
_mem0_client: Optional[Mem0Client] = None


def get_mem0_client(config: Mem0Config = None) -> Mem0Client:
    """获取 Mem0 客户端单例"""
    global _mem0_client
    if _mem0_client is None:
        _mem0_client = Mem0Client(config)
    return _mem0_client
