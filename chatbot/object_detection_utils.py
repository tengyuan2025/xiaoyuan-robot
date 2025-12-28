"""
物体检测工具模块

基于 YOLOv8 实现本地物体检测功能：
- 检测图片中的物体
- 返回物体类别和置信度
- 支持 80 种常见物体

依赖: pip install ultralytics
"""

import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("[ObjectDetection] 警告: 未安装 ultralytics")
    print("[ObjectDetection] 请运行: pip install ultralytics")


@dataclass
class DetectionResult:
    """检测结果"""
    class_name: str      # 物体类别名称
    confidence: float    # 置信度 (0-1)
    bbox: Tuple[int, int, int, int]  # 边界框 (x1, y1, x2, y2)


# YOLO COCO 类别名称（中英文对照）
COCO_CLASSES_CN = {
    'person': '人',
    'bicycle': '自行车',
    'car': '汽车',
    'motorcycle': '摩托车',
    'airplane': '飞机',
    'bus': '公交车',
    'train': '火车',
    'truck': '卡车',
    'boat': '船',
    'traffic light': '红绿灯',
    'fire hydrant': '消防栓',
    'stop sign': '停止标志',
    'parking meter': '停车计时器',
    'bench': '长椅',
    'bird': '鸟',
    'cat': '猫',
    'dog': '狗',
    'horse': '马',
    'sheep': '羊',
    'cow': '牛',
    'elephant': '大象',
    'bear': '熊',
    'zebra': '斑马',
    'giraffe': '长颈鹿',
    'backpack': '背包',
    'umbrella': '雨伞',
    'handbag': '手提包',
    'tie': '领带',
    'suitcase': '行李箱',
    'frisbee': '飞盘',
    'skis': '滑雪板',
    'snowboard': '单板滑雪',
    'sports ball': '球',
    'kite': '风筝',
    'baseball bat': '棒球棒',
    'baseball glove': '棒球手套',
    'skateboard': '滑板',
    'surfboard': '冲浪板',
    'tennis racket': '网球拍',
    'bottle': '瓶子',
    'wine glass': '酒杯',
    'cup': '杯子',
    'fork': '叉子',
    'knife': '刀',
    'spoon': '勺子',
    'bowl': '碗',
    'banana': '香蕉',
    'apple': '苹果',
    'sandwich': '三明治',
    'orange': '橙子',
    'broccoli': '西兰花',
    'carrot': '胡萝卜',
    'hot dog': '热狗',
    'pizza': '披萨',
    'donut': '甜甜圈',
    'cake': '蛋糕',
    'chair': '椅子',
    'couch': '沙发',
    'potted plant': '盆栽',
    'bed': '床',
    'dining table': '餐桌',
    'toilet': '马桶',
    'tv': '电视',
    'laptop': '笔记本电脑',
    'mouse': '鼠标',
    'remote': '遥控器',
    'keyboard': '键盘',
    'cell phone': '手机',
    'microwave': '微波炉',
    'oven': '烤箱',
    'toaster': '烤面包机',
    'sink': '水槽',
    'refrigerator': '冰箱',
    'book': '书',
    'clock': '时钟',
    'vase': '花瓶',
    'scissors': '剪刀',
    'teddy bear': '泰迪熊',
    'hair drier': '吹风机',
    'toothbrush': '牙刷'
}


class ObjectDetector:
    """物体检测器"""

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.5,
        use_chinese: bool = True
    ):
        """
        初始化物体检测器

        Args:
            model_name: YOLO 模型名称（yolov8n/s/m/l/x.pt）
                - yolov8n: 最快，精度较低
                - yolov8s: 快速，精度适中
                - yolov8m: 中等速度，精度较高
            confidence_threshold: 置信度阈值
            use_chinese: 是否使用中文类别名称
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.use_chinese = use_chinese
        self.model = None

        if YOLO_AVAILABLE:
            self._load_model()

    def _load_model(self):
        """加载 YOLO 模型"""
        try:
            print(f"[ObjectDetection] 正在加载模型: {self.model_name}")
            self.model = YOLO(self.model_name)
            print(f"[ObjectDetection] 模型加载成功")
        except Exception as e:
            print(f"[ObjectDetection] 模型加载失败: {e}")
            self.model = None

    def detect(self, image_path: str) -> List[DetectionResult]:
        """
        检测图片中的物体

        Args:
            image_path: 图片文件路径

        Returns:
            检测结果列表
        """
        if not YOLO_AVAILABLE:
            print("[ObjectDetection] 错误: ultralytics 库未安装")
            return []

        if self.model is None:
            print("[ObjectDetection] 错误: 模型未加载")
            return []

        if not os.path.exists(image_path):
            print(f"[ObjectDetection] 错误: 图片不存在: {image_path}")
            return []

        try:
            # 运行检测
            results = self.model(image_path, verbose=False)

            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for i in range(len(boxes)):
                    conf = float(boxes.conf[i])
                    if conf < self.confidence_threshold:
                        continue

                    cls_id = int(boxes.cls[i])
                    cls_name = result.names[cls_id]

                    # 转换为中文
                    if self.use_chinese and cls_name in COCO_CLASSES_CN:
                        cls_name = COCO_CLASSES_CN[cls_name]

                    # 获取边界框
                    bbox = boxes.xyxy[i].tolist()
                    bbox = tuple(int(x) for x in bbox)

                    detections.append(DetectionResult(
                        class_name=cls_name,
                        confidence=conf,
                        bbox=bbox
                    ))

            print(f"[ObjectDetection] 检测到 {len(detections)} 个物体")
            return detections

        except Exception as e:
            print(f"[ObjectDetection] 检测失败: {e}")
            return []

    def detect_and_describe(self, image_path: str) -> str:
        """
        检测图片中的物体并生成描述

        Args:
            image_path: 图片文件路径

        Returns:
            物体描述文本
        """
        detections = self.detect(image_path)

        if not detections:
            return "未检测到明显的物体"

        # 统计各类物体数量
        object_counts = {}
        for det in detections:
            name = det.class_name
            if name in object_counts:
                object_counts[name] += 1
            else:
                object_counts[name] = 1

        # 生成描述
        descriptions = []
        for name, count in object_counts.items():
            if count == 1:
                descriptions.append(name)
            else:
                descriptions.append(f"{count}个{name}")

        return "、".join(descriptions)


def check_yolo_available() -> Tuple[bool, str]:
    """
    检查 YOLO 是否可用

    Returns:
        (是否可用, 状态消息)
    """
    if YOLO_AVAILABLE:
        return True, "YOLO 库已安装"
    else:
        return False, "请安装 ultralytics: pip install ultralytics"
