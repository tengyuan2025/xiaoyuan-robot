# 安装指南

本文档提供 xiaoyuan-robot 项目在不同系统上的安装步骤。

## 系统要求

- Python 3.9+
- USB 外置麦克风（必需）
- 网络连接
- 豆包语音识别 API 密钥

---

## 快速安装

### 1. 克隆或下载项目

```bash
cd /path/to/your/workspace
# 如果是 git 仓库
git clone <repository-url> xiaoyuan-robot
cd xiaoyuan-robot

# 或者直接复制项目文件夹
```

### 2. 创建虚拟环境（推荐）

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate     # Windows
```

### 3. 安装依赖

#### macOS

```bash
# 1. 安装 PortAudio（PyAudio 的依赖）
brew install portaudio

# 2. 安装 FFmpeg（音频处理）
brew install ffmpeg

# 3. 安装 Python 依赖
pip install -r requirements.txt
```

#### Linux (Ubuntu/Debian)

```bash
# 1. 安装系统依赖
sudo apt-get update
sudo apt-get install -y portaudio19-dev python3-pyaudio ffmpeg

# 2. 安装 Python 依赖
pip install -r requirements.txt
```

#### Windows

```bash
# 1. 安装 FFmpeg
# 从 https://ffmpeg.org/download.html 下载并添加到 PATH

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 注意：如果 PyAudio 安装失败，从以下地址下载对应版本的 .whl 文件：
# https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
# 然后运行：pip install PyAudio-xxx.whl
```

---

## 配置 API 密钥

### 1. 获取豆包 API 密钥

访问 [火山引擎控制台](https://console.volcengine.com/speech/) 获取：
- APP ID
- Access Token
- 开通 "豆包流式语音识别模型2.0"

### 2. 配置密钥

密钥已经在代码中配置（`realtime_mic_asr.py` 第 35-38 行）。

如需修改：
```python
# 豆包API配置（豆包流式语音识别模型2.0）
APP_ID = "your_app_id"
ACCESS_KEY = "your_access_token"
WSS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
```

---

## 验证安装

### 1. 检查音频设备

```bash
python3 list_audio_devices.py
```

确保能看到你的 USB 麦克风设备。

### 2. 测试运行

```bash
python3 realtime_mic_asr.py
```

如果看到以下信息，说明安装成功：
```
============================================================
实时麦克风语音识别
============================================================
配置信息:
  - 音频设备: [X] USB Audio Device
  - 采样率: 16000Hz
  ...
✓ 已锁定 USB 外置麦克风
请对着麦克风说话，按 Ctrl+C 停止...
```

---

## 常见问题

### PyAudio 安装失败

**macOS:**
```bash
brew install portaudio
pip install pyaudio
```

**Linux:**
```bash
sudo apt-get install portaudio19-dev
pip install pyaudio
```

**Windows:**
下载预编译的 wheel 文件：
https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

### 找不到 USB 麦克风

**解决方案:**
1. 确保 USB 麦克风已连接
2. 运行 `python3 list_audio_devices.py` 查看设备列表
3. 在系统设置中检查麦克风权限
4. 重新插拔 USB 设备

### WebSocket 连接失败

**可能原因:**
- 网络连接问题
- API 密钥错误
- 服务未开通

**解决方案:**
1. 检查网络连接
2. 验证 API 密钥是否正确
3. 确认火山引擎控制台中服务已激活

### 权限错误

**macOS/Linux:**
```bash
# 给予麦克风访问权限
# 在系统设置 → 隐私与安全 → 麦克风 中允许终端访问
```

---

## 文件说明

- `realtime_mic_asr.py` - 实时麦克风语音识别主程序
- `list_audio_devices.py` - 查看音频设备列表
- `test_credentials.py` - 测试 API 配置
- `wait_for_service.py` - 等待服务激活
- `requirements.txt` - Python 依赖列表
- `CLAUDE.md` - 项目架构说明
- `chat_history.md` - 完整的开发过程记录

---

## 使用说明

### 实时麦克风识别

```bash
python3 realtime_mic_asr.py
```

对着麦克风说话，实时显示识别结果。按 `Ctrl+C` 停止。

### 文件音频识别

```bash
python3 sauc_python/sauc_websocket_demo.py --file /path/to/audio.wav
```

---

## 技术支持

如有问题，请查看：
- `CLAUDE.md` - 项目技术文档
- `chat_history.md` - 常见问题解决方案
- [豆包语音识别文档](https://www.volcengine.com/docs/6561/79818)

---

**安装完成后，建议阅读 `CLAUDE.md` 了解项目架构！**
