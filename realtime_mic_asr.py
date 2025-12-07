#!/usr/bin/env python3
"""
实时麦克风语音识别脚本
将麦克风音频实时发送给豆包流式语音识别服务并打印识别结果
"""

import asyncio
import aiohttp
import json
import struct
import gzip
import uuid
import logging
import pyaudio
import signal
import sys
from typing import Optional, Dict, Any, AsyncGenerator
from queue import Queue
import threading

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 音频配置常量
SAMPLE_RATE = 16000
CHANNELS = 1
BITS_PER_SAMPLE = 16
CHUNK_SIZE = 3200  # 每次读取的音频块大小
SEGMENT_DURATION_MS = 200  # 每个音频段的时长（毫秒）

# 豆包API配置（豆包流式语音识别模型2.0）
APP_ID = "3384355451"
ACCESS_KEY = "k3v2aKBdU1xuUfq4yeiM28QCcTv2R97j"
WSS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"

# 协议相关常量
class ProtocolVersion:
    V1 = 0b0001

class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111

class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011

class SerializationType:
    JSON = 0b0001

class CompressionType:
    GZIP = 0b0001


class AsrRequestHeader:
    """ASR请求头构造器"""

    def __init__(self):
        self.message_type = MessageType.CLIENT_FULL_REQUEST
        self.message_type_specific_flags = MessageTypeSpecificFlags.POS_SEQUENCE
        self.serialization_type = SerializationType.JSON
        self.compression_type = CompressionType.GZIP
        self.reserved_data = bytes([0x00])

    def with_message_type(self, message_type: int) -> 'AsrRequestHeader':
        self.message_type = message_type
        return self

    def with_message_type_specific_flags(self, flags: int) -> 'AsrRequestHeader':
        self.message_type_specific_flags = flags
        return self

    def to_bytes(self) -> bytes:
        header = bytearray()
        header.append((ProtocolVersion.V1 << 4) | 1)
        header.append((self.message_type << 4) | self.message_type_specific_flags)
        header.append((self.serialization_type << 4) | self.compression_type)
        header.extend(self.reserved_data)
        return bytes(header)


class RequestBuilder:
    """请求构造器"""

    @staticmethod
    def new_auth_headers() -> Dict[str, str]:
        """创建认证请求头"""
        reqid = str(uuid.uuid4())
        return {
            "X-Api-Resource-Id": "volc.seedasr.sauc.duration",  # 尝试模型1.0
            "X-Api-Request-Id": reqid,
            "X-Api-Access-Key": ACCESS_KEY,
            "X-Api-App-Key": APP_ID,
            "X-Api-Connect-Id": reqid
        }

    @staticmethod
    def new_full_client_request(seq: int) -> bytes:
        """创建完整的客户端请求（第一个包）"""
        header = AsrRequestHeader() \
            .with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)

        payload = {
            "user": {
                "uid": "realtime_mic_user"
            },
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": SAMPLE_RATE,
                "bits": BITS_PER_SAMPLE,
                "channel": CHANNELS
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "enable_nonstream": False
            }
        }

        payload_bytes = json.dumps(payload).encode('utf-8')
        compressed_payload = gzip.compress(payload_bytes)
        payload_size = len(compressed_payload)

        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))
        request.extend(struct.pack('>I', payload_size))
        request.extend(compressed_payload)

        return bytes(request)

    @staticmethod
    def new_audio_only_request(seq: int, segment: bytes, is_last: bool = False) -> bytes:
        """创建纯音频数据请求"""
        header = AsrRequestHeader()
        if is_last:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.NEG_WITH_SEQUENCE)
            seq = -seq
        else:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)
        header.with_message_type(MessageType.CLIENT_AUDIO_ONLY_REQUEST)

        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))

        compressed_segment = gzip.compress(segment)
        request.extend(struct.pack('>I', len(compressed_segment)))
        request.extend(compressed_segment)

        return bytes(request)


class AsrResponse:
    """ASR响应对象"""

    def __init__(self):
        self.code = 0
        self.event = 0
        self.is_last_package = False
        self.payload_sequence = 0
        self.payload_size = 0
        self.payload_msg = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "event": self.event,
            "is_last_package": self.is_last_package,
            "payload_sequence": self.payload_sequence,
            "payload_size": self.payload_size,
            "payload_msg": self.payload_msg
        }


