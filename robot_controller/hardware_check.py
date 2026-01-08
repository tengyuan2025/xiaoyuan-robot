#!/usr/bin/env python3
"""
硬件连接检测脚本
用于检测 RK3568 陪伴机器人主控板上的硬件连接状态
"""

import subprocess
import os
import sys
import glob
import platform


class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(title: str):
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {title}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")


def print_status(name: str, status: bool, details: str = ""):
    """打印检测状态"""
    if status:
        icon = f"{Colors.GREEN}✓{Colors.END}"
        status_text = f"{Colors.GREEN}已连接{Colors.END}"
    else:
        icon = f"{Colors.RED}✗{Colors.END}"
        status_text = f"{Colors.RED}未检测到{Colors.END}"

    print(f"  {icon} {name}: {status_text}")
    if details:
        for line in details.strip().split('\n'):
            print(f"      {Colors.YELLOW}{line}{Colors.END}")


def run_command(cmd: str) -> tuple[bool, str]:
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "命令超时"
    except Exception as e:
        return False, str(e)


def check_platform():
    """检测运行平台"""
    print_header("系统信息")

    system = platform.system()
    machine = platform.machine()

    print(f"  操作系统: {system}")
    print(f"  架构: {machine}")

    if system == "Linux":
        # 获取更详细的 Linux 信息
        success, output = run_command("cat /etc/os-release | grep PRETTY_NAME")
        if success:
            distro = output.split('=')[1].strip('"') if '=' in output else output
            print(f"  发行版: {distro}")

        success, output = run_command("uname -r")
        if success:
            print(f"  内核版本: {output}")

    print(f"\n  {Colors.YELLOW}提示: 此脚本主要针对 Linux 系统设计{Colors.END}")

    return system


def check_usb_devices():
    """检测 USB 设备"""
    print_header("USB 设备")

    if platform.system() != "Linux":
        print(f"  {Colors.YELLOW}跳过: 仅支持 Linux 系统{Colors.END}")
        return

    success, output = run_command("lsusb")
    if success and output:
        devices = output.strip().split('\n')
        print(f"  检测到 {len(devices)} 个 USB 设备:")
        for device in devices:
            # 解析 lsusb 输出
            print(f"    • {device}")
    else:
        print_status("USB 设备", False, "无法获取 USB 设备列表")


def check_audio_devices():
    """检测音频设备 (ALSA)"""
    print_header("音频设备")

    if platform.system() != "Linux":
        print(f"  {Colors.YELLOW}跳过: 仅支持 Linux 系统{Colors.END}")
        return

    # 检测播放设备
    print(f"\n  {Colors.BOLD}播放设备 (扬声器/USB声卡):{Colors.END}")
    success, output = run_command("aplay -l 2>/dev/null")
    if success and output and "card" in output.lower():
        for line in output.split('\n'):
            if line.startswith('card') or line.startswith('  '):
                print(f"    {line}")
        print_status("音频输出", True)
    else:
        print_status("音频输出", False, "未检测到播放设备")

    # 检测录音设备
    print(f"\n  {Colors.BOLD}录音设备 (麦克风/降噪板):{Colors.END}")
    success, output = run_command("arecord -l 2>/dev/null")
    if success and output and "card" in output.lower():
        for line in output.split('\n'):
            if line.startswith('card') or line.startswith('  '):
                print(f"    {line}")
        print_status("音频输入", True)
    else:
        print_status("音频输入", False, "未检测到录音设备")


def check_camera_devices():
    """检测摄像头设备"""
    print_header("摄像头设备")

    if platform.system() != "Linux":
        print(f"  {Colors.YELLOW}跳过: 仅支持 Linux 系统{Colors.END}")
        return

    video_devices = glob.glob("/dev/video*")

    if video_devices:
        print(f"  检测到 {len(video_devices)} 个视频设备:")
        for device in sorted(video_devices):
            # 尝试获取设备信息
            success, output = run_command(f"v4l2-ctl --device={device} --info 2>/dev/null | grep 'Card type'")
            if success and output:
                card_type = output.split(':')[1].strip() if ':' in output else "未知"
                print(f"    • {device}: {card_type}")
            else:
                print(f"    • {device}")
        print_status("摄像头", True)
    else:
        print_status("摄像头", False, "未检测到 /dev/video* 设备")


