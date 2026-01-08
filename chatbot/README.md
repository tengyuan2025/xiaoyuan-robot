# 豆包语音助手 Demo

基于火山引擎豆包大模型的多模态语音助手演示程序，集成了语音识别（ASR）、对话生成（Chat）、语音合成（TTS）、人脸识别、物体检测、声纹识别和智能记忆七大功能。

## 功能特性

### 核心功能
- **语音识别**：使用豆包流式语音识别模型2.0，支持实时语音转文字
- **智能对话**：使用 Doubao-Seed-1.6 推理模型进行多轮对话
- **语音合成**：使用豆包语音合成模型2.0，将 AI 回复转为语音播放
- **流式处理**：Chat 流式返回 + TTS 流式合成，大幅降低响应延迟

### 视觉识别
- **人脸识别**：基于 face_recognition 库，支持人脸注册和识别
- **物体检测**：基于 YOLOv8，支持 80 类常见物体检测（中文标签）
- **摄像头拍照**：自动拍照并进行图文分析

### 声纹识别
- **说话人识别**：基于 Resemblyzer 的 d-vector 嵌入
- **自动注册**：首次对话后自动询问名字并记录声纹
- **身份识别**：再次对话时自动识别说话人

### 智能记忆（Mem0）
- **长期记忆**：基于 Mem0 服务存储用户偏好和重要信息
- **关键信息提取**：自动从对话中提取喜好、关系、事实等
- **上下文注入**：对话前自动搜索相关记忆，提供个性化回复
- **身份关联**：记忆与声纹识别联动，为每个用户维护独立记忆

### 交互优化
- **静音检测**：自动检测静音并结束录音
- **打断功能**：播放语音时可点击打断，立即开始新对话
- **意图识别**：自动识别"看看"、"记住我"等特殊意图

## 环境要求

- Python 3.8+
- Windows / macOS / Linux
- 麦克风设备
- 摄像头（可选，用于视觉识别功能）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

**Windows 用户注意**：
- `dlib` 安装可能需要 Visual Studio Build Tools
- 推荐使用预编译包：`pip install dlib-bin`
- 然后安装 face_recognition：`pip install face_recognition`

**macOS 用户**：
```bash
brew install cmake
pip install -r requirements.txt
```

### 2. 配置 API 密钥

复制示例配置文件：

```bash
cp api_secrets.example.py api_secrets.py
```

编辑 `api_secrets.py`，填入你的真实 API 密钥：

```python
# 语音识别 (ASR)
ASR_APPID = "你的APPID"
ASR_ACCESS_TOKEN = "你的ACCESS_TOKEN"
ASR_RESOURCE_ID = "volc.seedasr.sauc.duration"

# 对话模型 (Chat)
CHAT_API_KEY = "你的API_KEY"

# 语音合成 (TTS)
TTS_APPID = "你的APPID"
TTS_ACCESS_TOKEN = "你的ACCESS_TOKEN"
TTS_RESOURCE_ID = "seed-tts-2.0"
```

> **注意**：`api_secrets.py` 已被 `.gitignore` 忽略，不会提交到 Git 仓库。

### 3. 运行程序

```bash
python voice_assistant.py
```

## 使用说明

### 基础对话

1. 点击 **🎤 点击说话** 按钮开始录音
2. 对着麦克风说话
3. 停止说话后，静音 1.5 秒自动结束录音（或手动点击结束）
4. 等待语音识别和 AI 回复
5. AI 回复会自动播放语音
6. 播放时可点击 **⏹️ 点击打断** 按钮打断播放并开始新对话

### 视觉识别

| 语音指令 | 功能 |
|---------|------|
| "看看这是什么" / "你看到了什么" | 拍照 + 人脸识别 + 物体检测 |
| "这是谁" / "认识他吗" | 拍照 + 人脸识别 |
| "记住我" / "记住我的脸" | 拍照 + 人脸注册（会追问名字） |

### 声纹识别

- **首次对话**：系统会在对话结束后询问"请问怎么称呼你？"
- **说出名字**：系统记录声纹并回复"好的，{名字}，我记住你了！"
- **再次对话**：系统自动识别你的声音（相似度 > 0.75 即匹配成功）

## 项目结构

```
chatbot/
├── voice_assistant.py        # 主程序
├── config.py                 # 配置文件（非敏感参数）
├── api_secrets.py            # 敏感配置（不提交到 git）
├── api_secrets.example.py    # 敏感配置示例
├── requirements.txt          # Python 依赖
│
├── intent_handler.py         # 意图识别处理器
├── camera_utils.py           # 摄像头工具
├── face_recognition_utils.py # 人脸识别模块
├── object_detection_utils.py # YOLO 物体检测模块
├── speaker_recognition_utils.py # 声纹识别模块
├── mem0_client.py            # Mem0 记忆服务客户端
│
├── faces/                    # 人脸数据存储目录
│   └── encodings.json        # 已注册的人脸编码
├── voiceprints.json          # 已注册的声纹数据
│
├── .gitignore                # Git 忽略文件
├── README.md                 # 说明文档
└── docs/                     # 文档目录
    ├── asr.md                # 语音识别 API 文档
    ├── tts.md                # 语音合成 API 文档
    └── voice_assistant_flowchart.md  # 程序流程图
```

## 配置说明

### 静音检测 (`config.py`)

```python
SILENCE_THRESHOLD = 1000  # 静音振幅阈值（500-1500）
SILENCE_TIMEOUT = 1.5     # 静音超时时间（秒）
```

### 声纹识别 (`config.py`)