class ResponseParser:
    """响应解析器"""

    @staticmethod
    def parse_response(msg: bytes) -> AsrResponse:
        """解析服务端响应"""
        response = AsrResponse()

        header_size = msg[0] & 0x0f
        message_type = msg[1] >> 4
        message_type_specific_flags = msg[1] & 0x0f
        serialization_method = msg[2] >> 4
        message_compression = msg[2] & 0x0f

        payload = msg[header_size*4:]

        # 解析flags
        if message_type_specific_flags & 0x01:
            response.payload_sequence = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]
        if message_type_specific_flags & 0x02:
            response.is_last_package = True
        if message_type_specific_flags & 0x04:
            response.event = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]

        # 解析message_type
        if message_type == MessageType.SERVER_FULL_RESPONSE:
            response.payload_size = struct.unpack('>I', payload[:4])[0]
            payload = payload[4:]
        elif message_type == MessageType.SERVER_ERROR_RESPONSE:
            response.code = struct.unpack('>i', payload[:4])[0]
            response.payload_size = struct.unpack('>I', payload[4:8])[0]
            payload = payload[8:]

        if not payload:
            return response

        # 解压缩
        if message_compression == CompressionType.GZIP:
            try:
                payload = gzip.decompress(payload)
            except Exception as e:
                logger.error(f"解压缩失败: {e}")
                return response

        # 解析payload
        try:
            if serialization_method == SerializationType.JSON:
                response.payload_msg = json.loads(payload.decode('utf-8'))
        except Exception as e:
            logger.error(f"解析payload失败: {e}")

        return response


class MicrophoneRecorder:
    """麦克风录音器"""

    def __init__(self, device_index=None):
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.is_recording = False
        self.audio_queue = Queue()
        self.device_index = device_index

    def start_recording(self):
        """开始录音"""
        try:
            # 获取设备信息
            if self.device_index is not None:
                device_info = self.audio.get_device_info_by_index(self.device_index)
                device_name = device_info['name']
                logger.info(f"使用音频设备: [{self.device_index}] {device_name}")
            else:
                device_name = "默认设备"
                logger.info(f"使用音频设备: {device_name}")

            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=CHUNK_SIZE,
                stream_callback=self._audio_callback
            )
            self.is_recording = True
            self.stream.start_stream()
            logger.info(f"开始录音 - 采样率: {SAMPLE_RATE}Hz, 声道: {CHANNELS}, 位深: {BITS_PER_SAMPLE}bit")
        except Exception as e:
            logger.error(f"启动麦克风失败: {e}")
            raise

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """音频回调函数"""
        if status:
            logger.warning(f"音频状态: {status}")
        self.audio_queue.put(in_data)
        return (None, pyaudio.paContinue)

    def get_audio_chunk(self) -> Optional[bytes]:
        """获取音频块（非阻塞）"""
        if not self.audio_queue.empty():
            return self.audio_queue.get()
        return None

    def stop_recording(self):
        """停止录音"""
        if self.stream:
            self.is_recording = False
            self.stream.stop_stream()
            self.stream.close()
            logger.info("停止录音")

    def cleanup(self):
        """清理资源"""
        self.stop_recording()
        if self.audio:
            self.audio.terminate()


