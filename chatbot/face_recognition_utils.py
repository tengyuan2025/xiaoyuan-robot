"""
人脸识别工具模块

基于 face_recognition 库实现本地人脸识别功能：
- 人脸检测和编码
- 人脸注册（保存编码到本地）
- 人脸识别（与已知人脸比对）
- 已知人脸管理

依赖: pip install face_recognition
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

try:
    import face_recognition
    import numpy as np
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    print("[FaceRecognition] 警告: 未安装 face_recognition")
    print("[FaceRecognition] 请运行: pip install face_recognition")


@dataclass
class FaceInfo:
    """人脸信息"""
    name: str
    encoding: List[float]
    registered_at: str
    image_path: Optional[str] = None


@dataclass
class RecognitionResult:
    """识别结果"""
    name: str  # 匹配的人名，未知人脸为 "unknown"
    confidence: float  # 匹配置信度 (0-1)
    location: Tuple[int, int, int, int]  # (top, right, bottom, left)


class FaceRecognitionManager:
    """人脸识别管理器"""

    def __init__(
        self,
        encodings_path: str = None,
        tolerance: float = 0.6,
        model: str = "hog"
    ):
        """
        初始化人脸识别管理器

        Args:
            encodings_path: 人脸编码存储文件路径
            tolerance: 人脸匹配容差（越小越严格，建议0.4-0.6）
            model: 检测模型，"hog"（快速）或 "cnn"（准确但需要GPU）
        """
        if encodings_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            encodings_path = os.path.join(base_dir, "faces", "encodings.json")

        self.encodings_path = encodings_path
        self.tolerance = tolerance
        self.model = model

        # 确保目录存在
        os.makedirs(os.path.dirname(self.encodings_path), exist_ok=True)

        # 加载已有的人脸数据
        self.known_faces: List[FaceInfo] = []
        self.known_encodings: List[np.ndarray] = []
        self.known_names: List[str] = []
        self._load_encodings()

    def _load_encodings(self) -> None:
        """从JSON文件加载人脸编码"""
        if not os.path.exists(self.encodings_path):
            print(f"[FaceRecognition] 编码文件不存在，将创建新文件: {self.encodings_path}")
            return

        try:
            with open(self.encodings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            faces = data.get("faces", [])
            for face_data in faces:
                face_info = FaceInfo(
                    name=face_data["name"],
                    encoding=face_data["encoding"],
                    registered_at=face_data.get("registered_at", ""),
                    image_path=face_data.get("image_path")
                )
                self.known_faces.append(face_info)
                self.known_encodings.append(np.array(face_data["encoding"]))
                self.known_names.append(face_data["name"])

            print(f"[FaceRecognition] 已加载 {len(self.known_faces)} 个已知人脸")
        except Exception as e:
            print(f"[FaceRecognition] 加载编码文件失败: {e}")

    def _save_encodings(self) -> bool:
        """保存人脸编码到JSON文件"""
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "faces": []
            }

            for face_info in self.known_faces:
                face_dict = {
                    "name": face_info.name,
                    "encoding": face_info.encoding if isinstance(face_info.encoding, list)
                               else face_info.encoding.tolist(),
                    "registered_at": face_info.registered_at
                }
                if face_info.image_path:
                    face_dict["image_path"] = face_info.image_path
                data["faces"].append(face_dict)

            with open(self.encodings_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[FaceRecognition] 已保存 {len(self.known_faces)} 个人脸编码")
            return True
        except Exception as e:
            print(f"[FaceRecognition] 保存编码文件失败: {e}")
            return False

    def detect_faces(self, image_path: str) -> List[Tuple[int, int, int, int]]:
        """
        检测图片中的人脸位置

        Args:
            image_path: 图片文件路径

        Returns:
            人脸位置列表 [(top, right, bottom, left), ...]
        """
        if not FACE_RECOGNITION_AVAILABLE:
            print("[FaceRecognition] 错误: face_recognition 库未安装")
            return []

        try:
            image = face_recognition.load_image_file(image_path)
            face_locations = face_recognition.face_locations(image, model=self.model)
            print(f"[FaceRecognition] 检测到 {len(face_locations)} 张人脸")
            return face_locations
        except Exception as e:
            print(f"[FaceRecognition] 检测人脸失败: {e}")
            return []

    def encode_face(
        self,
        image_path: str,
        face_location: Tuple[int, int, int, int] = None
    ) -> Optional[np.ndarray]:
        """
        提取人脸编码（128维向量）

        Args:
            image_path: 图片文件路径
            face_location: 指定人脸位置，None则自动检测第一张人脸

        Returns:
            128维人脸编码向量，失败返回None
        """
        if not FACE_RECOGNITION_AVAILABLE:
            print("[FaceRecognition] 错误: face_recognition 库未安装")
            return None

        try:
            image = face_recognition.load_image_file(image_path)

            if face_location:
                face_locations = [face_location]
            else:
                face_locations = face_recognition.face_locations(image, model=self.model)

            if not face_locations:
                print("[FaceRecognition] 未检测到人脸")
                return None

            # 提取编码（只取第一张人脸）
            encodings = face_recognition.face_encodings(image, face_locations)
            if encodings:
                return encodings[0]
            return None
        except Exception as e:
            print(f"[FaceRecognition] 提取人脸编码失败: {e}")
            return None

    def register_face(
        self,
        image_path: str,
        name: str,
        encoding: np.ndarray = None
    ) -> Tuple[bool, str]:
        """
        注册新人脸

        Args:
            image_path: 图片文件路径
            name: 人名
            encoding: 预先提取的编码（可选，如果已经提取过）

        Returns:
            (成功标志, 消息)
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return False, "face_recognition 库未安装"

        # 检查是否已存在同名
        if name in self.known_names:
            return False, f"已存在名为 {name} 的人脸，请使用其他名字"

        # 提取人脸编码
        if encoding is None:
            encoding = self.encode_face(image_path)

        if encoding is None:
            return False, "未能检测到人脸，请确保脸部清晰可见"

        # 创建人脸信息
        face_info = FaceInfo(
            name=name,
            encoding=encoding.tolist(),
            registered_at=datetime.now().isoformat(),
            image_path=image_path
        )

        # 添加到列表
        self.known_faces.append(face_info)
        self.known_encodings.append(encoding)
        self.known_names.append(name)

        # 保存到文件
        if self._save_encodings():
            return True, f"已成功记住 {name}"
        else:
            # 回滚
            self.known_faces.pop()
            self.known_encodings.pop()
            self.known_names.pop()
            return False, "保存人脸数据失败"

    def register_face_with_encoding(
        self,
        encoding: np.ndarray,
        name: str
    ) -> Tuple[bool, str]:
        """
        使用预先提取的编码注册人脸（用于追问确认模式）

        Args:
            encoding: 人脸编码向量
            name: 人名

        Returns:
            (成功标志, 消息)
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return False, "face_recognition 库未安装"

        # 检查是否已存在同名
        if name in self.known_names:
            return False, f"已存在名为 {name} 的人脸，请使用其他名字"

        # 创建人脸信息
        face_info = FaceInfo(
            name=name,
            encoding=encoding.tolist() if isinstance(encoding, np.ndarray) else encoding,
            registered_at=datetime.now().isoformat()
        )

        # 添加到列表
        self.known_faces.append(face_info)
        if isinstance(encoding, np.ndarray):
            self.known_encodings.append(encoding)
        else:
            self.known_encodings.append(np.array(encoding))
        self.known_names.append(name)

        # 保存到文件
        if self._save_encodings():
            return True, f"已成功记住 {name}"
        else:
            # 回滚
            self.known_faces.pop()
            self.known_encodings.pop()
            self.known_names.pop()
            return False, "保存人脸数据失败"

    def recognize_faces(self, image_path: str) -> List[RecognitionResult]:
        """
        识别图片中的人脸

        Args:
            image_path: 图片文件路径

        Returns:
            识别结果列表
        """
        if not FACE_RECOGNITION_AVAILABLE:
            print("[FaceRecognition] 错误: face_recognition 库未安装")
            return []

        if not self.known_encodings:
            print("[FaceRecognition] 没有已注册的人脸数据")
            return []

        try:
            image = face_recognition.load_image_file(image_path)
            face_locations = face_recognition.face_locations(image, model=self.model)

            if not face_locations:
                print("[FaceRecognition] 未检测到人脸")
                return []

            face_encodings = face_recognition.face_encodings(image, face_locations)

            results = []
            for encoding, location in zip(face_encodings, face_locations):
                # 计算与所有已知人脸的距离
                distances = face_recognition.face_distance(
                    self.known_encodings, encoding
                )

                # 找到最佳匹配
                best_idx = np.argmin(distances)
                best_distance = distances[best_idx]

                if best_distance <= self.tolerance:
                    name = self.known_names[best_idx]
                    confidence = 1 - best_distance
                else:
                    name = "unknown"
                    confidence = 0.0

                results.append(RecognitionResult(
                    name=name,
                    confidence=confidence,
                    location=location
                ))

                print(f"[FaceRecognition] 识别结果: {name} (置信度: {confidence:.2f})")

            return results
        except Exception as e:
            print(f"[FaceRecognition] 识别人脸失败: {e}")
            return []

    def delete_face(self, name: str) -> bool:
        """
        删除已注册的人脸

        Args:
            name: 人名

        Returns:
            是否删除成功
        """
        if name not in self.known_names:
            print(f"[FaceRecognition] 未找到名为 {name} 的人脸")
            return False

        idx = self.known_names.index(name)
        self.known_faces.pop(idx)
        self.known_encodings.pop(idx)
        self.known_names.pop(idx)

        if self._save_encodings():
            print(f"[FaceRecognition] 已删除 {name}")
            return True
        return False

    def list_faces(self) -> List[str]:
        """
        列出所有已注册的人名

        Returns:
            人名列表
        """
        return self.known_names.copy()

    def has_registered_faces(self) -> bool:
        """检查是否有已注册的人脸"""
        return len(self.known_faces) > 0

    def get_face_count(self) -> int:
        """获取已注册的人脸数量"""
        return len(self.known_faces)


def check_face_recognition_available() -> Tuple[bool, str]:
    """
    检查 face_recognition 库是否可用

    Returns:
        (是否可用, 状态消息)
    """
    if FACE_RECOGNITION_AVAILABLE:
        return True, "face_recognition 库已安装"
    else:
        return False, "请安装 face_recognition: pip install face_recognition"
