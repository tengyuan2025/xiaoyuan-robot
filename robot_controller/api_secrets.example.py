# -*- coding: utf-8 -*-
"""
API 密钥配置模板

使用前请复制此文件为 api_secrets.py 并填入真实的 API 密钥

    cp api_secrets.example.py api_secrets.py
"""

# ============================================================
# 火山引擎豆包 API 密钥
# 申请地址: https://console.volcengine.com/
# ============================================================

# 语音识别 (ASR)
ASR_APPID = "your_asr_appid"
ASR_ACCESS_TOKEN = "your_asr_access_token"

# 对话模型 (Chat)
CHAT_API_KEY = "your_chat_api_key"

# 语音合成 (TTS)
TTS_APPID = "your_tts_appid"
TTS_ACCESS_TOKEN = "your_tts_access_token"


# ============================================================
# 可选：Picovoice Porcupine 语音唤醒
# 申请地址: https://picovoice.ai/
# ============================================================

PORCUPINE_ACCESS_KEY = ""
