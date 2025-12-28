# 豆包语音助手 Demo

基于火山引擎豆包大模型的语音助手演示程序，集成了语音识别（ASR）、对话生成（Chat）和语音合成（TTS）三大功能。

## 功能特性

- **语音识别**：使用豆包流式语音识别模型2.0，支持实时语音转文字
- **智能对话**：使用 Doubao-Seed-1.6 推理模型进行多轮对话
- **语音合成**：使用豆包语音合成模型2.0，将 AI 回复转为语音播放
- **静音检测**：自动检测静音并结束录音
- **打断功能**：播放语音时可点击打断，立即开始新对话

## 环境要求

- Python 3.8+
- Windows / macOS / Linux
- 麦克风设备

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

复制示例配置文件：

```bash
cp api_secrets.example.py api_secrets.py
```

编辑 `api_secrets.py`，填入你的真实 API 密钥：

> **注意**：`api_secrets.py` 已被 `.gitignore` 忽略，不会提交到 Git 仓库。

### 3. 运行程序

```bash
python voice_assistant.py
```

## 使用说明

1. 点击 **🎤 点击说话** 按钮开始录音
2. 对着麦克风说话
3. 停止说话后，静音 3 秒自动结束录音（或手动点击结束）
4. 等待语音识别和 AI 回复
5. AI 回复会自动播放语音
6. 播放时可点击 **⏹️ 点击打断** 按钮打断播放并开始新对话

## 项目结构

```
chatbot/
├── voice_assistant.py    # 主程序
├── config.py                 # 配置文件（非敏感参数）
├── api_secrets.py            # 敏感配置（不提交到 git）
├── api_secrets.example.py    # 敏感配置示例
├── requirements.txt      # Python 依赖
├── .gitignore            # Git 忽略文件
├── README.md             # 说明文档
└── docs/                 # API 文档
    ├── asr.md            # 语音识别文档
    ├── tts.md            # 语音合成文档
    └── ...
```

## 配置说明

### 静音检测 (`config.py`)

```python
SILENCE_THRESHOLD = 1000  # 静音振幅阈值（500-1500）
SILENCE_TIMEOUT = 3.0     # 静音超时时间（秒）
```

### 语音识别接口

```python
# bigmodel_async: 双向流式优化版（推荐，需要2.0资源ID）
# bigmodel: 双向流式模式（需要1.0资源ID，实时性更好）
ASR_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
```

### TTS 音色

2.0 版本音色（需配合 `seed-tts-2.0`）：
- `zh_female_vv_uranus_bigtts` - Vivi 2.0（中英文）
- `zh_female_xiaohe_uranus_bigtts` - 小何 2.0（中文）
- `zh_male_m191_uranus_bigtts` - 云舟 2.0（中文）
- `zh_male_taocheng_uranus_bigtts` - 小天 2.0（中文）

完整音色列表：[火山引擎文档](https://www.volcengine.com/docs/6561/1257544)

## 代码结构说明

| 类/函数 | 功能 |
|--------|------|
| `AudioRecorder` | 音频录制器，负责从麦克风采集 PCM 数据 |
| `ASRWorker` | 流式语音识别工作线程，WebSocket 通信 |
| `ChatWorker` | 文本对话工作线程，调用 Doubao-Seed-1.6 |
| `TTSWorker` | 语音合成工作线程，调用豆包 TTS 并播放 |
| `WorkerSignals` | Qt 信号类，用于线程间通信 |
| `VoiceAssistantWindow` | 主窗口界面 |

## 数据流程

```
用户点击麦克风
    ↓
AudioRecorder 采集音频
    ↓
ASRWorker 流式发送音频 → 豆包语音识别 API
    ↓
实时返回识别文本 → 界面更新
    ↓
静音检测自动停止 / 用户手动停止
    ↓
ChatWorker 发送文本 → Doubao-Seed-1.6 API
    ↓
返回 AI 回复 → 界面更新
    ↓
TTSWorker 发送文本 → 豆包语音合成 API
    ↓
返回音频数据 → pygame 播放
    ↓
播放完成 / 用户打断 → 恢复初始状态
```

## 常见问题

### 1. 麦克风无法使用

- 检查系统是否授权应用使用麦克风
- 运行程序时会打印可用的音频设备列表，确认麦克风已识别

### 2. WebSocket 连接失败 (HTTP 400)

- 检查资源 ID 是否与接口匹配
- `bigmodel_async` 需要 2.0 资源 ID：`volc.seedasr.sauc.duration`
- `bigmodel` 需要 1.0 资源 ID：`volc.bigasr.sauc.duration`

### 3. TTS 错误：resource ID is mismatched

- 检查音色与资源 ID 是否匹配
- 2.0 音色（`*_uranus_bigtts`）需配合 `seed-tts-2.0`
- 1.0 音色（`*_moon_bigtts`/`*_mars_bigtts`）需配合 `seed-tts-1.0`

### 4. 识别结果显示延迟

- `bigmodel_async` 是优化版本，只在结果变化时返回
- 如需更实时的显示，可尝试使用 `bigmodel`（需要 1.0 资源 ID）

### 5. ImportError: 请先创建 api_secrets.py 文件

- 按照"配置 API 密钥"步骤，复制 `api_secrets.example.py` 为 `api_secrets.py` 并填入真实密钥

## 许可证

MIT License

本项目仅供学习和演示使用。使用豆包 API 需遵守火山引擎服务条款。