def check_serial_devices():
    """检测串口设备"""
    print_header("串口设备")

    if platform.system() != "Linux":
        print(f"  {Colors.YELLOW}跳过: 仅支持 Linux 系统{Colors.END}")
        return

    # USB 串口 (降噪板可能使用)
    usb_serial = glob.glob("/dev/ttyUSB*")
    # 硬件串口 (雷达可能使用)
    hw_serial = glob.glob("/dev/ttyS*") + glob.glob("/dev/ttyAMA*")
    # ACM 设备 (某些 USB 串口)
    acm_serial = glob.glob("/dev/ttyACM*")

    all_serial = usb_serial + acm_serial

    print(f"\n  {Colors.BOLD}USB 串口 (降噪板/麦克风):{Colors.END}")
    if usb_serial or acm_serial:
        for device in sorted(usb_serial + acm_serial):
            print(f"    • {device}")
        print_status("USB串口", True)
    else:
        print_status("USB串口", False)

    print(f"\n  {Colors.BOLD}硬件串口 (雷达):{Colors.END}")
    if hw_serial:
        # 过滤掉未使用的串口
        active_serial = []
        for device in sorted(hw_serial):
            # 检查串口是否可用
            if os.access(device, os.R_OK | os.W_OK):
                active_serial.append(device)

        if active_serial:
            for device in active_serial:
                print(f"    • {device}")
            print_status("硬件串口", True)
        else:
            print(f"  发现 {len(hw_serial)} 个串口，但无读写权限")
            print_status("硬件串口", False, "需要 root 权限或添加用户到 dialout 组")
    else:
        print_status("硬件串口", False)


def check_pwm_gpio():
    """检测 PWM/GPIO 设备 (舵机控制)"""
    print_header("PWM/GPIO 设备 (舵机)")

    if platform.system() != "Linux":
        print(f"  {Colors.YELLOW}跳过: 仅支持 Linux 系统{Colors.END}")
        return

    # 检查 PWM 设备
    pwm_chips = glob.glob("/sys/class/pwm/pwmchip*")

    print(f"\n  {Colors.BOLD}PWM 控制器:{Colors.END}")
    if pwm_chips:
        for chip in sorted(pwm_chips):
            chip_name = os.path.basename(chip)
            # 获取 PWM 通道数
            npwm_path = os.path.join(chip, "npwm")
            if os.path.exists(npwm_path):
                with open(npwm_path, 'r') as f:
                    npwm = f.read().strip()
                print(f"    • {chip_name}: {npwm} 个通道")
            else:
                print(f"    • {chip_name}")
        print_status("PWM", True)
    else:
        print_status("PWM", False, "未检测到 PWM 控制器")

    # 检查 GPIO
    print(f"\n  {Colors.BOLD}GPIO 控制器:{Colors.END}")
    gpio_chips = glob.glob("/sys/class/gpio/gpiochip*")
    if gpio_chips:
        for chip in sorted(gpio_chips)[:5]:  # 只显示前5个
            chip_name = os.path.basename(chip)
            print(f"    • {chip_name}")
        if len(gpio_chips) > 5:
            print(f"    ... 共 {len(gpio_chips)} 个 GPIO 控制器")
        print_status("GPIO", True)
    else:
        print_status("GPIO", False)


