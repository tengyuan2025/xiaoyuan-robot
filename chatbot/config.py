# -*- coding: utf-8 -*-
"""
语音助手配置文件

使用说明：
1. 复制 secrets.example.py 为 secrets.py
2. 在 secrets.py 中填入真实的 API 密钥
3. secrets.py 已被 .gitignore 忽略，不会提交到 git
"""

import os

# 导入敏感配置
try:
    from api_secrets import (
        ASR_APPID, ASR_ACCESS_TOKEN, ASR_RESOURCE_ID,
        CHAT_API_KEY,
        TTS_APPID, TTS_ACCESS_TOKEN, TTS_RESOURCE_ID
    )
except ImportError:
    raise ImportError(
        "请先创建 api_secrets.py 文件！\n"
        "1. 复制 api_secrets.example.py 为 api_secrets.py\n"
        "2. 在 api_secrets.py 中填入真实的 API 密钥"
    )

# ==================== 豆包语音识别配置 ====================
# 语音识别 WebSocket 接口地址
# bigmodel: 双向流式模式（需要1.0资源ID: volc.bigasr.sauc.duration）
# bigmodel_async: 双向流式优化版（支持2.0资源ID: volc.seedasr.sauc.duration）
# bigmodel_nostream: 流式输入模式，发完才返回
ASR_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"

# 音频录制参数（固定值，匹配模型要求）
AUDIO_FORMAT = 16  # 16-bit
AUDIO_CHANNELS = 1  # 单声道
AUDIO_RATE = 16000  # 16kHz 采样率
# 双向流式模式推荐单包 200ms（文档建议100-200ms，200ms性能最优）
AUDIO_CHUNK = 3200  # 200ms/帧 (16000 * 0.2 = 3200 samples)

# 静音检测配置
SILENCE_THRESHOLD = 1000  # 静音振幅阈值（低于此值视为静音，建议 500-1500）
SILENCE_TIMEOUT = 3.0  # 静音超时时间（秒），超过此时间自动结束录音
FINAL_WAIT_TIMEOUT = 3.0  # 发送最后一包后等待最终结果的超时时间（秒）


# ==================== Doubao-Seed-1.6 对话模型配置 ====================
# 对话模型接口地址
CHAT_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

# 模型名称（注意：使用短横线连接，带版本号）
CHAT_MODEL_NAME = "doubao-seed-1-6-251015"

# 模型参数
CHAT_MAX_TOKENS = 65535  # 最大生成 tokens 数
CHAT_TEMPERATURE = 0.7  # 随机性 (0-1)
CHAT_REASONING_EFFORT = "medium"  # 推理力度: low/medium/high


# ==================== 豆包语音合成配置 ====================
# 语音合成 WebSocket 接口地址（双向流式接口）
TTS_WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"

# 音色类型（speaker）
# 注意: 音色版本必须与资源 ID 匹配！
# 2.0 音色（带 _uranus_bigtts 后缀，需配合 seed-tts-2.0）:
#   - zh_female_vv_uranus_bigtts（Vivi 2.0，中英文）
#   - zh_female_xiaohe_uranus_bigtts（小何 2.0，中文）
#   - zh_male_m191_uranus_bigtts（云舟 2.0，中文）
#   - zh_male_taocheng_uranus_bigtts（小天 2.0，中文）
# 1.0 音色（带 _moon_bigtts/_mars_bigtts 后缀，需配合 seed-tts-1.0）
# 完整音色列表: https://www.volcengine.com/docs/6561/1257544
TTS_SPEAKER = "zh_female_xiaohe_uranus_bigtts"

# 音频输出格式（format）
TTS_FORMAT = "mp3"  # mp3 / ogg_opus / pcm

# 音频采样率
TTS_SAMPLE_RATE = 24000  # 可选: 8000,16000,22050,24000,32000,44100,48000

# 语速 (speech_rate) 取值范围[-50,100]，100代表2.0倍速，-50代表0.5倍速，0为默认
TTS_SPEECH_RATE = 0

# 音量 (loudness_rate) 取值范围[-50,100]，100代表2.0倍音量，-50代表0.5倍音量，0为默认
TTS_LOUDNESS_RATE = 0


# ==================== 界面配置 ====================
# 窗口标题
WINDOW_TITLE = "豆包语音助手 Demo"

# 窗口尺寸
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

# 临时音频文件保存路径
TEMP_AUDIO_PATH = os.path.join(os.path.dirname(__file__), "temp_audio.mp3")


# ==================== 网络配置 ====================
# 请求超时时间（秒）
REQUEST_TIMEOUT = 30

# 重试次数
MAX_RETRIES = 3
