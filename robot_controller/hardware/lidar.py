# -*- coding: utf-8 -*-
"""
激光雷达模块 (RPLIDAR C1)
思岚科技 RPLIDAR C1 激光雷达控制

使用 rplidar-roboticia 库进行通信
安装: pip install rplidar-roboticia
"""

import os
import sys
import time
import glob
import serial
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

# 延迟导入雷达库
RPLidar = None


def _import_rplidar():
    global RPLidar
    if RPLidar is None:
        try:
            from rplidar import RPLidar as _RPLidar
            RPLidar = _RPLidar
        except ImportError:
            raise ImportError("请安装 rplidar-roboticia: pip install rplidar-roboticia")


@dataclass
class ScanPoint:
    """扫描点数据"""
    quality: int      # 质量 (0-15)
    angle: float      # 角度 (0-360度)
    distance: float   # 距离 (mm)


class Lidar:
    """
    RPLIDAR C1 激光雷达控制类

    特性：
    - 8米测距范围
    - 360度扫描
    - 5000+ 采样点/秒
    """

    # RPLIDAR C1 默认配置
    DEFAULT_PORT = "/dev/ttyUSB1"
    DEFAULT_BAUDRATE = 460800

    def __init__(self, port: str = None, baudrate: int = None):
        """
        初始化雷达

        Args:
            port: 串口设备路径
            baudrate: 波特率
        """
        self.port = port or self.DEFAULT_PORT
        self.baudrate = baudrate or self.DEFAULT_BAUDRATE
        self.lidar = None
        self.is_connected = False
        self.info = {}
        self.health = {}

    def connect(self) -> bool:
        """连接雷达"""
        _import_rplidar()

        try:
            self.lidar = RPLidar(self.port, baudrate=self.baudrate)

            # 获取设备信息
            self.info = self.lidar.get_info()
            print(f"雷达已连接: {self.port}")
            print(f"  型号: {self.info.get('model', 'Unknown')}")
            print(f"  固件: {self.info.get('firmware', 'Unknown')}")
            print(f"  硬件: {self.info.get('hardware', 'Unknown')}")
            print(f"  序列号: {self.info.get('serialnumber', 'Unknown')}")

            # 获取健康状态
            self.health = self.lidar.get_health()
            health_status = self.health[0] if isinstance(self.health, tuple) else self.health
            print(f"  健康状态: {health_status}")

            self.is_connected = True
            return True

        except serial.SerialException as e:
            print(f"串口错误: {e}")
            return False
        except Exception as e:
            print(f"连接雷达失败: {e}")
            return False

    def start_scan(self):
        """开始扫描"""
        if not self.is_connected:
            raise RuntimeError("雷达未连接")

        self.lidar.start_motor()

    def stop_scan(self):
        """停止扫描"""
        if self.lidar:
            self.lidar.stop_motor()

    def get_scan(self, max_points: int = 360) -> List[ScanPoint]:
        """
        获取一圈扫描数据

        Args:
            max_points: 最大采集点数

        Returns:
            扫描点列表
        """
        if not self.is_connected:
            raise RuntimeError("雷达未连接")

        points = []

        try:
            for i, scan in enumerate(self.lidar.iter_scans()):
                for quality, angle, distance in scan:
                    points.append(ScanPoint(
                        quality=quality,
                        angle=angle,
                        distance=distance
                    ))
                    if len(points) >= max_points:
                        break

                if len(points) >= max_points:
                    break

                # 只取一圈数据
                if i >= 1:
                    break

        except Exception as e:
            print(f"扫描错误: {e}")

        return points

    def get_distance_at_angle(self, target_angle: float, tolerance: float = 5.0) -> Optional[float]:
        """
        获取指定角度的距离

        Args:
            target_angle: 目标角度 (0-360)
            tolerance: 角度容差

        Returns:
            距离 (mm) 或 None
        """
        points = self.get_scan(360)

        for point in points:
            if abs(point.angle - target_angle) <= tolerance:
                if point.distance > 0:
                    return point.distance

        return None

    def get_front_distance(self) -> Optional[float]:
        """获取正前方距离 (0度)"""
        return self.get_distance_at_angle(0, tolerance=10)

    def get_back_distance(self) -> Optional[float]:
        """获取正后方距离 (180度)"""
        return self.get_distance_at_angle(180, tolerance=10)

    def get_left_distance(self) -> Optional[float]:
        """获取左侧距离 (90度)"""
        return self.get_distance_at_angle(90, tolerance=10)

    def get_right_distance(self) -> Optional[float]:
        """获取右侧距离 (270度)"""
        return self.get_distance_at_angle(270, tolerance=10)

    def get_info(self) -> Dict[str, Any]:
        """获取雷达信息"""
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "is_connected": self.is_connected,
            "device_info": self.info,
            "health": self.health,
        }

    def disconnect(self):
        """断开连接"""
        if self.lidar:
            try:
                self.lidar.stop()
                self.lidar.disconnect()
            except Exception:
                pass
            self.lidar = None
        self.is_connected = False
        print("雷达已断开连接")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


