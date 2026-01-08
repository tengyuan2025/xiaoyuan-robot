# -*- coding: utf-8 -*-
"""
深度相机模块 (Nebula410)
Deptrum Nebula410 通过 MIPI2USB 转接板连接

注意：Deptrum SDK 是 C++ 库，这里通过 OpenCV UVC 模式访问
或通过 ctypes 调用 SDK（需要安装 SDK）
"""

import os
import sys
import subprocess
from typing import Optional, Tuple, Dict, Any
import numpy as np

# 延迟导入 OpenCV
cv2 = None


def _import_cv2():
    global cv2
    if cv2 is None:
        try:
            import cv2 as _cv2
            cv2 = _cv2
        except ImportError:
            raise ImportError("请安装 opencv-python: pip install opencv-python")


class DepthCamera:
    """
    Nebula410 深度相机控制类

    支持两种模式：
    1. UVC 模式 - 通过 OpenCV 直接访问（简单但功能有限）
    2. SDK 模式 - 通过 Deptrum SDK 访问（功能完整）
    """

    def __init__(self, device_id: int = 0, use_sdk: bool = False):
        """
        初始化深度相机

        Args:
            device_id: 视频设备ID（UVC模式）或相机索引（SDK模式）
            use_sdk: 是否使用 Deptrum SDK
        """
        self.device_id = device_id
        self.use_sdk = use_sdk
        self.cap = None
        self.pipeline = None
        self.is_open = False

    def open(self) -> bool:
        """打开相机"""
        if self.use_sdk:
            return self._open_sdk()
        else:
            return self._open_uvc()

    def _open_uvc(self) -> bool:
        """通过 OpenCV UVC 模式打开"""
        _import_cv2()

        # 尝试多个设备ID
        device_ids = [self.device_id] if self.device_id >= 0 else list(range(10))

        for dev_id in device_ids:
            try:
                cap = cv2.VideoCapture(dev_id, cv2.CAP_V4L2)
                if cap.isOpened():
                    # 设置分辨率
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

                    # 尝试读取一帧测试
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        self.cap = cap
                        self.device_id = dev_id
                        self.is_open = True
                        print(f"深度相机已通过 UVC 模式打开 (设备: /dev/video{dev_id})")
                        return True
                    cap.release()
            except Exception as e:
                continue

        print("无法打开深度相机 (UVC 模式)")
        return False

    def _open_sdk(self) -> bool:
        """通过 Deptrum SDK 打开（需要安装SDK）"""
        try:
            # 尝试导入 SDK Python 绑定（如果存在）
            # import deptrum as dt
            # self.pipeline = dt.Pipeline()
            # self.pipeline.start()
            print("Deptrum SDK Python 绑定未安装，请使用 UVC 模式")
            return False
        except ImportError:
            print("Deptrum SDK 未安装，请使用 UVC 模式或安装 SDK")
            return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """读取一帧图像"""
        if not self.is_open:
            return False, None

        if self.cap is not None:
            return self.cap.read()

        return False, None

    def read_depth(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        读取深度图像

        注意：UVC模式下返回的是RGB图像，不是真正的深度图
        需要SDK模式才能获取真正的深度数据
        """
        if not self.is_open:
            return False, None

        ret, frame = self.read_frame()
        if ret and frame is not None:
            # UVC模式下转换为灰度图模拟深度
            _import_cv2()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return True, gray

        return False, None

    def get_info(self) -> Dict[str, Any]:
        """获取相机信息"""
        info = {
            "device_id": self.device_id,
            "is_open": self.is_open,
            "mode": "SDK" if self.use_sdk else "UVC",
        }

        if self.cap is not None and self.is_open:
            _import_cv2()
            info["width"] = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            info["height"] = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            info["fps"] = self.cap.get(cv2.CAP_PROP_FPS)
            info["backend"] = self.cap.getBackendName()

        return info

    def close(self):
        """关闭相机"""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_open = False
        print("深度相机已关闭")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def detect_depth_cameras() -> list:
    """
    检测系统中的深度相机设备

    Returns:
        设备列表
    """
    cameras = []

    # Linux 系统检测
    if sys.platform.startswith('linux'):
        # 检查 /dev/video* 设备
        video_devices = []
        for i in range(20):
            dev_path = f"/dev/video{i}"
            if os.path.exists(dev_path):
                video_devices.append(dev_path)

        # 通过 v4l2-ctl 获取详细信息
        for dev in video_devices:
            try:
                result = subprocess.run(
                    ['v4l2-ctl', '--device', dev, '--info'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    output = result.stdout
                    # 检查是否是深度相机（Deptrum/Nebula）
                    if 'deptrum' in output.lower() or 'nebula' in output.lower():
                        cameras.append({
                            "device": dev,
                            "type": "depth_camera",
                            "info": output
                        })
                    elif 'depth' in output.lower():
                        cameras.append({
                            "device": dev,
                            "type": "depth_camera",
                            "info": output
                        })
            except Exception:
                pass

        # 检查 USB 设备
        try:
            result = subprocess.run(
                ['lsusb'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Deptrum 的 USB VID/PID
                if '2df6' in result.stdout.lower():
                    cameras.append({
                        "device": "USB",
                        "type": "deptrum_depth_camera",
                        "info": "Deptrum depth camera detected via USB"
                    })
        except Exception:
            pass

    return cameras


def test_depth_camera():
    """测试深度相机功能"""
    print("\n" + "="*60)
    print("深度相机 (Nebula410) 测试")
    print("="*60)

    # 检测设备
    print("\n[1] 检测深度相机设备...")
    cameras = detect_depth_cameras()
    if cameras:
        for cam in cameras:
            print(f"    发现: {cam['device']} ({cam['type']})")
    else:
        print("    未检测到专用深度相机设备")

    # 尝试打开相机
    print("\n[2] 尝试通过 UVC 模式打开相机...")

    camera = DepthCamera(device_id=-1)  # 自动检测
    if camera.open():
        info = camera.get_info()
        print(f"    分辨率: {info.get('width', 'N/A')}x{info.get('height', 'N/A')}")
        print(f"    帧率: {info.get('fps', 'N/A')} FPS")
        print(f"    后端: {info.get('backend', 'N/A')}")

        # 读取测试帧
        print("\n[3] 读取测试帧...")
        ret, frame = camera.read_frame()
        if ret:
            print(f"    成功读取帧: {frame.shape}")

            # 保存测试图像
            _import_cv2()
            test_img_path = "/tmp/depth_camera_test.jpg"
            try:
                cv2.imwrite(test_img_path, frame)
                print(f"    测试图像已保存: {test_img_path}")
            except Exception as e:
                print(f"    保存图像失败: {e}")
        else:
            print("    读取帧失败")

        camera.close()
        return True
    else:
        print("    打开相机失败")
        return False


if __name__ == "__main__":
    test_depth_camera()
