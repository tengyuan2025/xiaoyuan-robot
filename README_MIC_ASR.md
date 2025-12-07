# 实时麦克风语音识别脚本

## 功能说明

这个脚本可以将麦克风的音频实时发送给豆包流式语音识别服务，并打印出识别结果。

## 特性

- ✅ 实时麦克风录音
- ✅ 流式语音识别
- ✅ 实时显示识别结果（临时结果和最终结果）
- ✅ 使用豆包 SAUC BigModel 模型
- ✅ 支持标点符号、数字转换等功能
- ✅ 优雅的中断处理（Ctrl+C）

## 技术栈

- **音频采集**: PyAudio
- **网络通信**: aiohttp (WebSocket)
- **语音识别**: 豆包 SAUC API
- **异步框架**: asyncio

## 音频配置

- 采样率: 16000 Hz
- 声道数: 1 (单声道)
- 位深: 16 bit
- 格式: PCM
- 分段时长: 200ms

## 依赖安装

```bash
pip install pyaudio aiohttp
```

### macOS 安装 PyAudio

```bash
brew install portaudio
pip install pyaudio
```

### Linux 安装 PyAudio

```bash
sudo apt-get install portaudio19-dev python3-pyaudio
pip install pyaudio
```

## 使用方法

### 基本使用

```bash
python realtime_mic_asr.py
```

### 运行示例

```
==============================================================
实时麦克风语音识别
==============================================================
配置信息:
  - 采样率: 16000Hz
  - 声道数: 1
  - 位深: 16bit
  - 服务: wss://openspeech.bytedance.com/api/v3/sauc/bigmodel
==============================================================

请对着麦克风说话，按 Ctrl+C 停止...

2025-12-05 10:30:15 - INFO - 已连接到 wss://openspeech.bytedance.com/api/v3/sauc/bigmodel
2025-12-05 10:30:15 - INFO - 已发送完整客户端请求 (seq: 1)
2025-12-05 10:30:15 - INFO - 服务端确认连接成功
2025-12-05 10:30:15 - INFO - 开始录音 - 采样率: 16000Hz, 声道: 1, 位深: 16bit
2025-12-05 10:30:15 - INFO - 开始发送音频流...
2025-12-05 10:30:15 - INFO - 开始接收识别结果...

[临时] 识别结果: 你好
[临时] 识别结果: 你好世界
[最终] 识别结果: 你好，世界！

[临时] 识别结果: 今天天气
[临时] 识别结果: 今天天气真不错
[最终] 识别结果: 今天天气真不错。
```

### 停止识别

按 `Ctrl+C` 可以随时停止识别：

```
^C
正在停止录音...
2025-12-05 10:35:20 - INFO - 用户中断
2025-12-05 10:35:20 - INFO - 停止录音

程序结束
```

## API配置

脚本使用的豆包API配置（从xiaoyu-server项目获取）：

```python
APP_ID = "7059594059"
ACCESS_KEY = "tRDp6c2pMhqtMXWYCINDSCDQPyfaWZbt"
APP_KEY = "PlgvMymc7f3tQnJ6"
WSS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
```

## 工作原理

1. **初始化连接**: 建立WebSocket连接并发送初始配置请求
2. **音频采集**: PyAudio实时从麦克风采集音频数据
3. **数据分段**: 将音频数据按200ms分段
4. **流式发送**: 将音频段实时发送给豆包ASR服务
5. **结果接收**: 异步接收识别结果（临时结果和最终结果）
6. **结果展示**: 实时打印识别结果

## 识别结果说明

- **[临时]**: 中间识别结果，可能会变化
- **[最终]**: 最终确定的识别结果

## 启用的功能

- `enable_itn`: 数字转换（如"一千二百三十四" → "1234"）
- `enable_punc`: 标点符号添加
- `enable_ddc`: 语音端点检测
- `show_utterances`: 显示分句结果
- `enable_nonstream`: 非流式模式（设为False以启用流式）

## 日志级别

修改脚本中的日志级别查看更多详细信息：

```python
# 修改这一行
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG 查看详细日志
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

## 常见问题

### 1. 麦克风无法使用

**问题**: `IOError: [Errno -9996] Invalid input device`

**解决方案**:
- 检查麦克风是否正确连接
- 在系统设置中授权麦克风权限
- 尝试列出可用的音频设备

### 2. PyAudio安装失败

**macOS**:
```bash
brew install portaudio
pip install pyaudio
```

**Linux**:
```bash
sudo apt-get install portaudio19-dev
pip install pyaudio
```

### 3. WebSocket连接失败

**问题**: 连接超时或认证失败

**解决方案**:
- 检查网络连接
- 确认API密钥是否正确
- 检查防火墙设置

### 4. 无识别结果

**可能原因**:
- 麦克风音量太小
- 环境噪音太大
- 说话距离麦克风太远

**解决方案**:
- 调整麦克风音量
- 在安静环境中测试
- 靠近麦克风说话

## 代码结构

```
realtime_mic_asr.py
├── AsrRequestHeader        # 请求头构造器
├── RequestBuilder          # 请求构造器
├── AsrResponse             # 响应对象
├── ResponseParser          # 响应解析器
├── MicrophoneRecorder      # 麦克风录音器
└── RealtimeMicASRClient    # 实时ASR客户端
```

## 参考资料

- [豆包语音识别API文档](https://www.volcengine.com/docs/6561/79818)
- [PyAudio文档](https://people.csail.mit.edu/hubert/pyaudio/docs/)
- [aiohttp WebSocket文档](https://docs.aiohttp.org/en/stable/client_quickstart.html#websockets)

## 许可证

本脚本参考了豆包官方SDK示例代码（sauc_python/sauc_websocket_demo.py）。