def detect_lidar_ports() -> List[str]:
    """
    检测可能的雷达串口

    Returns:
        可用串口列表
    """
    ports = []

    if sys.platform.startswith('linux'):
        # USB 串口
        usb_ports = glob.glob('/dev/ttyUSB*')
        acm_ports = glob.glob('/dev/ttyACM*')
        ports.extend(usb_ports)
        ports.extend(acm_ports)

    elif sys.platform == 'win32':
        # Windows COM 口
        for i in range(256):
            port = f'COM{i}'
            try:
                s = serial.Serial(port)
                s.close()
                ports.append(port)
            except (OSError, serial.SerialException):
                pass

    return sorted(ports)


def test_lidar():
    """测试雷达功能"""
    print("\n" + "="*60)
    print("激光雷达 (RPLIDAR C1) 测试")
    print("="*60)

    # 检测串口
    print("\n[1] 检测可用串口...")
    ports = detect_lidar_ports()
    if ports:
        for port in ports:
            print(f"    发现: {port}")
    else:
        print("    未检测到可用串口")
        return False

    # 尝试连接雷达
    print("\n[2] 尝试连接雷达...")

    # 优先尝试配置中的端口
    test_ports = ['/dev/ttyUSB1', '/dev/ttyUSB0'] + ports
    test_ports = list(dict.fromkeys(test_ports))  # 去重保序

    lidar = None
    for port in test_ports:
        if not os.path.exists(port) and sys.platform.startswith('linux'):
            continue

        print(f"    尝试: {port}...")
        try:
            lidar = Lidar(port=port)
            if lidar.connect():
                break
            else:
                lidar = None
        except Exception as e:
            print(f"    失败: {e}")
            lidar = None

    if lidar is None:
        print("    无法连接雷达")
        return False

    # 执行扫描测试
    print("\n[3] 执行扫描测试...")
    try:
        lidar.start_scan()
        time.sleep(2)  # 等待电机稳定

        points = lidar.get_scan(100)
        print(f"    采集到 {len(points)} 个扫描点")

        if points:
            # 显示部分数据
            print("\n    扫描数据示例 (前10个点):")
            print("    角度(度)  | 距离(mm)  | 质量")
            print("    " + "-"*35)
            for p in points[:10]:
                print(f"    {p.angle:8.2f}  | {p.distance:8.1f}  | {p.quality:2d}")

            # 统计信息
            valid_points = [p for p in points if p.distance > 0]
            if valid_points:
                min_dist = min(p.distance for p in valid_points)
                max_dist = max(p.distance for p in valid_points)
                avg_dist = sum(p.distance for p in valid_points) / len(valid_points)
                print(f"\n    统计: 最近 {min_dist:.0f}mm, 最远 {max_dist:.0f}mm, 平均 {avg_dist:.0f}mm")

            # 获取方向距离
            print("\n[4] 方向距离测试...")
            front = lidar.get_front_distance()
            back = lidar.get_back_distance()
            left = lidar.get_left_distance()
            right = lidar.get_right_distance()

            print(f"    前方 (0度): {front:.0f}mm" if front else "    前方 (0度): N/A")
            print(f"    后方 (180度): {back:.0f}mm" if back else "    后方 (180度): N/A")
            print(f"    左侧 (90度): {left:.0f}mm" if left else "    左侧 (90度): N/A")
            print(f"    右侧 (270度): {right:.0f}mm" if right else "    右侧 (270度): N/A")

        lidar.stop_scan()
        lidar.disconnect()
        return True

    except Exception as e:
        print(f"    扫描失败: {e}")
        if lidar:
            lidar.disconnect()
        return False


if __name__ == "__main__":
    test_lidar()
