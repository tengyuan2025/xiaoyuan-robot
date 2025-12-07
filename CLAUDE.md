# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Chinese speech recognition project (xiaoyuan-robot) that integrates with ByteDance's Doubao (豆包) ASR (Automatic Speech Recognition) service. The project focuses on real-time microphone audio recognition using WebSocket streaming.

## Core Components

### 1. Real-time Microphone ASR (`realtime_mic_asr.py`)
The main application that captures live microphone input and streams it to the Doubao ASR service for real-time speech recognition.

**Key classes:**
- `AsrRequestHeader`: Constructs binary protocol headers for WebSocket messages
- `RequestBuilder`: Creates authentication headers and protocol-compliant requests
- `ResponseParser`: Parses binary responses from the ASR service
- `MicrophoneRecorder`: Manages PyAudio recording with async queue-based streaming
- `RealtimeMicASRClient`: Main orchestrator that coordinates connection, recording, and recognition

**Audio configuration:**
- Sample rate: 16000 Hz
- Channels: 1 (mono)
- Bit depth: 16 bit
- Format: PCM
- Segment duration: 200ms chunks

### 2. File-based ASR Demo (`sauc_python/sauc_websocket_demo.py`)
Reference implementation for processing pre-recorded audio files. Contains similar protocol handling logic but uses file input instead of microphone.

## API Configuration

The project uses ByteDance Doubao ASR API with credentials embedded in code:
- WebSocket endpoint: `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel`
- Credentials are hardcoded in `realtime_mic_asr.py` (lines 36-38)
- Demo template with placeholder keys in `sauc_python/sauc_websocket_demo.py` (lines 53-54)

## Binary Protocol Details

The codebase implements a custom binary protocol for WebSocket communication:

**Protocol structure:**
- Version: V1 (0b0001)
- Message types: CLIENT_FULL_REQUEST (initial), CLIENT_AUDIO_ONLY_REQUEST (streaming)
- Serialization: JSON with GZIP compression
- Sequence numbers: Positive for ongoing, negative for final packet

**Message flow:**
1. Send full client request with audio config and recognition parameters
2. Stream audio segments with sequence numbers
3. Receive both temporary and final recognition results
4. Send final packet with negative sequence number to signal end

## Development Commands

### Setup
```bash
# Install dependencies
pip install pyaudio aiohttp

# macOS: Install PortAudio first
brew install portaudio
pip install pyaudio

# Linux: Install PortAudio dev packages
sudo apt-get install portaudio19-dev python3-pyaudio
pip install pyaudio
```

### Running the Application
```bash
# Real-time microphone recognition
python realtime_mic_asr.py

# File-based recognition (demo)
python3 sauc_python/sauc_websocket_demo.py --file /path/to/audio.wav
```

### Stopping
- Press `Ctrl+C` to gracefully stop recording and exit

## Architecture Notes

**Async design:**
- Uses `asyncio` for concurrent audio capture and WebSocket communication
- Separate coroutines for sending (audio streaming) and receiving (recognition results)
- PyAudio callback puts audio chunks into a queue for async processing

**Audio handling:**
- PyAudio streams are managed with callbacks to avoid blocking
- Audio buffer accumulates chunks until segment size (200ms) is reached
- Segments are GZIP-compressed before transmission

**Recognition features enabled:**
- `enable_itn`: Number conversion (e.g., "一千二百三十四" → "1234")
- `enable_punc`: Automatic punctuation insertion
- `enable_ddc`: Voice activity detection (endpoint detection)
- `show_utterances`: Display sentence-level results
- `enable_nonstream`: False (streaming mode enabled)

## Key Considerations

**Signal handling:**
- SIGINT and SIGTERM handlers ensure clean shutdown
- Microphone resources are properly released via context managers

**Audio format requirements:**
- WAV files must be: 16kHz, mono, 16-bit PCM
- `sauc_websocket_demo.py` includes FFmpeg conversion for non-compliant audio

**Error handling:**
- Response parser handles malformed/incomplete packets
- GZIP decompression failures are logged but don't crash the client
- WebSocket errors trigger clean shutdown of both send/receive tasks
