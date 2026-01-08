#!/bin/bash
# 嵌入式机器人依赖安装脚本
# 适用于 RK3568 Ubuntu 20.04 aarch64

set -e

echo "=========================================="
echo "  嵌入式陪伴机器人 - 依赖安装脚本"
echo "  目标平台: RK3568 aarch64"
echo "=========================================="

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

# 更新包管理器
echo ""
echo "[1/7] 更新系统包..."
$SUDO apt update

# 安装基础工具
echo ""
echo "[2/7] 安装基础工具..."
$SUDO apt install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    pkg-config

# 安装音频相关依赖
echo ""
echo "[3/7] 安装音频依赖..."
$SUDO apt install -y \
    libasound2-dev \
    portaudio19-dev \
    libportaudio2 \
    alsa-utils \
    mpg123 \
    ffmpeg

# 安装视觉相关依赖
echo ""
echo "[4/7] 安装视觉依赖..."
$SUDO apt install -y \
    libopencv-dev \
    python3-opencv

# 安装 Python 开发依赖
echo ""
echo "[5/7] 安装 Python 开发依赖..."
$SUDO apt install -y \
    python3-dev \
    python3-pip \
    python3-venv

# 创建虚拟环境（如果不存在）
echo ""
echo "[6/7] 设置 Python 虚拟环境..."
VENV_PATH="$HOME/robot_env"
if [ ! -d "$VENV_PATH" ]; then
    echo "创建虚拟环境: $VENV_PATH"
    python3 -m venv "$VENV_PATH"
fi

# 激活虚拟环境
source "$VENV_PATH/bin/activate"

# 升级 pip
pip install --upgrade pip

# 安装 Python 依赖
echo ""
echo "[7/7] 安装 Python 依赖..."
pip install -r requirements.txt

echo ""
echo "=========================================="
echo "  基础依赖安装完成！"
echo "=========================================="

# 可选依赖提示
echo ""
echo "=== 可选依赖 ==="
echo ""
echo "1. 人脸识别 (需要编译 dlib，约 30 分钟):"
echo "   pip install dlib"
echo "   pip install face_recognition"
echo ""
echo "2. 物体检测 (YOLOv8):"
echo "   pip install ultralytics"
echo ""
echo "3. 声纹识别:"
echo "   pip install resemblyzer webrtcvad"
echo ""
echo "4. Porcupine 语音唤醒 (需要 API Key):"
echo "   pip install pvporcupine"
echo ""

# 配置 ALSA
echo "=== 配置 ALSA ==="
echo ""
echo "请运行以下命令测试音频设备:"
echo "  arecord -l     # 列出录音设备"
echo "  aplay -l       # 列出播放设备"
echo "  alsamixer      # 调整音量"
echo ""

# 创建日志目录
$SUDO mkdir -p /var/log/robot
$SUDO chown $USER:$USER /var/log/robot

# 设置 udev 规则（USB 设备权限）
echo "=== 设置 USB 设备权限 ==="
UDEV_RULE="/etc/udev/rules.d/99-robot.rules"
if [ ! -f "$UDEV_RULE" ]; then
    echo "创建 udev 规则..."
    $SUDO bash -c "cat > $UDEV_RULE << 'EOF'
# USB 摄像头
SUBSYSTEM==\"video4linux\", MODE=\"0666\"

# USB 串口
SUBSYSTEM==\"tty\", ATTRS{idVendor}==\"10c4\", MODE=\"0666\"

# 雷达
SUBSYSTEM==\"tty\", ATTRS{idVendor}==\"10c4\", ATTRS{idProduct}==\"ea60\", SYMLINK+=\"rplidar\", MODE=\"0666\"

# 深度相机 Nebula
SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"2b5f\", MODE=\"0666\"
EOF"
    $SUDO udevadm control --reload-rules
    $SUDO udevadm trigger
    echo "udev 规则已创建"
fi

echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "下一步:"
echo "1. 复制 api_secrets.example.py 为 api_secrets.py"
echo "   cp api_secrets.example.py api_secrets.py"
echo ""
echo "2. 编辑 api_secrets.py 填入 API 密钥"
echo "   nano api_secrets.py"
echo ""
echo "3. 运行机器人"
echo "   source ~/robot_env/bin/activate"
echo "   python main.py"
echo ""
