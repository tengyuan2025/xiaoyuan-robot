# -*- coding: utf-8 -*-
"""
硬件控制模块

包含:
- depth_camera: 深度相机 (Nebula410) 控制
- lidar: 激光雷达 (RPLIDAR C1) 控制
- servo: 舵机 (PWM) 控制
"""

from .depth_camera import DepthCamera, detect_depth_cameras
from .lidar import Lidar, detect_lidar_ports
from .servo import Servo, ServoController, detect_pwm_chips

__all__ = [
    'DepthCamera',
    'detect_depth_cameras',
    'Lidar',
    'detect_lidar_ports',
    'Servo',
    'ServoController',
    'detect_pwm_chips',
]
