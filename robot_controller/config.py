# -*- coding: utf-8 -*-
"""
嵌入式机器人配置文件
适用于 RK3568 平台
"""

# ============================================================
# 硬件配置
# ============================================================

# 音频设备配置（基于硬件测试结果）
AUDIO_CONFIG = {
    # USB 声卡（录音和播放）
    "device": "plughw:2,0",
    "sample_rate": 16000,
    "channels": 1,
    "bit_depth": 16,
    "chunk_size": 3200,  # 200ms @ 16kHz
}

# 降噪板串口配置
NOISE_REDUCTION_BOARD = {
    "port": "/dev/ttyUSB0",
    "baudrate": 115200,
}

# 摄像头配置
CAMERA_CONFIG = {
    "usb_camera": {
        "device": "/dev/video9",
        "width": 640,
        "height": 480,
    },
    "depth_camera": {
        "enabled": True,
        "sdk_path": "~/deptrum-sdk-linux-aarch64-v2.0.219",
    },
}

# 雷达配置
LIDAR_CONFIG = {
    "port": "/dev/ttyUSB1",
    "baudrate": 460800,
    "model": "RPLIDAR_C1",
}

# 舵机配置
SERVO_CONFIG = {
    "head": {
        "pan_channel": 0,   # 左右转动
        "tilt_channel": 1,  # 上下点头
    },
    "left_arm": {
        "channel": 2,
    },
    "right_arm": {
        "channel": 3,
    },
}

# LCD 显示配置
LCD_CONFIG = {
    "enabled": True,
    "width": 480,
    "height": 480,
    "interface": "mipi",
}


# ============================================================
# API 配置（火山引擎豆包服务）
# ============================================================

# 语音识别 (ASR)
ASR_CONFIG = {
    "ws_url": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
    "resource_id": "volc.seedasr.sauc.duration",  # 2.0版本
    "enable_itn": True,      # 数字转换
    "enable_punc": True,     # 自动标点
    "enable_ddc": True,      # 语音活动检测
    "show_utterances": True, # 显示句子级结果
}

# 对话模型 (Chat)
CHAT_CONFIG = {
    "api_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "model_name": "doubao-seed-1-6-251015",
    "max_tokens": 4096,
    "temperature": 0.7,
    "stream": True,
}

# 语音合成 (TTS)
TTS_CONFIG = {
    "ws_url": "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
    "resource_id": "seed-tts-2.0",
    "speaker": "zh_female_xiaohe_uranus_bigtts",  # 小何2.0音色
    "audio_format": "mp3",
    "sample_rate": 24000,
}

# 记忆服务 (Mem0)
MEM0_CONFIG = {
    "base_url": "http://tenyuan.tech:9000",
    "enabled": True,
}


# ============================================================
# 语音唤醒配置
# ============================================================

WAKE_WORD_CONFIG = {
    "enabled": True,
    "engine": "porcupine",  # 可选: porcupine, snowboy, custom
    "keywords": ["小元", "你好小元"],
    "sensitivity": 0.5,
    # 备用方案：基于静音检测的按键唤醒
    "fallback_button": True,
}


# ============================================================
# 系统配置
# ============================================================

SYSTEM_CONFIG = {
    # 日志配置
    "log_level": "INFO",
    "log_file": "/var/log/robot/robot.log",

    # 静音检测
    "silence_threshold": 500,       # 静音阈值
    "silence_duration": 1.5,        # 静音持续时间（秒）
    "max_record_duration": 30,      # 最大录音时长（秒）

    # 性能配置
    "enable_face_recognition": True,
    "enable_object_detection": True,
    "enable_speaker_recognition": True,

    # 机器人性格配置
    "personality": {
        "name": "小元",
        "style": "活泼",  # 活泼/稳重/幽默
        "emoji": False,
    },
}


# ============================================================
# 系统提示词
# ============================================================

SYSTEM_PROMPT = """你是一个名叫{name}的陪伴机器人，性格{style}。

## 你的能力
- 与用户进行自然对话
- 回答各种问题
- 记住用户的喜好和信息
- 识别用户的身份（通过声音和面容）
- 看到周围的环境（通过摄像头）

## 对话风格
- 简洁友好，每次回复控制在2-3句话
- 适当使用语气词，让对话更自然
- 根据用户情绪调整回应方式
- 记住之前的对话内容

## 注意事项
- 不要使用emoji表情
- 回复要口语化，适合语音播放
- 如果不确定，诚实地说不知道
""".format(
    name=SYSTEM_CONFIG["personality"]["name"],
    style=SYSTEM_CONFIG["personality"]["style"],
)
