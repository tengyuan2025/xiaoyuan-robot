# -*- coding: utf-8 -*-
"""
舵机控制模块
通过 PWM (sysfs) 控制 RK3568 上的舵机

舵机配置 (来自组件连接图):
- 头部舵机: 左右转动(pan) + 上下点头(tilt)
- 左臂舵机
- 右臂舵机
"""

import os
import sys
import time
import glob
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class ServoConfig:
    """舵机配置"""
    name: str
    pwm_chip: int
    pwm_channel: int
    min_pulse_us: int = 500      # 最小脉宽 (微秒)
    max_pulse_us: int = 2500     # 最大脉宽 (微秒)
    min_angle: float = 0         # 最小角度 (度)
    max_angle: float = 180       # 最大角度 (度)
    default_angle: float = 90    # 默认角度


# 默认舵机配置
DEFAULT_SERVO_CONFIGS = {
    "head_pan": ServoConfig(
        name="头部水平",
        pwm_chip=0,
        pwm_channel=0,
        min_angle=-90,
        max_angle=90,
        default_angle=0
    ),
    "head_tilt": ServoConfig(
        name="头部俯仰",
        pwm_chip=0,
        pwm_channel=1,
        min_angle=-30,
        max_angle=30,
        default_angle=0
    ),
    "left_arm": ServoConfig(
        name="左臂",
        pwm_chip=0,
        pwm_channel=2,
        default_angle=0
    ),
    "right_arm": ServoConfig(
        name="右臂",
        pwm_chip=0,
        pwm_channel=3,
        default_angle=0
    ),
}


class PWMController:
    """
    PWM 控制器 (通过 sysfs)

    Linux PWM sysfs 接口:
    /sys/class/pwm/pwmchipX/
        export     - 导出 PWM 通道
        unexport   - 取消导出 PWM 通道
        pwmY/
            enable   - 启用/禁用 (1/0)
            period   - 周期 (纳秒)
            duty_cycle - 占空比 (纳秒)
            polarity - 极性 (normal/inversed)
    """

    PWM_BASE_PATH = "/sys/class/pwm"
    DEFAULT_PERIOD_NS = 20_000_000  # 20ms (50Hz) - 标准舵机频率

    def __init__(self, chip: int, channel: int):
        """
        初始化 PWM 控制器

        Args:
            chip: PWM 芯片编号
            channel: PWM 通道编号
        """
        self.chip = chip
        self.channel = channel
        self.chip_path = f"{self.PWM_BASE_PATH}/pwmchip{chip}"
        self.channel_path = f"{self.chip_path}/pwm{channel}"
        self.is_exported = False
        self.is_enabled = False

    def export(self) -> bool:
        """导出 PWM 通道"""
        if not os.path.exists(self.chip_path):
            print(f"PWM 芯片不存在: {self.chip_path}")
            return False

        if os.path.exists(self.channel_path):
            self.is_exported = True
            return True

        try:
            with open(f"{self.chip_path}/export", 'w') as f:
                f.write(str(self.channel))
            time.sleep(0.1)  # 等待 sysfs 创建节点
            self.is_exported = os.path.exists(self.channel_path)
            return self.is_exported
        except PermissionError:
            print(f"权限不足，请使用 sudo 运行或添加 udev 规则")
            return False
        except Exception as e:
            print(f"导出 PWM 失败: {e}")
            return False

    def unexport(self):
        """取消导出 PWM 通道"""
        if not self.is_exported:
            return

        try:
            self.disable()
            with open(f"{self.chip_path}/unexport", 'w') as f:
                f.write(str(self.channel))
            self.is_exported = False
        except Exception:
            pass

    def set_period(self, period_ns: int):
        """设置周期 (纳秒)"""
        if not self.is_exported:
            return

        try:
            with open(f"{self.channel_path}/period", 'w') as f:
                f.write(str(period_ns))
        except Exception as e:
            print(f"设置周期失败: {e}")

    def set_duty_cycle(self, duty_ns: int):
        """设置占空比 (纳秒)"""
        if not self.is_exported:
            return

        try:
            with open(f"{self.channel_path}/duty_cycle", 'w') as f:
                f.write(str(duty_ns))
        except Exception as e:
            print(f"设置占空比失败: {e}")

    def enable(self):
        """启用 PWM 输出"""
        if not self.is_exported:
            return

        try:
            with open(f"{self.channel_path}/enable", 'w') as f:
                f.write('1')
            self.is_enabled = True
        except Exception as e:
            print(f"启用 PWM 失败: {e}")

    def disable(self):
        """禁用 PWM 输出"""
        if not self.is_exported:
            return

        try:
            with open(f"{self.channel_path}/enable", 'w') as f:
                f.write('0')
            self.is_enabled = False
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        """获取 PWM 状态"""
        status = {
            "chip": self.chip,
            "channel": self.channel,
            "chip_path": self.chip_path,
            "is_exported": self.is_exported,
            "is_enabled": self.is_enabled,
        }

        if self.is_exported and os.path.exists(self.channel_path):
            try:
                with open(f"{self.channel_path}/period", 'r') as f:
                    status["period_ns"] = int(f.read().strip())
                with open(f"{self.channel_path}/duty_cycle", 'r') as f:
                    status["duty_cycle_ns"] = int(f.read().strip())
                with open(f"{self.channel_path}/enable", 'r') as f:
                    status["enabled"] = f.read().strip() == '1'
            except Exception:
                pass

        return status


