#!/usr/bin/env python3
"""
列出所有可用的音频设备
"""
import pyaudio

def list_audio_devices():
    p = pyaudio.PyAudio()

    print("=" * 70)
    print("可用的音频设备列表")
    print("=" * 70)
    print()

    default_input = p.get_default_input_device_info()
    default_output = p.get_default_output_device_info()

    print(f"🎤 默认输入设备（麦克风）:")
    print(f"   索引: {default_input['index']}")
    print(f"   名称: {default_input['name']}")
    print(f"   声道数: {default_input['maxInputChannels']}")
    print(f"   采样率: {int(default_input['defaultSampleRate'])} Hz")
    print()

    print(f"🔊 默认输出设备（扬声器）:")
    print(f"   索引: {default_output['index']}")
    print(f"   名称: {default_output['name']}")
    print()

    print("=" * 70)
    print("所有设备详情")
    print("=" * 70)
    print()

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)

        # 设备类型
        device_type = []
        if info['maxInputChannels'] > 0:
            device_type.append("输入")
        if info['maxOutputChannels'] > 0:
            device_type.append("输出")
        type_str = "/".join(device_type)

        # 是否是默认设备
        is_default = ""
        if info['index'] == default_input['index']:
            is_default = " ⭐ 默认输入"
        elif info['index'] == default_output['index']:
            is_default = " ⭐ 默认输出"

        print(f"设备 [{i}] {type_str}{is_default}")
        print(f"  名称: {info['name']}")
        print(f"  输入声道: {info['maxInputChannels']}")
        print(f"  输出声道: {info['maxOutputChannels']}")
        print(f"  默认采样率: {int(info['defaultSampleRate'])} Hz")
        print()

    p.terminate()

    print("=" * 70)
    print("提示")
    print("=" * 70)
    print()
    print("realtime_mic_asr.py 当前使用的是:")
    print(f"  设备索引: {default_input['index']}")
    print(f"  设备名称: {default_input['name']}")
    print()
    print("如需使用其他设备，可以在代码中指定 input_device_index 参数")
    print()

if __name__ == "__main__":
    try:
        list_audio_devices()
    except Exception as e:
        print(f"错误: {e}")
        print("\n可能的原因:")
        print("  1. PyAudio 未正确安装")
        print("  2. 没有可用的音频设备")
        print("  3. 权限问题")