def check_display():
    """检测显示设备"""
    print_header("显示设备 (LCD)")

    if platform.system() != "Linux":
        print(f"  {Colors.YELLOW}跳过: 仅支持 Linux 系统{Colors.END}")
        return

    # Framebuffer 设备
    fb_devices = glob.glob("/dev/fb*")

    print(f"\n  {Colors.BOLD}Framebuffer 设备:{Colors.END}")
    if fb_devices:
        for fb in sorted(fb_devices):
            # 获取分辨率信息
            fb_num = fb.replace("/dev/fb", "")
            success, output = run_command(f"cat /sys/class/graphics/fb{fb_num}/virtual_size 2>/dev/null")
            if success and output:
                print(f"    • {fb}: {output.replace(',', 'x')} 像素")
            else:
                print(f"    • {fb}")
        print_status("Framebuffer", True)
    else:
        print_status("Framebuffer", False)

    # DRM 设备 (现代显示子系统)
    print(f"\n  {Colors.BOLD}DRM 显示设备:{Colors.END}")
    drm_devices = glob.glob("/dev/dri/card*")
    if drm_devices:
        for drm in sorted(drm_devices):
            print(f"    • {drm}")
        print_status("DRM", True)
    else:
        print_status("DRM", False)


def check_i2c():
    """检测 I2C 设备 (可能用于某些传感器)"""
    print_header("I2C 总线")

    if platform.system() != "Linux":
        print(f"  {Colors.YELLOW}跳过: 仅支持 Linux 系统{Colors.END}")
        return

    i2c_devices = glob.glob("/dev/i2c-*")

    if i2c_devices:
        print(f"  检测到 {len(i2c_devices)} 个 I2C 总线:")
        for i2c in sorted(i2c_devices):
            print(f"    • {i2c}")
        print_status("I2C", True)
    else:
        print_status("I2C", False)


def check_network():
    """检测网络连接"""
    print_header("网络连接")

    # 检测 WiFi
    if platform.system() == "Linux":
        success, output = run_command("iwconfig 2>/dev/null | grep -E 'wlan|ESSID'")
        if success and output:
            print(f"  {Colors.BOLD}WiFi:{Colors.END}")
            for line in output.split('\n'):
                print(f"    {line.strip()}")
            print_status("WiFi", True)
        else:
            print_status("WiFi", False, "未检测到 WiFi 连接")

    # 检测网络连通性
    print(f"\n  {Colors.BOLD}网络连通性测试:{Colors.END}")
    success, _ = run_command("ping -c 1 -W 3 8.8.8.8 2>/dev/null || ping -n 1 -w 3000 8.8.8.8 2>nul")
    print_status("互联网连接", success)


def generate_summary(system: str):
    """生成检测总结"""
    print_header("检测总结")

    if system != "Linux":
        print(f"""
  {Colors.YELLOW}注意: 当前在 {system} 系统上运行{Colors.END}

  此脚本需要在 RK3568 主控板 (Linux) 上运行才能检测硬件。

  请通过 SSH 连接到主控板后运行:

    {Colors.BOLD}scp hardware_check.py user@<主控IP>:~/{Colors.END}
    {Colors.BOLD}ssh user@<主控IP>{Colors.END}
    {Colors.BOLD}python3 hardware_check.py{Colors.END}
""")
    else:
        print(f"""
  请根据以上检测结果确认硬件连接:

  {Colors.BOLD}必要硬件:{Colors.END}
    • 麦克风/降噪板 - 语音输入
    • USB声卡/扬声器 - 语音输出
    • 摄像头 - 视觉识别

  {Colors.BOLD}可选硬件:{Colors.END}
    • 舵机 (PWM) - 头部/手臂动作
    • 雷达 (串口) - 底盘导航
    • LCD (MIPI) - 表情显示

  {Colors.BOLD}如有设备未检测到，请检查:{Colors.END}
    1. 硬件是否正确连接
    2. 驱动是否已加载
    3. 用户权限是否足够 (可尝试 sudo 运行)
""")


def main():
    print(f"""
{Colors.BOLD}╔══════════════════════════════════════════════════════════╗
║          陪伴机器人硬件连接检测工具 v1.0                  ║
║              RK3568 Platform                               ║
╚══════════════════════════════════════════════════════════╝{Colors.END}
""")

    # 检测平台
    system = check_platform()

    # 检测各类硬件
    check_usb_devices()
    check_audio_devices()
    check_camera_devices()
    check_serial_devices()
    check_pwm_gpio()
    check_display()
    check_i2c()
    check_network()

    # 生成总结
    generate_summary(system)


if __name__ == "__main__":
    main()
