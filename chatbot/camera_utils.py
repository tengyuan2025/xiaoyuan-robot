# -*- coding: utf-8 -*-
"""
摄像头工具模块

功能：
1. 调用摄像头拍摄单张图片
2. 图片压缩（控制在1080P以内）
3. 图片转Base64编码
4. 支持 Windows/macOS/Linux 系统
5. 异常处理和资源管理

依赖：
- opencv-python: pip install opencv-python

作者：Claude Code
日期：2024
"""

import os
import sys
import base64
from typing import Optional, Tuple


def capture_image(
    save_path: str,
    camera_index: int = 0,
    warmup_frames: int = 10,
    max_width: int = 1920,
    max_height: int = 1080,
    quality: int = 85
) -> Optional[str]:
    """
    调用摄像头拍摄一张图片，自动压缩到指定尺寸

    Args:
        save_path: 图片保存路径
        camera_index: 摄像头索引（默认0为主摄像头）
        warmup_frames: 预热帧数（让摄像头自动曝光稳定）
        max_width: 最大宽度（超过则等比缩放）
        max_height: 最大高度（超过则等比缩放）
        quality: JPEG压缩质量 (1-100)

    Returns:
        保存的图片路径，失败返回None
    """
    try:
        import cv2
    except ImportError:
        print("[Camera] 错误: 未安装 opencv-python")
        print("[Camera] 请运行: pip install opencv-python")
        return None

    cap = None

    try:
        print(f"[Camera] 正在打开摄像头 (index={camera_index})...")

        # Windows 使用 CAP_DSHOW 提升兼容性  # NEW
        if sys.platform == 'win32':
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(camera_index)

        # 检查是否成功打开
        if not cap.isOpened():
            print("[Camera] 错误: 无法打开摄像头")
            print("[Camera] 可能原因: 1.无摄像头 2.权限不足 3.被其他程序占用")
            return None

        # 设置摄像头参数（请求较高分辨率，后续会压缩）
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        # 预热：读取几帧让自动曝光稳定
        print(f"[Camera] 摄像头预热中...")
        for i in range(warmup_frames):
            ret, _ = cap.read()
            if not ret:
                print(f"[Camera] 警告: 预热帧 {i} 读取失败")

        # 拍摄正式照片
        print("[Camera] 正在拍摄...")
        ret, frame = cap.read()

        if not ret or frame is None:
            print("[Camera] 错误: 拍摄失败，无法读取帧")
            return None

        # 获取原始尺寸
        height, width = frame.shape[:2]
        print(f"[Camera] 原始尺寸: {width}x{height}")

        # 压缩图片尺寸（如果超过限制）  # NEW
        if width > max_width or height > max_height:
            # 计算缩放比例（保持宽高比）
            scale_w = max_width / width
            scale_h = max_height / height
            scale = min(scale_w, scale_h)

            new_width = int(width * scale)
            new_height = int(height * scale)

            frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
            print(f"[Camera] 压缩后尺寸: {new_width}x{new_height}")

        # 确保目录存在
        save_dir = os.path.dirname(save_path)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        # 保存图片（使用JPEG压缩）
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        success = cv2.imwrite(save_path, frame, encode_params)

        if success:
            file_size = os.path.getsize(save_path)
            print(f"[Camera] 拍摄成功: {save_path}")
            print(f"[Camera] 文件大小: {file_size/1024:.1f}KB")
            return save_path
        else:
            print(f"[Camera] 错误: 保存图片失败 ({save_path})")
            return None

    except Exception as e:
        print(f"[Camera] 拍摄异常: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        # 释放摄像头资源  # NEW: 确保资源释放
        if cap is not None:
            cap.release()
            print("[Camera] 摄像头已释放")
        # Windows 下销毁窗口（如果有）
        try:
            import cv2
            cv2.destroyAllWindows()
        except:
            pass


def image_to_base64(image_path: str) -> Optional[str]:  # NEW
    """
    将图片文件转换为带格式头的Base64字符串

    Args:
        image_path: 图片文件路径

    Returns:
        格式为 "data:image/jpeg;base64,xxx" 的字符串，失败返回None
    """
    if not image_path or not os.path.exists(image_path):
        print(f"[Camera] 错误: 图片文件不存在 ({image_path})")
        return None

    try:
        with open(image_path, "rb") as f:
            image_data = f.read()

        # 编码为Base64
        base64_str = base64.b64encode(image_data).decode('utf-8')

        # 添加格式头
        result = f"data:image/jpeg;base64,{base64_str}"

        print(f"[Camera] Base64编码完成，长度: {len(result)} 字符")
        return result

    except Exception as e:
        print(f"[Camera] Base64编码失败: {e}")
        return None


def capture_and_encode(  # NEW: 便捷函数，拍照+编码一步完成
    save_path: str,
    camera_index: int = 0,
    max_width: int = 1920,
    max_height: int = 1080,
    quality: int = 85
) -> Tuple[Optional[str], Optional[str]]:
    """
    拍照并转换为Base64编码

    Args:
        save_path: 临时图片保存路径
        camera_index: 摄像头索引
        max_width: 最大宽度
        max_height: 最大高度
        quality: JPEG压缩质量

    Returns:
        (图片路径, Base64字符串) 元组，失败时对应位置为None
    """
    # 拍照
    image_path = capture_image(
        save_path=save_path,
        camera_index=camera_index,
        max_width=max_width,
        max_height=max_height,
        quality=quality
    )

    if not image_path:
        return None, None

    # 转Base64
    base64_str = image_to_base64(image_path)

    return image_path, base64_str


def delete_temp_image(image_path: str) -> bool:
    """
    删除临时图片文件

    Args:
        image_path: 图片路径

    Returns:
        是否删除成功
    """
    if not image_path:
        return False

    try:
        if os.path.exists(image_path):
            os.remove(image_path)
            print(f"[Camera] 临时图片已删除: {image_path}")
            return True
        return False
    except Exception as e:
        print(f"[Camera] 删除临时图片失败: {e}")
        return False


def check_camera_available(camera_index: int = 0) -> Tuple[bool, str]:
    """
    检查摄像头是否可用

    Args:
        camera_index: 摄像头索引

    Returns:
        (是否可用, 状态消息)
    """
    try:
        import cv2
    except ImportError:
        return False, "opencv-python 未安装"

    try:
        if sys.platform == 'win32':
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(camera_index)

        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            if ret:
                return True, f"摄像头 {camera_index} 可用"
            else:
                return False, f"摄像头 {camera_index} 已打开但无法读取"
        else:
            return False, f"摄像头 {camera_index} 无法打开"
    except Exception as e:
        return False, f"检查失败: {str(e)}"


# 测试代码
if __name__ == "__main__":
    print("=== 摄像头工具测试 ===")

    # 检查摄像头
    available, msg = check_camera_available(0)
    print(f"摄像头状态: {msg}")

    if available:
        # 拍照并编码测试
        test_path = "test_capture.jpg"
        image_path, base64_str = capture_and_encode(
            save_path=test_path,
            max_width=1280,
            max_height=720,
            quality=80
        )

        if base64_str:
            print(f"Base64前100字符: {base64_str[:100]}...")
            print(f"Base64总长度: {len(base64_str)}")

            # 清理测试文件
            delete_temp_image(test_path)
    else:
        print("未检测到可用摄像头")
