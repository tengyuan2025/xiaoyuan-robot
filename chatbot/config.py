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
SILENCE_TIMEOUT = 1.5  # 静音超时时间（秒），超过此时间自动结束录音
FINAL_WAIT_TIMEOUT = 1.5  # 发送最后一包后等待最终结果的超时时间（秒）


# ==================== Doubao-Seed-1.6 对话模型配置 ====================
# 对话模型接口地址
CHAT_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

# 模型名称（注意：使用短横线连接，带版本号）
CHAT_MODEL_NAME = "doubao-seed-1-6-251015"

# 模型参数
CHAT_MAX_TOKENS = 256  # 最大生成 tokens 数（限制长度提速）
CHAT_TEMPERATURE = 0.2  # 随机性 (0-1)，降低以加速生成
CHAT_STREAM = True  # 开启流式返回（关键优化项）
CHAT_THINKING = "disabled"  # 关闭深度思考模式，直接返回结果（提速核心）


# ==================== Base64图文分析配置 ====================
# 图文分析使用同一个模型（Doubao-Seed-1.6），通过Base64编码+提示词实现
# 图文分析时使用非流式调用（需要完整上下文，流式会降低精度）
IMAGE_ANALYSIS_STREAM = False

# 图文分析模型参数（比普通对话需要更多tokens）
IMAGE_ANALYSIS_MAX_TOKENS = 1024
IMAGE_ANALYSIS_TEMPERATURE = 0.2

# 图片压缩配置（避免Base64过长导致超时）
IMAGE_MAX_WIDTH = 1920   # 最大宽度
IMAGE_MAX_HEIGHT = 1080  # 最大高度
IMAGE_QUALITY = 85       # JPEG压缩质量 (1-100)

# 临时图片保存路径
TEMP_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "temp_capture.jpg")

# Base64图文分析提示词模板
IMAGE_ANALYSIS_PROMPT_TEMPLATE = """请严格按照以下步骤执行：
1. 解码我提供的Base64字符串（格式为data:image/jpeg;base64,xxx），还原为JPEG图片；
2. 分析图片内容（物体、场景、颜色等关键信息）；
3. 结合我的问题「{user_question}」，给出简洁清晰的回答；
4. 仅回复最终答案，不要提及Base64、解码等过程性内容。

图片Base64编码：
{image_base64}"""


# ==================== 人脸识别配置 ====================
# 人脸编码存储路径
FACE_ENCODINGS_PATH = os.path.join(os.path.dirname(__file__), "faces", "encodings.json")

# 人脸匹配容差（越小越严格，建议0.4-0.6）
# 0.6: 默认值，适合一般场景
# 0.5: 更严格，减少误识别
# 0.4: 非常严格，可能增加漏识别
FACE_RECOGNITION_TOLERANCE = 0.6

# 人脸检测模型
# "hog": 快速，CPU友好，适合实时检测
# "cnn": 更准确，需要GPU支持，速度较慢
FACE_RECOGNITION_MODEL = "hog"

# 人脸识别结果融合到对话的提示词模板
# {face_names}: 识别到的人名列表
# {user_question}: 用户原始问题
# {image_base64}: 图片Base64编码
FACE_RECOGNITION_PROMPT_TEMPLATE = """我拍摄了一张照片，{face_info}。

请根据照片内容回答用户的问题：「{user_question}」

要求：
1. 回答要简洁清晰
2. 如果识别出了人名，在回答中自然地提到
3. 不要提及Base64或技术细节

图片Base64编码：
{image_base64}"""


# ==================== 声纹识别配置 ====================
# 声纹数据存储路径
VOICEPRINT_DATA_PATH = os.path.join(os.path.dirname(__file__), "voiceprints.json")

# 声纹匹配相似度阈值（余弦相似度，0-1，越高越严格）
# 0.80: 非常严格，可能漏识别
# 0.75: 推荐值，平衡准确率和召回率
# 0.70: 较宽松，可能误识别
SPEAKER_SIMILARITY_THRESHOLD = 0.75

# 最小有效音频时长（秒），低于此时长不提取声纹
SPEAKER_MIN_AUDIO_DURATION = 1.0


# ==================== YOLO 物体检测配置 ====================
# YOLO 模型选择
# yolov8n.pt: 最快，精度较低（推荐，首次运行自动下载约 6MB）
# yolov8s.pt: 快速，精度适中（约 22MB）
# yolov8m.pt: 中等速度，精度较高（约 52MB）
YOLO_MODEL_NAME = "yolov8n.pt"

# 检测置信度阈值（越高越严格）
YOLO_CONFIDENCE_THRESHOLD = 0.5

# 是否使用中文类别名称
YOLO_USE_CHINESE = True


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
