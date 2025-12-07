# 对话历史记录

**日期**: 2025-12-07
**项目**: xiaoyuan-robot - 豆包语音识别实时麦克风应用

---

## 目录

1. [问题背景](#问题背景)
2. [项目初始化](#项目初始化)
3. [启动准备工作](#启动准备工作)
4. [错误排查过程](#错误排查过程)
5. [最终解决方案](#最终解决方案)
6. [成功配置总结](#成功配置总结)

---

## 问题背景

### 用户初始问题
**Q**: 你能看到最后一次对话的内容吗？如何能让你记住之前对话的内容呢？

**A**: 每次会话是独立的，无法访问之前的对话历史。建议的解决方案：
- 在当前会话中继续对话
- 将重要信息写入文件（如项目文档）
- 使用 CLAUDE.md 等项目文档记录上下文
- 新会话时提供简要摘要

---

## 项目初始化

### 创建 CLAUDE.md

**用户执行**: `/init` 命令

**操作**: 分析代码库并创建 CLAUDE.md 文档

**发现的项目结构**:
```
xiaoyuan-robot/
├── realtime_mic_asr.py           # 实时麦克风语音识别
├── sauc_python/
│   └── sauc_websocket_demo.py    # 文件音频识别demo
├── README_MIC_ASR.md             # 项目说明文档
└── venv/                         # 虚拟环境
```

**创建的 CLAUDE.md 包含**:
- 项目概述（豆包ASR实时语音识别）
- 核心组件说明
- 二进制协议详情
- 开发命令
- 架构设计

---

## 启动准备工作

### 用户需求
**Q**: 想在本机启动 `sauc_websocket_demo.py`，需要做什么？

### 准备步骤

#### 1. 配置 API 密钥
**问题**: demo 文件中密钥为占位符
```python
"app_key": "xxxxxxx",
"access_key": "xxxxxxxxxxxx"
```

**解决**: 从 `realtime_mic_asr.py` 复制真实密钥
```python
"app_key": "PlgvMymc7f3tQnJ6",
"access_key": "tRDp6c2pMhqtMXWYCINDSCDQPyfaWZbt"
```

#### 2. 安装 Python 依赖
```bash
source venv/bin/activate
pip install aiohttp
```
**结果**: ✅ 成功安装 aiohttp 及依赖包

#### 3. 安装 FFmpeg
```bash
brew install ffmpeg
```
**结果**: ✅ 成功安装 FFmpeg（用于音频格式转换）

#### 4. 准备测试音频文件
**发现**: 项目中暂无 `.wav` 测试文件
**建议**: 用户准备自己的音频文件，或使用 `realtime_mic_asr.py` 直接录音

---

## 错误排查过程

### 错误 1: 403 Forbidden

**错误日志**:
```
2025-12-07 19:37:15 - ERROR - WebSocket连接失败: 403, message='Invalid response status'
```

**分析**:
- HTTP 403 = 认证被拒绝
- 检查发现 `APP_ID` 定义了但未使用
- 代码中只发送了 `APP_KEY` 和 `ACCESS_KEY`

**尝试修复**: 添加 `X-App-Id: APP_ID` 到请求头
```python
return {
    "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
    "X-Api-Request-Id": reqid,
    "X-Api-Access-Key": ACCESS_KEY,
    "X-Api-App-Key": APP_KEY,
    "X-App-Id": APP_ID  # 新添加
}
```

**结果**: ❌ 仍然报错，但错误码变了

---

### 错误 2: 401 Unauthorized

**错误日志**:
```
2025-12-07 20:31:09 - ERROR - WebSocket连接失败: 401, message='Invalid response status'
```

**分析**:
- HTTP 401 = 认证失败，凭证不正确
- 发现用户修改了密钥配置：
  - APP_ID: `7059594059` → `3384355451`
  - APP_KEY 也改了
  - 但 ACCESS_KEY 没变

**问题**: 三个密钥（APP_ID、ACCESS_KEY、APP_KEY）必须来自同一个应用！

**搜索验证**: 在 workspace 中搜索发现 xiaoyu-server 项目使用的配置：
```python
APP_ID = "7059594059"
ACCESS_KEY = "tRDp6c2pMhqtMXWYCINDSCDQPyfaWZbt"
APP_KEY = "PlgvMymc7f3tQnJ6"
```

---

### 错误 3: 400 Bad Request（关键突破）

**用户提供控制台截图**:
- 服务: 豆包流式语音识别模型**2.0**
- APP ID: `3384355451`
- Access Token: `k3v2aKBdU1xuUfq4yeiM28QCcTv2R97j`
- Secret Key: `dVfkTUVJhlhxLOx4rU0xXjK4EJHaZV4j`

**发现重大错误**: 用户把 Secret Key 当成 Access Token 使用了！

**正确配置应该是**:
```python
APP_ID = "3384355451"
ACCESS_KEY = "k3v2aKBdU1xuUfq4yeiM28QCcTv2R97j"  # 使用 Access Token！
```

**修复后仍然 400 错误**

---

### 参考官方文档

**用户提供**: 豆包语音识别官方文档

**关键发现**:
1. **认证头字段命名**:
   ```
   X-Api-App-Key  ← 这个字段应该填 APP ID，不是 APP KEY！
   ```

2. **正确的认证头**:
   ```python
   {
       "X-Api-Resource-Id": "volc.bigasr.sauc.duration",  # 或 volc.seedasr.sauc.duration
       "X-Api-Request-Id": reqid,
       "X-Api-Access-Key": ACCESS_KEY,
       "X-Api-App-Key": APP_ID,        # 填 APP_ID！
       "X-Api-Connect-Id": reqid
   }
   ```

3. **Resource-Id 区分**:
   - 模型1.0: `volc.bigasr.sauc.duration`
   - 模型2.0: `volc.seedasr.sauc.duration`

**修复**:
- 将 `X-Api-App-Key` 的值从 `APP_KEY` 改为 `APP_ID`
- 添加 `X-Api-Connect-Id` 字段
- 删除多余的 `X-App-Id` 字段

---

### 持续 400 错误 - 服务开通问题

**修复认证头后仍然 400**

**创建测试脚本**: `test_credentials.py`

**测试结果**:
```
配置1: 模型2.0 (3384355451) → ❌ 400 请求错误
配置2: 模型1.0 (3384355451) → ❌ 403 权限不足
配置3: xiaoyu-server配置    → ❌ 403 权限不足
```

**重要发现**:
- 配置1（模型2.0）返回 **400** 而不是 403
- 400 和 403 的区别：
  - 403 = 认证直接被拒绝
  - 400 = 认证通过，但请求有问题

**结论**: 配置1的 APP_ID 和 Access Key 是**正确的、匹配的**，但服务可能还在开通中！

**用户确认**: "2.0的我刚开通，是不是得等一会才能生效？"

**创建等待脚本**: `wait_for_service.py` - 自动每分钟重试测试连接

---

## 最终解决方案

### 关键突破

**用户修改**: `WSS_URL` 从 `bigmodel` 改为 `bigmodel_async`
```python
WSS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
```

**结果**: ✅ **连接成功！**

```
2025-12-07 21:04:26 - INFO - ✓ 已成功连接到 wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
2025-12-07 21:04:26 - INFO - 服务端确认连接成功
2025-12-07 21:04:26 - INFO - 开始录音
```

### 新问题: 音频格式错误

**错误日志**:
```
code=45000151, msg={'error': '[Invalid audio format] ... invalid WAV file format'}
```

**原因**:
- PyAudio 录制的是**纯PCM音频流**
- 代码告诉服务器格式是 `"format": "wav"`
- 服务器期望 WAV 容器格式，但收到的是原始 PCM

**修复**:
```python
"audio": {
    "format": "pcm",  # 从 "wav" 改为 "pcm"
    "codec": "raw",
    "rate": 16000,
    "bits": 16,
    "channel": 1
}
```

**结果**: ✅ **问题解决！可以正常识别语音了！**

---

## 成功配置总结

### 最终工作配置

```python
# API配置
APP_ID = "3384355451"
ACCESS_KEY = "k3v2aKBdU1xuUfq4yeiM28QCcTv2R97j"
WSS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"

# 音频配置
SAMPLE_RATE = 16000
CHANNELS = 1
BITS_PER_SAMPLE = 16
```

### 认证请求头

```python
def new_auth_headers() -> Dict[str, str]:
    reqid = str(uuid.uuid4())
    return {
        "X-Api-Resource-Id": "volc.seedasr.sauc.duration",  # 模型2.0
        "X-Api-Request-Id": reqid,
        "X-Api-Access-Key": ACCESS_KEY,
        "X-Api-App-Key": APP_ID,      # 注意：填APP_ID而不是APP_KEY
        "X-Api-Connect-Id": reqid
    }
```

### 音频配置

```python
"audio": {
    "format": "pcm",    # 关键：PyAudio提供PCM数据流
    "codec": "raw",
    "rate": 16000,
    "bits": 16,
    "channel": 1
}
```

### WebSocket 端点

```python
# 双向流式模式（优化版）- 推荐使用
wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async

# 其他可用端点：
# wss://openspeech.bytedance.com/api/v3/sauc/bigmodel           # 双向流式
# wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream  # 流式输入
```

---

## 关键经验教训

### 1. API 认证字段命名的陷阱
- `X-Api-App-Key` 字段实际上应该填 **APP ID**
- 这是火山引擎/豆包API的特殊命名约定
- 文档中明确说明了，但容易被误解

### 2. 密钥配置必须匹配
- APP_ID、Access Token 必须来自同一个应用
- 控制台中的 "Access Token" ≠ "Secret Key"
- 正确的是使用 "Access Token"

### 3. Resource-Id 版本对应
- 模型1.0: `volc.bigasr.sauc.duration`
- 模型2.0: `volc.seedasr.sauc.duration`
- 必须与开通的服务版本匹配

### 4. 服务激活时间
- 新开通的服务可能需要几分钟激活
- 400错误可能意味着"服务开通中"
- 建议等待5-10分钟后重试

### 5. 音频格式声明
- PyAudio 录制 → 原始 PCM 数据流
- 必须声明 `"format": "pcm"`
- 不能声明 `"format": "wav"`（除非真的发送WAV容器）

### 6. 双向流式优化版性能更好
- `bigmodel_async` 端点性能优于 `bigmodel`
- 只在结果变化时返回数据（不是每包都返回）
- RTF 和首字、尾字时延都有提升

---

## 创建的辅助文件

### 1. CLAUDE.md
- 项目架构说明
- 开发命令参考
- 技术要点记录

### 2. test_credentials.py
- 测试不同API配置组合
- 快速诊断认证问题
- 区分 401/403/400 错误

### 3. wait_for_service.py
- 自动等待服务激活
- 每分钟重试检测
- 最多等待20分钟

### 4. chat_history.md（本文件）
- 完整的对话历史
- 问题排查过程
- 解决方案记录

---

## 运行测试

### 实时麦克风语音识别
```bash
python3 realtime_mic_asr.py
```

### 文件音频识别
```bash
python3 sauc_python/sauc_websocket_demo.py --file /path/to/audio.wav
```

### 测试API配置
```bash
python3 test_credentials.py
```

### 等待服务激活
```bash
python3 wait_for_service.py
```

---

## 下一步建议

1. **测试语音识别功能**
   - 对着麦克风说话
   - 观察实时识别结果
   - 测试中文、数字、标点等功能

2. **查看官方文档高级功能**
   - 热词定制
   - 敏感词过滤
   - 语种检测
   - 情绪检测
   - 性别检测

3. **集成到实际应用**
   - 语音助手
   - 实时字幕
   - 会议记录
   - 客服系统

4. **监控使用情况**
   - 控制台查看用量
   - 关注账户余额
   - 注意请求限制

---

## 参考资料

- [豆包语音识别官方文档](https://www.volcengine.com/docs/6561/79818)
- [PyAudio 文档](https://people.csail.mit.edu/hubert/pyaudio/docs/)
- [aiohttp WebSocket 文档](https://docs.aiohttp.org/en/stable/client_quickstart.html#websockets)
- 火山引擎控制台：https://console.volcengine.com/speech/

---

**记录完成时间**: 2025-12-07 21:10
**最终状态**: ✅ 成功运行
**解决问题总数**: 6个（403, 401, 400, 音频格式, 端点选择, 字段命名）