class Servo:
    """
    舵机控制类

    通过 PWM 信号控制舵机角度
    标准舵机: 50Hz PWM，500-2500us 脉宽对应 0-180 度
    """

    def __init__(self, config: ServoConfig):
        """
        初始化舵机

        Args:
            config: 舵机配置
        """
        self.config = config
        self.pwm = PWMController(config.pwm_chip, config.pwm_channel)
        self.current_angle = config.default_angle
        self.is_initialized = False

    def init(self) -> bool:
        """初始化舵机"""
        if not self.pwm.export():
            return False

        # 设置 PWM 周期 (50Hz = 20ms)
        self.pwm.set_period(PWMController.DEFAULT_PERIOD_NS)

        # 移动到默认位置
        self.set_angle(self.config.default_angle)

        # 启用 PWM
        self.pwm.enable()

        self.is_initialized = True
        print(f"舵机 '{self.config.name}' 初始化完成")
        return True

    def angle_to_pulse_ns(self, angle: float) -> int:
        """将角度转换为脉宽 (纳秒)"""
        # 限制角度范围
        angle = max(self.config.min_angle, min(self.config.max_angle, angle))

        # 计算脉宽
        angle_range = self.config.max_angle - self.config.min_angle
        pulse_range = self.config.max_pulse_us - self.config.min_pulse_us

        normalized = (angle - self.config.min_angle) / angle_range
        pulse_us = self.config.min_pulse_us + normalized * pulse_range

        return int(pulse_us * 1000)  # 微秒转纳秒

    def set_angle(self, angle: float):
        """
        设置舵机角度

        Args:
            angle: 目标角度
        """
        if not self.pwm.is_exported:
            print(f"舵机 '{self.config.name}' 未初始化")
            return

        # 限制角度范围
        angle = max(self.config.min_angle, min(self.config.max_angle, angle))

        # 计算并设置脉宽
        duty_ns = self.angle_to_pulse_ns(angle)
        self.pwm.set_duty_cycle(duty_ns)

        self.current_angle = angle

    def get_angle(self) -> float:
        """获取当前角度"""
        return self.current_angle

    def move_smooth(self, target_angle: float, duration: float = 1.0, steps: int = 50):
        """
        平滑移动到目标角度

        Args:
            target_angle: 目标角度
            duration: 移动时间 (秒)
            steps: 分步数量
        """
        start_angle = self.current_angle
        angle_diff = target_angle - start_angle
        step_delay = duration / steps

        for i in range(steps + 1):
            t = i / steps
            # 使用 ease-in-out 缓动
            if t < 0.5:
                ease = 2 * t * t
            else:
                ease = 1 - pow(-2 * t + 2, 2) / 2

            current = start_angle + angle_diff * ease
            self.set_angle(current)
            time.sleep(step_delay)

    def center(self):
        """回到中心位置"""
        center = (self.config.min_angle + self.config.max_angle) / 2
        self.set_angle(center)

    def deinit(self):
        """释放舵机"""
        self.pwm.disable()
        self.pwm.unexport()
        self.is_initialized = False


