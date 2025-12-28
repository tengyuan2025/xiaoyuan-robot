# -*- coding: utf-8 -*-
"""
敏感配置文件示例

使用说明：
1. 复制此文件并重命名为 secrets.py
2. 将下面的占位符替换为你的真实 API 密钥
3. secrets.py 已被 .gitignore 忽略，不会被提交到 git

获取密钥：
- 火山引擎控制台: https://console.volcengine.com/
- 语音技术: https://console.volcengine.com/speech/app
"""

# ==================== 语音识别 (ASR) ====================
# 火山引擎控制台获取的 APPID
ASR_APPID = "your_asr_appid"

# 语音识别服务的 ACCESS_TOKEN
ASR_ACCESS_TOKEN = "your_asr_access_token"

# ASR 资源 ID
# 豆包流式语音识别模型1.0: volc.bigasr.sauc.duration
# 豆包流式语音识别模型2.0: volc.seedasr.sauc.duration
ASR_RESOURCE_ID = "volc.seedasr.sauc.duration"


# ==================== 对话模型 (Chat) ====================
# 火山引擎 API Key（用于 Doubao-Seed-1.6 模型）
CHAT_API_KEY = "your_chat_api_key"


# ==================== 语音合成 (TTS) ====================
# 语音合成服务的 APPID（可能与 ASR 相同）
TTS_APPID = "your_tts_appid"

# 语音合成服务的 ACCESS_TOKEN
TTS_ACCESS_TOKEN = "your_tts_access_token"

# TTS 资源 ID
# 豆包语音合成模型1.0: seed-tts-1.0
# 豆包语音合成模型2.0: seed-tts-2.0
TTS_RESOURCE_ID = "seed-tts-2.0"