class RealtimeMicASRClient:
    """实时麦克风ASR客户端"""

    def __init__(self, device_index=0):
        self.seq = 1
        self.conn = None
        self.session = None
        self.recorder = MicrophoneRecorder(device_index=device_index)
        self.is_running = False

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.conn and not self.conn.closed:
            await self.conn.close()
        if self.session and not self.session.closed:
            await self.session.close()
        self.recorder.cleanup()

    async def create_connection(self) -> None:
        """创建WebSocket连接"""
        headers = RequestBuilder.new_auth_headers()
        logger.info("=== 发送建连请求 ===")
        logger.info(f"URL: {WSS_URL}")
        logger.info(f"请求头: {json.dumps(headers, indent=2, ensure_ascii=False)}")
        try:
            self.conn = await self.session.ws_connect(WSS_URL, headers=headers)
            logger.info(f"✓ 已成功连接到 {WSS_URL}")
        except Exception as e:
            logger.error(f"✗ WebSocket连接失败: {e}")
            logger.error(f"请检查：1) 控制台服务是否已开通 2) 密钥是否正确 3) Resource-Id是否匹配")
            raise

    async def send_full_client_request(self) -> None:
        """发送完整客户端请求（第一个包）"""
        request = RequestBuilder.new_full_client_request(self.seq)
        try:
            await self.conn.send_bytes(request)
            logger.info(f"已发送完整客户端请求 (seq: {self.seq})")
            self.seq += 1

            # 等待服务端响应
            msg = await self.conn.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                response = ResponseParser.parse_response(msg.data)
                if response.code != 0:
                    logger.error(f"服务端返回错误: {response.to_dict()}")
                    raise RuntimeError(f"服务端错误: {response.code}")
                logger.info("服务端确认连接成功")
            else:
                logger.error(f"意外的消息类型: {msg.type}")
                raise RuntimeError(f"意外的消息类型: {msg.type}")
        except Exception as e:
            logger.error(f"发送完整客户端请求失败: {e}")
            raise

    async def send_audio_stream(self):
        """发送音频流"""
        # 计算每个音频段的大小
        segment_size = SAMPLE_RATE * CHANNELS * (BITS_PER_SAMPLE // 8) * SEGMENT_DURATION_MS // 1000
        audio_buffer = bytearray()

        logger.info("开始发送音频流...")

        try:
            while self.is_running:
                # 从队列获取音频数据
                chunk = self.recorder.get_audio_chunk()
                if chunk:
                    audio_buffer.extend(chunk)

                # 当缓冲区达到一个段的大小时发送
                while len(audio_buffer) >= segment_size:
                    segment = bytes(audio_buffer[:segment_size])
                    audio_buffer = audio_buffer[segment_size:]

                    request = RequestBuilder.new_audio_only_request(self.seq, segment, is_last=False)
                    await self.conn.send_bytes(request)
                    logger.debug(f"已发送音频段 (seq: {self.seq}, size: {len(segment)})")
                    self.seq += 1

                await asyncio.sleep(0.01)  # 短暂延迟避免CPU占用过高

        except Exception as e:
            logger.error(f"发送音频流出错: {e}")
            raise

    async def receive_responses(self):
        """接收并处理服务端响应"""
        logger.info("开始接收识别结果...")

        try:
            async for msg in self.conn:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    response = ResponseParser.parse_response(msg.data)

                    # 打印识别结果
                    if response.payload_msg:
                        result = response.payload_msg

                        # 提取识别文本
                        if "result" in result:
                            text = result.get("result", "")
                            is_final = result.get("is_final", False)

                            if text:
                                status = "[最终]" if is_final else "[临时]"
                                print(f"\n{status} 识别结果: {text}")

                        # 显示详细信息（可选）
                        if logger.level <= logging.DEBUG:
                            logger.debug(f"完整响应: {json.dumps(result, ensure_ascii=False, indent=2)}")

                    # 检查错误
                    if response.code != 0:
                        logger.error(f"服务端错误: code={response.code}, msg={response.payload_msg}")

                    # 检查是否是最后一个包
                    if response.is_last_package:
                        logger.info("收到最后一个响应包")
                        break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket错误: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket连接已关闭")
                    break

        except Exception as e:
            logger.error(f"接收响应出错: {e}")
            raise

    async def run(self):
        """运行实时识别"""
        try:
            # 1. 创建WebSocket连接
            await self.create_connection()

            # 2. 发送完整客户端请求
            await self.send_full_client_request()

            # 3. 启动麦克风录音
            self.recorder.start_recording()
            self.is_running = True

            # 4. 并发执行发送和接收任务
            send_task = asyncio.create_task(self.send_audio_stream())
            recv_task = asyncio.create_task(self.receive_responses())

            # 等待任何一个任务完成
            done, pending = await asyncio.wait(
                [send_task, recv_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"运行出错: {e}")
            raise
        finally:
            self.is_running = False
            self.recorder.stop_recording()

    def stop(self):
        """停止客户端"""
        logger.info("正在停止客户端...")
        self.is_running = False


# 全局客户端实例
client_instance = None


def signal_handler(sig, frame):
    """处理中断信号"""
    print("\n\n正在停止录音...")
    if client_instance:
        client_instance.stop()
    sys.exit(0)


def find_audio_device_by_name(device_name_keyword):
    """通过设备名称关键字查找音频设备"""
    p = pyaudio.PyAudio()
    device_index = None
    device_info = None

    # 遍历所有设备
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        # 检查是否是输入设备，且名称匹配
        if info['maxInputChannels'] > 0 and device_name_keyword.lower() in info['name'].lower():
            device_index = i
            device_info = info
            break

    p.terminate()
    return device_index, device_info


async def main():
    """主函数"""
    global client_instance

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 查找 USB Audio Device
    required_device_name = "USB Audio Device"  # 必须使用的设备名称
    device_index, device_info = find_audio_device_by_name(required_device_name)

    if device_index is None:
        print("=" * 60)
        print("❌ 错误：未找到 USB 外置麦克风")
        print("=" * 60)
        print(f"\n无法找到设备: {required_device_name}")
        print("\n请确保：")
        print("  1. USB 麦克风已正确连接到电脑")
        print("  2. 系统已识别该设备")
        print("  3. 设备名称包含 'USB Audio Device'")
        print("\n运行以下命令查看所有可用设备：")
        print("  python3 list_audio_devices.py")
        print("\n" + "=" * 60)
        sys.exit(1)

    device_name = device_info['name']

    print("=" * 60)
    print("实时麦克风语音识别")
    print("=" * 60)
    print(f"配置信息:")
    print(f"  - 音频设备: [{device_index}] {device_name}")
    print(f"  - 采样率: {SAMPLE_RATE}Hz")
    print(f"  - 声道数: {CHANNELS}")
    print(f"  - 位深: {BITS_PER_SAMPLE}bit")
    print(f"  - 服务: {WSS_URL}")
    print("=" * 60)
    print("\n✓ 已锁定 USB 外置麦克风")
    print("请对着麦克风说话，按 Ctrl+C 停止...\n")

    async with RealtimeMicASRClient(device_index=device_index) as client:
        client_instance = client
        try:
            await client.run()
        except KeyboardInterrupt:
            logger.info("用户中断")
        except Exception as e:
            logger.error(f"程序异常: {e}")
        finally:
            print("\n程序结束")


if __name__ == "__main__":
    # 检查PyAudio是否可用
    try:
        import pyaudio
    except ImportError:
        print("错误: 未安装 pyaudio 库")
        print("请运行: pip install pyaudio")
        sys.exit(1)

    asyncio.run(main())