class ServoController:
    """
    舵机控制器

    管理多个舵机的统一接口
    """

    def __init__(self, configs: Dict[str, ServoConfig] = None):
        """
        初始化舵机控制器

        Args:
            configs: 舵机配置字典
        """
        self.configs = configs or DEFAULT_SERVO_CONFIGS
        self.servos: Dict[str, Servo] = {}

    def init_all(self) -> bool:
        """初始化所有舵机"""
        success = True
        for name, config in self.configs.items():
            servo = Servo(config)
            if servo.init():
                self.servos[name] = servo
            else:
                print(f"舵机 '{name}' 初始化失败")
                success = False
        return success

    def init_servo(self, name: str) -> bool:
        """初始化指定舵机"""
        if name not in self.configs:
            print(f"未知舵机: {name}")
            return False

        servo = Servo(self.configs[name])
        if servo.init():
            self.servos[name] = servo
            return True
        return False

    def set_angle(self, name: str, angle: float):
        """设置指定舵机角度"""
        if name in self.servos:
            self.servos[name].set_angle(angle)
        else:
            print(f"舵机 '{name}' 未初始化")

    def get_angle(self, name: str) -> Optional[float]:
        """获取指定舵机角度"""
        if name in self.servos:
            return self.servos[name].get_angle()
        return None

    def center_all(self):
        """所有舵机回到中心位置"""
        for servo in self.servos.values():
            servo.center()

    def deinit_all(self):
        """释放所有舵机"""
        for servo in self.servos.values():
            servo.deinit()
        self.servos.clear()

    # 便捷方法
    def nod(self, count: int = 2):
        """点头动作"""
        if "head_tilt" not in self.servos:
            return

        original = self.servos["head_tilt"].get_angle()
        for _ in range(count):
            self.servos["head_tilt"].move_smooth(15, 0.3)
            self.servos["head_tilt"].move_smooth(-10, 0.3)
        self.servos["head_tilt"].move_smooth(original, 0.3)

    def shake_head(self, count: int = 2):
        """摇头动作"""
        if "head_pan" not in self.servos:
            return

        original = self.servos["head_pan"].get_angle()
        for _ in range(count):
            self.servos["head_pan"].move_smooth(-30, 0.3)
            self.servos["head_pan"].move_smooth(30, 0.3)
        self.servos["head_pan"].move_smooth(original, 0.3)

    def wave(self, arm: str = "right"):
        """挥手动作"""
        servo_name = f"{arm}_arm"
        if servo_name not in self.servos:
            return

        original = self.servos[servo_name].get_angle()
        self.servos[servo_name].move_smooth(120, 0.5)
        for _ in range(3):
            self.servos[servo_name].move_smooth(90, 0.2)
            self.servos[servo_name].move_smooth(120, 0.2)
        self.servos[servo_name].move_smooth(original, 0.5)


def detect_pwm_chips() -> List[Dict[str, Any]]:
    """检测系统中的 PWM 控制器"""
    pwm_chips = []

    if not os.path.exists(PWMController.PWM_BASE_PATH):
        return pwm_chips

    chips = glob.glob(f"{PWMController.PWM_BASE_PATH}/pwmchip*")

    for chip_path in chips:
        chip_name = os.path.basename(chip_path)
        chip_num = int(chip_name.replace('pwmchip', ''))

        info = {
            "chip": chip_num,
            "path": chip_path,
            "channels": 0,
        }

        # 获取通道数
        npwm_path = os.path.join(chip_path, "npwm")
        if os.path.exists(npwm_path):
            try:
                with open(npwm_path, 'r') as f:
                    info["channels"] = int(f.read().strip())
            except Exception:
                pass

        pwm_chips.append(info)

    return pwm_chips


def test_servo():
    """测试舵机功能"""
    print("\n" + "="*60)
    print("舵机 (PWM) 测试")
    print("="*60)

    # 检测 PWM 控制器
    print("\n[1] 检测 PWM 控制器...")
    chips = detect_pwm_chips()
    if chips:
        for chip in chips:
            print(f"    发现: pwmchip{chip['chip']} ({chip['channels']} 个通道)")
    else:
        print("    未检测到 PWM 控制器")
        print("    提示: 确保运行在支持 PWM 的 Linux 系统上 (如 RK3568)")
        return False

    # 检测是否有足够权限
    print("\n[2] 检查权限...")
    chip_path = chips[0]['path'] if chips else f"{PWMController.PWM_BASE_PATH}/pwmchip0"
    export_path = os.path.join(chip_path, "export")

    if os.path.exists(export_path):
        if os.access(export_path, os.W_OK):
            print("    PWM 导出权限: OK")
        else:
            print("    PWM 导出权限: 需要 root 权限")
            print("    提示: 使用 sudo 运行或配置 udev 规则")
            return False
    else:
        print(f"    未找到: {export_path}")
        return False

    # 测试舵机控制
    print("\n[3] 测试舵机控制...")
    controller = ServoController()

    # 只测试第一个舵机
    first_servo_name = list(DEFAULT_SERVO_CONFIGS.keys())[0]
    first_servo_config = DEFAULT_SERVO_CONFIGS[first_servo_name]

    print(f"    测试舵机: {first_servo_config.name} (pwmchip{first_servo_config.pwm_chip}/pwm{first_servo_config.pwm_channel})")

    servo = Servo(first_servo_config)
    if servo.init():
        print("    初始化: 成功")

        # 测试移动
        print("\n[4] 测试舵机移动...")
        print(f"    当前角度: {servo.get_angle()}")

        # 移动到几个位置
        test_angles = [0, 45, 90, 135, 90]
        for angle in test_angles:
            print(f"    移动到: {angle} 度")
            servo.set_angle(angle)
            time.sleep(0.5)

        # 测试平滑移动
        print("    平滑移动测试...")
        servo.move_smooth(0, 1.0)
        servo.move_smooth(90, 1.0)

        print(f"    最终角度: {servo.get_angle()}")

        servo.deinit()
        print("\n    舵机测试完成")
        return True
    else:
        print("    初始化: 失败")
        return False


if __name__ == "__main__":
    test_servo()
