#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
硬件功能测试脚本
测试深度相机、雷达、舵机的功能性并读取设备数据

使用方法:
    python test_hardware.py          # 运行所有测试
    python test_hardware.py camera   # 仅测试深度相机
    python test_hardware.py lidar    # 仅测试雷达
    python test_hardware.py servo    # 仅测试舵机

在 RK3568 主控板上运行此脚本
"""

import sys
import os
import time
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_banner():
    """打印横幅"""
    print(f"""
{Colors.BOLD}{Colors.CYAN}
╔═══════════════════════════════════════════════════════════════╗
║               陪伴机器人硬件功能测试工具                        ║
║                   RK3568 Platform                              ║
║                                                                 ║
║  测试项目:                                                      ║
║    - 深度相机 (Nebula410)                                       ║
║    - 激光雷达 (RPLIDAR C1)                                      ║
║    - 舵机 (PWM)                                                 ║
╚═══════════════════════════════════════════════════════════════╝
{Colors.END}
""")


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*65}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {title}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*65}{Colors.END}")


def print_result(name: str, success: bool, details: str = ""):
    """打印测试结果"""
    if success:
        icon = f"{Colors.GREEN}[PASS]{Colors.END}"
    else:
        icon = f"{Colors.RED}[FAIL]{Colors.END}"

    print(f"\n{icon} {name}")
    if details:
        for line in details.strip().split('\n'):
            print(f"       {line}")


def test_depth_camera(interactive: bool = True) -> bool:
    """
    测试深度相机 (Nebula410)

    Returns:
        测试是否通过
    """
    print_section("深度相机 (Nebula410) 测试")

    try:
        from hardware.depth_camera import DepthCamera, detect_depth_cameras
    except ImportError as e:
        print(f"  {Colors.RED}导入模块失败: {e}{Colors.END}")
        print(f"  {Colors.YELLOW}提示: pip install opencv-python{Colors.END}")
        return False

    results = []

    # 1. 检测设备
    print("\n[1/4] 检测深度相机设备...")
    cameras = detect_depth_cameras()
    if cameras:
        for cam in cameras:
            print(f"      发现: {cam['device']} ({cam['type']})")
        results.append(("设备检测", True))
    else:
        print("      未检测到专用深度相机设备 (将尝试通用视频设备)")
        results.append(("设备检测", False))

    # 2. 打开相机
    print("\n[2/4] 尝试打开相机 (UVC 模式)...")
    camera = DepthCamera(device_id=-1)
    if camera.open():
        info = camera.get_info()
        print(f"      设备ID: {info.get('device_id', 'N/A')}")
        print(f"      分辨率: {info.get('width', 'N/A')}x{info.get('height', 'N/A')}")
        print(f"      帧率: {info.get('fps', 'N/A')} FPS")
        print(f"      后端: {info.get('backend', 'N/A')}")
        results.append(("打开相机", True))

        # 3. 读取帧
        print("\n[3/4] 读取测试帧...")
        success_count = 0
        for i in range(5):
            ret, frame = camera.read_frame()
            if ret and frame is not None:
                success_count += 1

        if success_count > 0:
            print(f"      成功读取 {success_count}/5 帧")
            print(f"      帧尺寸: {frame.shape}")
            results.append(("读取帧", True))

            # 保存测试图像
            try:
                import cv2
                test_img_path = "/tmp/depth_camera_test.jpg"
                cv2.imwrite(test_img_path, frame)
                print(f"      测试图像已保存: {test_img_path}")
            except Exception as e:
                print(f"      保存图像失败: {e}")
        else:
            print("      读取帧失败")
            results.append(("读取帧", False))

        # 4. 深度图测试
        print("\n[4/4] 读取深度数据...")
        ret, depth = camera.read_depth()
        if ret and depth is not None:
            print(f"      深度图尺寸: {depth.shape}")
            print(f"      深度值范围: {depth.min()} - {depth.max()}")

            # 计算中心区域平均深度
            h, w = depth.shape[:2]
            center_region = depth[h//3:2*h//3, w//3:2*w//3]
            avg_depth = center_region.mean()
            print(f"      中心区域平均值: {avg_depth:.1f}")
            results.append(("深度数据", True))
        else:
            print("      读取深度数据失败")
            results.append(("深度数据", False))

        camera.close()
    else:
        print("      打开相机失败")
        results.append(("打开相机", False))

    # 汇总结果
    passed = sum(1 for _, r in results if r)
    total = len(results)
    success = passed == total

    print(f"\n{Colors.BOLD}测试结果: {passed}/{total} 通过{Colors.END}")
    return success


def test_lidar(interactive: bool = True) -> bool:
    """
    测试激光雷达 (RPLIDAR C1)

    Returns:
        测试是否通过
    """
    print_section("激光雷达 (RPLIDAR C1) 测试")

    try:
        from hardware.lidar import Lidar, detect_lidar_ports
    except ImportError as e:
        print(f"  {Colors.RED}导入模块失败: {e}{Colors.END}")
        print(f"  {Colors.YELLOW}提示: pip install rplidar-roboticia pyserial{Colors.END}")
        return False

    results = []

    # 1. 检测串口
    print("\n[1/5] 检测可用串口...")
    ports = detect_lidar_ports()
    if ports:
        for port in ports:
            print(f"      发现: {port}")
        results.append(("串口检测", True))
    else:
        print("      未检测到可用串口")
        results.append(("串口检测", False))
        return False

    # 2. 连接雷达
    print("\n[2/5] 尝试连接雷达...")
    lidar = None

    # 按优先级尝试端口
    test_ports = ['/dev/ttyUSB1', '/dev/ttyUSB0'] + ports
    test_ports = list(dict.fromkeys(test_ports))  # 去重

    for port in test_ports:
        if not os.path.exists(port) and sys.platform.startswith('linux'):
            continue

        print(f"      尝试: {port}...")
        try:
            lidar = Lidar(port=port)
            if lidar.connect():
                print(f"      {Colors.GREEN}连接成功{Colors.END}")
                results.append(("连接雷达", True))
                break
            else:
                lidar = None
        except Exception as e:
            print(f"      连接失败: {e}")
            lidar = None

    if lidar is None:
        print("      无法连接雷达")
        results.append(("连接雷达", False))
        return False

    try:
        # 3. 获取设备信息
        print("\n[3/5] 获取设备信息...")
        info = lidar.get_info()
        device_info = info.get('device_info', {})
        print(f"      型号: {device_info.get('model', 'Unknown')}")
        print(f"      固件: {device_info.get('firmware', 'Unknown')}")
        print(f"      序列号: {device_info.get('serialnumber', 'Unknown')}")
        results.append(("设备信息", True))

        # 4. 执行扫描
        print("\n[4/5] 执行扫描测试...")
        lidar.start_scan()
        print("      等待电机稳定...")
        time.sleep(2)

        points = lidar.get_scan(200)
        print(f"      采集到 {len(points)} 个扫描点")

        if points:
            # 统计有效点
            valid_points = [p for p in points if p.distance > 0]
            print(f"      有效点数: {len(valid_points)}")

            if valid_points:
                min_dist = min(p.distance for p in valid_points)
                max_dist = max(p.distance for p in valid_points)
                avg_dist = sum(p.distance for p in valid_points) / len(valid_points)
                print(f"      距离范围: {min_dist:.0f}mm - {max_dist:.0f}mm")
                print(f"      平均距离: {avg_dist:.0f}mm")

                # 显示样例数据
                print("\n      扫描数据示例:")
                print("      角度(度)  | 距离(mm)  | 质量")
                print("      " + "-"*35)
                for p in valid_points[:8]:
                    print(f"      {p.angle:8.2f}  | {p.distance:8.1f}  | {p.quality:2d}")

            results.append(("扫描测试", True))
        else:
            print("      未获取到扫描数据")
            results.append(("扫描测试", False))

        # 5. 方向距离测试
        print("\n[5/5] 方向距离测试...")
        directions = [
            ("前方 (0度)", 0),
            ("右侧 (90度)", 90),
            ("后方 (180度)", 180),
            ("左侧 (270度)", 270),
        ]

        for name, angle in directions:
            dist = lidar.get_distance_at_angle(angle, tolerance=15)
            if dist:
                print(f"      {name}: {dist:.0f}mm")
            else:
                print(f"      {name}: N/A")

        results.append(("方向距离", True))

        lidar.stop_scan()

    finally:
        lidar.disconnect()

    # 汇总结果
    passed = sum(1 for _, r in results if r)
    total = len(results)
    success = passed == total

    print(f"\n{Colors.BOLD}测试结果: {passed}/{total} 通过{Colors.END}")
    return success


def test_servo(interactive: bool = True) -> bool:
    """
    测试舵机 (PWM)

    Returns:
        测试是否通过
    """
    print_section("舵机 (PWM) 测试")

    try:
        from hardware.servo import Servo, ServoController, detect_pwm_chips, DEFAULT_SERVO_CONFIGS
    except ImportError as e:
        print(f"  {Colors.RED}导入模块失败: {e}{Colors.END}")
        return False

    results = []

    # 1. 检测 PWM 控制器
    print("\n[1/4] 检测 PWM 控制器...")
    chips = detect_pwm_chips()
    if chips:
        for chip in chips:
            print(f"      发现: pwmchip{chip['chip']} ({chip['channels']} 个通道)")
        results.append(("PWM 控制器检测", True))
    else:
        print("      未检测到 PWM 控制器")
        print(f"      {Colors.YELLOW}提示: 此测试需要在 RK3568 等嵌入式 Linux 上运行{Colors.END}")
        results.append(("PWM 控制器检测", False))
        return False

    # 2. 检查权限
    print("\n[2/4] 检查 PWM 权限...")
    chip_path = chips[0]['path']
    export_path = os.path.join(chip_path, "export")

    if os.path.exists(export_path):
        if os.access(export_path, os.W_OK):
            print("      PWM 导出权限: OK")
            results.append(("PWM 权限", True))
        else:
            print("      PWM 导出权限: 需要 root 权限")
            print(f"      {Colors.YELLOW}提示: 使用 sudo 运行或配置 udev 规则{Colors.END}")
            results.append(("PWM 权限", False))
    else:
        print(f"      未找到: {export_path}")
        results.append(("PWM 权限", False))
        return False

    # 3. 初始化舵机
    print("\n[3/4] 初始化舵机...")
    controller = ServoController()

    # 尝试初始化第一个舵机
    first_servo_name = list(DEFAULT_SERVO_CONFIGS.keys())[0]
    first_config = DEFAULT_SERVO_CONFIGS[first_servo_name]
    print(f"      测试舵机: {first_config.name}")
    print(f"      PWM: pwmchip{first_config.pwm_chip}/pwm{first_config.pwm_channel}")

    servo = Servo(first_config)
    if servo.init():
        print("      初始化: 成功")
        results.append(("舵机初始化", True))

        # 4. 测试移动
        print("\n[4/4] 测试舵机移动...")

        if interactive:
            print(f"      {Colors.YELLOW}即将移动舵机，请确保安全！{Colors.END}")
            input("      按 Enter 继续...")

        print(f"      当前角度: {servo.get_angle()}")

        # 测试基本移动
        test_angles = [45, 90, 135, 90]
        for angle in test_angles:
            print(f"      移动到: {angle} 度")
            servo.set_angle(angle)
            time.sleep(0.3)

        # 平滑移动测试
        print("      平滑移动: 90 -> 0 -> 90")
        servo.move_smooth(0, 0.8)
        servo.move_smooth(90, 0.8)

        print(f"      最终角度: {servo.get_angle()}")
        results.append(("舵机移动", True))

        servo.deinit()
    else:
        print("      初始化: 失败")
        results.append(("舵机初始化", False))

    # 汇总结果
    passed = sum(1 for _, r in results if r)
    total = len(results)
    success = passed == total

    print(f"\n{Colors.BOLD}测试结果: {passed}/{total} 通过{Colors.END}")
    return success


def run_all_tests(interactive: bool = True) -> dict:
    """
    运行所有硬件测试

    Returns:
        测试结果字典
    """
    results = {}

    print_banner()

    # 深度相机测试
    try:
        results['depth_camera'] = test_depth_camera(interactive)
    except Exception as e:
        print(f"\n{Colors.RED}深度相机测试异常: {e}{Colors.END}")
        results['depth_camera'] = False

    # 雷达测试
    try:
        results['lidar'] = test_lidar(interactive)
    except Exception as e:
        print(f"\n{Colors.RED}雷达测试异常: {e}{Colors.END}")
        results['lidar'] = False

    # 舵机测试
    try:
        results['servo'] = test_servo(interactive)
    except Exception as e:
        print(f"\n{Colors.RED}舵机测试异常: {e}{Colors.END}")
        results['servo'] = False

    # 打印总结
    print_section("测试总结")

    all_passed = all(results.values())
    for name, passed in results.items():
        status = f"{Colors.GREEN}PASS{Colors.END}" if passed else f"{Colors.RED}FAIL{Colors.END}"
        display_name = {
            'depth_camera': '深度相机 (Nebula410)',
            'lidar': '激光雷达 (RPLIDAR C1)',
            'servo': '舵机 (PWM)',
        }.get(name, name)
        print(f"  [{status}] {display_name}")

    if all_passed:
        print(f"\n{Colors.GREEN}{Colors.BOLD}所有硬件测试通过！{Colors.END}")
    else:
        failed = [n for n, p in results.items() if not p]
        print(f"\n{Colors.YELLOW}{Colors.BOLD}部分测试未通过: {', '.join(failed)}{Colors.END}")
        print(f"\n{Colors.YELLOW}故障排除建议:{Colors.END}")
        print("  1. 确保硬件正确连接")
        print("  2. 检查串口/USB 权限 (添加用户到 dialout 组)")
        print("  3. 确保安装了必要的 Python 库")
        print("  4. 对于舵机测试，可能需要 sudo 权限")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='机器人硬件功能测试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_hardware.py          # 运行所有测试
  python test_hardware.py camera   # 仅测试深度相机
  python test_hardware.py lidar    # 仅测试雷达
  python test_hardware.py servo    # 仅测试舵机
  python test_hardware.py --no-interactive  # 非交互模式运行
        """
    )
    parser.add_argument(
        'test',
        nargs='?',
        choices=['all', 'camera', 'lidar', 'servo'],
        default='all',
        help='要运行的测试 (默认: all)'
    )
    parser.add_argument(
        '--no-interactive', '-n',
        action='store_true',
        help='非交互模式 (不等待用户输入)'
    )

    args = parser.parse_args()
    interactive = not args.no_interactive

    if args.test == 'all':
        results = run_all_tests(interactive)
        sys.exit(0 if all(results.values()) else 1)
    elif args.test == 'camera':
        print_banner()
        success = test_depth_camera(interactive)
        sys.exit(0 if success else 1)
    elif args.test == 'lidar':
        print_banner()
        success = test_lidar(interactive)
        sys.exit(0 if success else 1)
    elif args.test == 'servo':
        print_banner()
        success = test_servo(interactive)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
