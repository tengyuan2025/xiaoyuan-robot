#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块测试脚本
用于验证各个模块是否正常工作
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_imports():
    """测试模块导入"""
    print("\n=== 测试模块导入 ===\n")

    modules = [
        ("config", "配置模块"),
        ("utils.logger", "日志模块"),
        ("core.state_machine", "状态机"),
        ("core.audio_recorder", "音频录制"),
        ("core.audio_player", "音频播放"),
        ("core.wake_word", "语音唤醒"),
        ("ai.asr_client", "ASR 客户端"),
        ("ai.chat_client", "Chat 客户端"),
        ("ai.tts_client", "TTS 客户端"),
        ("ai.mem0_client", "Mem0 客户端"),
    ]

    success = 0
    failed = 0

    for module, name in modules:
        try:
            __import__(module)
            print(f"  [OK] {name} ({module})")
            success += 1
        except ImportError as e:
            print(f"  [FAIL] {name} ({module}): {e}")
            failed += 1

    print(f"\n导入测试: {success} 成功, {failed} 失败")
    return failed == 0


def test_config():
    """测试配置加载"""
    print("\n=== 测试配置加载 ===\n")

    try:
        from config import (
            AUDIO_CONFIG,
            ASR_CONFIG,
            CHAT_CONFIG,
            TTS_CONFIG,
            SYSTEM_CONFIG
        )

        print(f"  音频设备: {AUDIO_CONFIG['device']}")
        print(f"  采样率: {AUDIO_CONFIG['sample_rate']} Hz")
        print(f"  ASR 资源: {ASR_CONFIG['resource_id']}")
        print(f"  Chat 模型: {CHAT_CONFIG['model_name']}")
        print(f"  TTS 音色: {TTS_CONFIG['speaker']}")
        print(f"  日志级别: {SYSTEM_CONFIG['log_level']}")
        print("\n  [OK] 配置加载成功")
        return True
    except Exception as e:
        print(f"\n  [FAIL] 配置加载失败: {e}")
        return False


def test_api_secrets():
    """测试 API 密钥配置"""
    print("\n=== 测试 API 密钥 ===\n")

    try:
        from api_secrets import (
            ASR_APPID,
            ASR_ACCESS_TOKEN,
            CHAT_API_KEY,
            TTS_APPID,
            TTS_ACCESS_TOKEN
        )

        secrets = {
            "ASR_APPID": ASR_APPID,
            "ASR_ACCESS_TOKEN": ASR_ACCESS_TOKEN,
            "CHAT_API_KEY": CHAT_API_KEY,
            "TTS_APPID": TTS_APPID,
            "TTS_ACCESS_TOKEN": TTS_ACCESS_TOKEN,
        }

        all_set = True
        for key, value in secrets.items():
            if value and not value.startswith("your_"):
                print(f"  [OK] {key}: 已配置")
            else:
                print(f"  [WARN] {key}: 未配置")
                all_set = False

        return all_set
    except ImportError:
        print("  [WARN] api_secrets.py 未找到")
        print("  请复制 api_secrets.example.py 为 api_secrets.py")
        return False


async def test_audio_recorder():
    """测试音频录制"""
    print("\n=== 测试音频录制 ===\n")

    try:
        from core.audio_recorder import AudioRecorder, AudioConfig
        from config import AUDIO_CONFIG

        recorder = AudioRecorder(AudioConfig(
            device=AUDIO_CONFIG["device"],
            sample_rate=AUDIO_CONFIG["sample_rate"]
        ))

        print(f"  设备: {AUDIO_CONFIG['device']}")
        print("  启动录音 (3秒)...")

        if await recorder.start():
            audio_data = b""
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < 3:
                chunk = await recorder.read_chunk()
                if chunk:
                    audio_data += chunk

            await recorder.stop()

            print(f"  录制数据: {len(audio_data)} bytes")
            print(f"  时长: {recorder.get_duration():.1f} 秒")
            print("\n  [OK] 音频录制测试通过")
            return True
        else:
            print("\n  [FAIL] 录音启动失败")
            return False

    except Exception as e:
        print(f"\n  [FAIL] 音频录制测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_audio_player():
    """测试音频播放"""
    print("\n=== 测试音频播放 ===\n")

    try:
        from core.audio_player import AudioPlayer, PlaybackConfig
        from config import AUDIO_CONFIG

        player = AudioPlayer(PlaybackConfig(
            device=AUDIO_CONFIG["device"]
        ))

        # 生成测试音频 (1kHz 正弦波, 1秒)
        import struct
        import math

        sample_rate = 16000
        duration = 1.0
        frequency = 1000

        samples = []
        for i in range(int(sample_rate * duration)):
            t = i / sample_rate
            value = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * t))
            samples.append(struct.pack('<h', value))

        test_audio = b''.join(samples)

        print(f"  设备: {AUDIO_CONFIG['device']}")
        print(f"  测试音频: {frequency}Hz 正弦波, {duration}秒")
        print("  播放中...")

        result = await player.play_pcm(test_audio, sample_rate)

        if result:
            print("\n  [OK] 音频播放测试通过")
            return True
        else:
            print("\n  [FAIL] 音频播放失败")
            return False

    except Exception as e:
        print(f"\n  [FAIL] 音频播放测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_mem0():
    """测试 Mem0 连接"""
    print("\n=== 测试 Mem0 服务 ===\n")

    try:
        from ai.mem0_client import Mem0Client, Mem0Config
        from config import MEM0_CONFIG

        client = Mem0Client(Mem0Config(
            base_url=MEM0_CONFIG["base_url"],
            enabled=MEM0_CONFIG["enabled"]
        ))

        print(f"  服务地址: {MEM0_CONFIG['base_url']}")
        print("  检查连接...")

        if client.health_check():
            print("\n  [OK] Mem0 服务连接正常")
            return True
        else:
            print("\n  [WARN] Mem0 服务不可用")
            return False

    except Exception as e:
        print(f"\n  [WARN] Mem0 测试失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 50)
    print("  嵌入式机器人模块测试")
    print("=" * 50)

    results = []

    # 同步测试
    results.append(("模块导入", test_imports()))
    results.append(("配置加载", test_config()))
    results.append(("API 密钥", test_api_secrets()))

    # 异步测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        results.append(("音频录制", loop.run_until_complete(test_audio_recorder())))
        results.append(("音频播放", loop.run_until_complete(test_audio_player())))
        results.append(("Mem0 服务", loop.run_until_complete(test_mem0())))
    finally:
        loop.close()

    # 汇总结果
    print("\n" + "=" * 50)
    print("  测试结果汇总")
    print("=" * 50 + "\n")

    passed = 0
    failed = 0
    warned = 0

    for name, result in results:
        if result is True:
            status = "[PASS]"
            passed += 1
        elif result is False:
            status = "[FAIL]"
            failed += 1
        else:
            status = "[WARN]"
            warned += 1
        print(f"  {status} {name}")

    print(f"\n总计: {passed} 通过, {failed} 失败, {warned} 警告")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