```python
SPEAKER_SIMILARITY_THRESHOLD = 0.75  # 匹配阈值（0.70-0.85）
SPEAKER_MIN_AUDIO_DURATION = 1.0     # 最小音频时长（秒）
```

### 人脸识别 (`config.py`)

```python
FACE_RECOGNITION_TOLERANCE = 0.6  # 匹配容差（0.4-0.6，越小越严格）
FACE_RECOGNITION_MODEL = "hog"    # 检测模型（hog快/cnn准）
```

### 智能记忆 (`config.py`)

```python
MEM0_BASE_URL = "http://tenyuan.tech:9000"  # Mem0 服务地址
MEM0_ENABLED = True                          # 是否启用记忆功能
MEM0_SEARCH_TOP_K = 5                        # 搜索返回的最大记忆条数
MEM0_SIMILARITY_THRESHOLD = 0.5              # 记忆相似度阈值
```

### TTS 音色

2.0 版本音色（需配合 `seed-tts-2.0`）：
- `zh_female_vv_uranus_bigtts` - Vivi 2.0（中英文）
- `zh_female_xiaohe_uranus_bigtts` - 小何 2.0（中文）
- `zh_male_m191_uranus_bigtts` - 云舟 2.0（中文）
- `zh_male_taocheng_uranus_bigtts` - 小天 2.0（中文）

完整音色列表：[火山引擎文档](https://www.volcengine.com/docs/6561/1257544)

## 代码结构说明

| 类/模块 | 功能 |
|--------|------|
| `AudioRecorder` | 音频录制器，负责从麦克风采集 PCM 数据 |
| `ASRWorker` | 流式语音识别工作线程，WebSocket 通信 |
| `ChatWorker` | 文本对话工作线程，调用 Doubao-Seed-1.6 |
| `StreamingTTSWorker` | 流式语音合成工作线程，边合成边播放 |
| `WorkerSignals` | Qt 信号类，用于线程间通信 |
| `VoiceAssistantWindow` | 主窗口界面 |
| `IntentHandler` | 意图识别处理器 |
| `FaceRecognitionManager` | 人脸识别管理器 |
| `ObjectDetector` | YOLO 物体检测器 |
| `SpeakerRecognitionManager` | 声纹识别管理器 |
| `Mem0Client` | Mem0 记忆服务客户端 |

## 数据流程

```
用户点击麦克风
    ↓
AudioRecorder 采集音频
    ↓
┌─────────────────────────────────────┐
│ 并行处理                             │
│ ├─ ASRWorker → 豆包语音识别 API      │
│ └─ 声纹提取 → 说话人匹配/暂存         │
└─────────────────────────────────────┘
    ↓
静音检测自动停止 / 用户手动停止
    ↓
意图判断 (IntentHandler)
    ├─ "看看" → 拍照 + 人脸识别 + YOLO → 本地结果
    ├─ "记住我" → 拍照 + 人脸编码 → 追问名字
    └─ 默认 → 纯文本对话
    ↓
┌─────────────────────────────────────┐
│ Mem0 搜索相关记忆                    │
│ → 注入上下文到 Chat 请求             │
└─────────────────────────────────────┘
    ↓
ChatWorker 流式请求 → Doubao-Seed-1.6 API
    ↓
┌─────────────────────────────────────┐
│ Mem0 异步存储（后台线程）            │
│ → 提取关键信息 → 存储到记忆服务       │
└─────────────────────────────────────┘
    ↓
StreamingTTSWorker 流式合成 → 豆包 TTS API
    ↓
pygame 播放音频
    ↓
播放完成检查
    ├─ 有待注册声纹 → 追问名字 → 注册 → 迁移记忆
    └─ 无 → 恢复初始状态
```

## 常见问题

### 1. 麦克风无法使用

- 检查系统是否授权应用使用麦克风
- 运行程序时会打印可用的音频设备列表，确认麦克风已识别

### 2. WebSocket 连接失败 (HTTP 400)

- 检查资源 ID 是否与接口匹配
- `bigmodel_async` 需要 2.0 资源 ID：`volc.seedasr.sauc.duration`

### 3. TTS 错误：resource ID is mismatched

- 检查音色与资源 ID 是否匹配
- 2.0 音色（`*_uranus_bigtts`）需配合 `seed-tts-2.0`

### 4. face_recognition 安装失败

Windows 用户推荐：
```bash
pip install dlib-bin
pip install face_recognition
```

### 5. 声纹识别不准确

- 调整 `SPEAKER_SIMILARITY_THRESHOLD`（默认 0.75）
- 降低阈值（如 0.70）可减少漏识别
- 提高阈值（如 0.80）可减少误识别
- 多次对话可累积声纹样本，提高准确率

### 6. YOLO 模型下载慢

首次运行会自动下载 YOLOv8n 模型（约 6MB），如网络慢可手动下载后放到工作目录。

### 7. ImportError: 请先创建 api_secrets.py 文件

按照"配置 API 密钥"步骤，复制 `api_secrets.example.py` 为 `api_secrets.py` 并填入真实密钥。

### 8. Mem0 服务连接失败

- 检查 `MEM0_BASE_URL` 是否正确
- 确认 Mem0 服务是否正常运行：`curl http://tenyuan.tech:9000/health`
- 如需禁用记忆功能，设置 `MEM0_ENABLED = False`

### 9. 记忆功能不生效

- 确认 `MEM0_ENABLED = True`
- 声纹识别正常工作后才会有 `current_user_id`
- 检查控制台是否有 `[Mem0]` 相关日志

## 许可证

MIT License

本项目仅供学习和演示使用。使用豆包 API 需遵守火山引擎服务条款。
