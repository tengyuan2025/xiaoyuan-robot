# -*- coding: utf-8 -*-
"""
声纹识别工具模块

基于 Resemblyzer 库实现本地声纹识别功能：
- 从音频中提取说话人嵌入向量（256维 d-vector）
- 声纹注册（保存嵌入向量到本地）
- 声纹匹配（与已知声纹库对比）
- 已知说话人管理

依赖: pip install resemblyzer
"""

import os
import json
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass

import numpy as np

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    from resemblyzer.audio import sampling_rate as RESEMBLYZER_SR
    RESEMBLYZER_AVAILABLE = True
except ImportError:
    RESEMBLYZER_AVAILABLE = False
    RESEMBLYZER_SR = 16000
    print("[SpeakerRecognition] 警告: 未安装 resemblyzer")
    print("[SpeakerRecognition] 请运行: pip install resemblyzer")


@dataclass
class SpeakerInfo:
    """说话人信息"""
    name: str
    embedding: List[float]  # 256维向量
    registered_at: str
    audio_samples: int = 1  # 累积的音频样本数


class SpeakerRecognitionManager:
    """声纹识别管理器"""

    def __init__(
        self,
        data_path: str = None,
        similarity_threshold: float = 0.80,
        min_audio_duration: float = 1.0
    ):
        """
        初始化声纹识别管理器

        Args:
            data_path: 声纹数据存储文件路径
            similarity_threshold: 匹配相似度阈值（余弦相似度，0-1，越高越严格）
            min_audio_duration: 最小有效音频时长（秒）
        """
        if data_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_path = os.path.join(base_dir, "voiceprints.json")

        self.data_path = data_path
        self.similarity_threshold = similarity_threshold
        self.min_audio_duration = min_audio_duration

        # 声纹编码器（延迟加载）
        self._encoder: Optional[VoiceEncoder] = None

        # 加载已有的声纹数据
        self.known_speakers: List[SpeakerInfo] = []
        self.known_embeddings: List[np.ndarray] = []
        self.known_names: List[str] = []
        self._load_voiceprints()

    @property
    def encoder(self) -> Optional['VoiceEncoder']:
        """延迟加载声纹编码器"""
        if self._encoder is None and RESEMBLYZER_AVAILABLE:
            print("[SpeakerRecognition] 正在加载声纹编码器模型...")
            self._encoder = VoiceEncoder()
            print("[SpeakerRecognition] 声纹编码器加载完成")
        return self._encoder

    def _load_voiceprints(self) -> None:
        """从JSON文件加载声纹数据"""
        if not os.path.exists(self.data_path):
            print(f"[SpeakerRecognition] 声纹文件不存在，将创建新文件: {self.data_path}")
            return

        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            speakers = data.get("speakers", [])
            for speaker_data in speakers:
                speaker_info = SpeakerInfo(
                    name=speaker_data["name"],
                    embedding=speaker_data["embedding"],
                    registered_at=speaker_data.get("registered_at", ""),
                    audio_samples=speaker_data.get("audio_samples", 1)
                )
                self.known_speakers.append(speaker_info)
                self.known_embeddings.append(np.array(speaker_data["embedding"]))
                self.known_names.append(speaker_data["name"])

            print(f"[SpeakerRecognition] 已加载 {len(self.known_speakers)} 个已知声纹")
        except Exception as e:
            print(f"[SpeakerRecognition] 加载声纹文件失败: {e}")

    def _save_voiceprints(self) -> bool:
        """保存声纹数据到JSON文件"""
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "speakers": []
            }

            for speaker_info in self.known_speakers:
                speaker_dict = {
                    "name": speaker_info.name,
                    "embedding": speaker_info.embedding if isinstance(speaker_info.embedding, list)
                                 else speaker_info.embedding.tolist(),
                    "registered_at": speaker_info.registered_at,
                    "audio_samples": speaker_info.audio_samples
                }
                data["speakers"].append(speaker_dict)

            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[SpeakerRecognition] 已保存 {len(self.known_speakers)} 个声纹")
            return True
        except Exception as e:
            print(f"[SpeakerRecognition] 保存声纹文件失败: {e}")
            return False

    def extract_embedding(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000
    ) -> Optional[np.ndarray]:
        """
        从音频数据中提取声纹嵌入向量

        Args:
            audio_bytes: PCM音频字节数据（16-bit, mono）
            sample_rate: 采样率

        Returns:
            256维嵌入向量，失败返回None
        """
        if not RESEMBLYZER_AVAILABLE:
            print("[SpeakerRecognition] 错误: resemblyzer 库未安装")
            return None

        if self.encoder is None:
            print("[SpeakerRecognition] 错误: 声纹编码器加载失败")
            return None

        try:
            # 将PCM字节转换为float32数组
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float = audio_int16.astype(np.float32) / 32768.0

            # 检查音频时长
            duration = len(audio_float) / sample_rate
            if duration < self.min_audio_duration:
                print(f"[SpeakerRecognition] 音频太短 ({duration:.2f}s < {self.min_audio_duration}s)")
                return None

            # 如果采样率不匹配，需要重采样
            if sample_rate != RESEMBLYZER_SR:
                # 简单的重采样（线性插值）
                ratio = RESEMBLYZER_SR / sample_rate
                new_length = int(len(audio_float) * ratio)
                audio_float = np.interp(
                    np.linspace(0, len(audio_float) - 1, new_length),
                    np.arange(len(audio_float)),
                    audio_float
                )

            # 预处理音频（VAD + 归一化）
            wav = preprocess_wav(audio_float)

            if len(wav) == 0:
                print("[SpeakerRecognition] 预处理后音频为空（可能全是静音）")
                return None

            # 提取嵌入向量
            embedding = self.encoder.embed_utterance(wav)
            print(f"[SpeakerRecognition] 成功提取声纹 (shape: {embedding.shape})")
            return embedding

        except Exception as e:
            print(f"[SpeakerRecognition] 提取声纹失败: {e}")
            return None

    def match_speaker(
        self,
        embedding: np.ndarray,
        threshold: float = None
    ) -> Tuple[Optional[str], float]:
        """
        将声纹与已知说话人库进行匹配

        Args:
            embedding: 256维嵌入向量
            threshold: 匹配阈值（覆盖默认值）

        Returns:
            (说话人名字或None, 最高相似度)
        """
        if threshold is None:
            threshold = self.similarity_threshold

        if not self.known_embeddings:
            print("[SpeakerRecognition] 声纹库为空")
            return None, 0.0

        try:
            # 计算余弦相似度
            embedding_norm = embedding / np.linalg.norm(embedding)
            similarities = []

            for known_emb in self.known_embeddings:
                known_norm = known_emb / np.linalg.norm(known_emb)
                sim = np.dot(embedding_norm, known_norm)
                similarities.append(sim)

            # 找到最佳匹配
            best_idx = np.argmax(similarities)
            best_similarity = similarities[best_idx]

            print(f"[SpeakerRecognition] 最佳匹配: {self.known_names[best_idx]} "
                  f"(相似度: {best_similarity:.3f}, 阈值: {threshold})")

            if best_similarity >= threshold:
                return self.known_names[best_idx], best_similarity
            else:
                return None, best_similarity

        except Exception as e:
            print(f"[SpeakerRecognition] 匹配失败: {e}")
            return None, 0.0

    def register_speaker(
        self,
        name: str,
        embedding: np.ndarray
    ) -> Tuple[bool, str]:
        """
        注册新说话人

        Args:
            name: 说话人名字
            embedding: 256维嵌入向量

        Returns:
            (成功标志, 消息)
        """
        if not RESEMBLYZER_AVAILABLE:
            return False, "resemblyzer 库未安装"

        # 检查是否已存在同名
        if name in self.known_names:
            # 更新现有声纹（累积平均）
            idx = self.known_names.index(name)
            speaker = self.known_speakers[idx]
            old_emb = self.known_embeddings[idx]

            # 加权平均合并声纹
            n = speaker.audio_samples
            new_emb = (old_emb * n + embedding) / (n + 1)
            new_emb = new_emb / np.linalg.norm(new_emb)  # 归一化

            # 更新数据
            speaker.embedding = new_emb.tolist()
            speaker.audio_samples = n + 1
            self.known_embeddings[idx] = new_emb

            if self._save_voiceprints():
                return True, f"已更新 {name} 的声纹 (样本数: {n + 1})"
            return False, "保存声纹失败"

        # 创建新说话人
        speaker_info = SpeakerInfo(
            name=name,
            embedding=embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
            registered_at=datetime.now().isoformat(),
            audio_samples=1
        )

        # 添加到列表
        self.known_speakers.append(speaker_info)
        self.known_embeddings.append(
            embedding if isinstance(embedding, np.ndarray) else np.array(embedding)
        )
        self.known_names.append(name)

        # 保存到文件
        if self._save_voiceprints():
            return True, f"已成功记住 {name} 的声音"
        else:
            # 回滚
            self.known_speakers.pop()
            self.known_embeddings.pop()
            self.known_names.pop()
            return False, "保存声纹数据失败"

    def delete_speaker(self, name: str) -> bool:
        """删除已注册的说话人"""
        if name not in self.known_names:
            print(f"[SpeakerRecognition] 未找到名为 {name} 的声纹")
            return False

        idx = self.known_names.index(name)
        self.known_speakers.pop(idx)
        self.known_embeddings.pop(idx)
        self.known_names.pop(idx)

        if self._save_voiceprints():
            print(f"[SpeakerRecognition] 已删除 {name}")
            return True
        return False

    def list_speakers(self) -> List[str]:
        """列出所有已注册的说话人"""
        return self.known_names.copy()

    def has_registered_speakers(self) -> bool:
        """检查是否有已注册的声纹"""
        return len(self.known_speakers) > 0

    def get_speaker_count(self) -> int:
        """获取已注册的说话人数量"""
        return len(self.known_speakers)


def check_resemblyzer_available() -> Tuple[bool, str]:
    """
    检查 resemblyzer 库是否可用

    Returns:
        (是否可用, 状态消息)
    """
    if RESEMBLYZER_AVAILABLE:
        return True, "resemblyzer 库已安装"
    else:
        return False, "请安装 resemblyzer: pip install resemblyzer"
