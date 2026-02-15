# BCC950 Demo Applications

Demo applications showcasing the Logitech BCC950 camera control library integrated
with computer vision, speech recognition, text-to-speech, and conversational AI.

## Project Structure

```
demos/
  basic_embodied.py    - Simple see/hear/think/speak loop (~200 lines)
  embodied/            - (Legacy) Full AI — now lives in tritium-sc
  vision/
    motion_tracker.py  - Auto-tracks moving objects via background subtraction
    movement_verifier.py - Interactive PTZ + optical flow verification tool
    calibration.py     - ArUco marker-based pan/tilt calibration
  voice/
    voice_control.py   - Whisper-based natural language camera control
    narrator.py        - Narration of what the camera sees (Haar or Ollama)
    requirements.txt   - Voice demo dependencies
```

## Prerequisites

All demos require:

- Linux with v4l-utils installed
- Python 3.10+
- A connected Logitech BCC950 camera
- The `bcc950` Python package

The fastest way to set everything up:

```bash
./scripts/setup.sh
source .venv/bin/activate
```

## Basic Embodied AI Demo

A simple ~200-line demo showing BCC950 camera + YOLO person tracking + Whisper STT
+ Piper TTS in a see/hear/think/speak loop.

For the **full AI Commander** (sensorium, thinking thread, memory, autonomous behavior),
see [TRITIUM-SC](https://github.com/scubasonar/tritium-sc).

### Prerequisites

| Component | Purpose | Size |
|-----------|---------|------|
| Ollama + llava:7b | Vision + language understanding | ~5GB |
| Whisper large-v3 | Speech-to-text | ~3GB |
| Piper + Amy voice | Text-to-speech | ~50MB |
| OpenCV | Frame capture | ~50MB |
| sounddevice | Audio I/O | ~1MB |
| ultralytics | YOLO person tracking | ~50MB |

### Run

```bash
# Full demo
python demos/basic_embodied.py

# Lightweight (smaller models, no TTS, no tracking)
python demos/basic_embodied.py --model gemma3:4b --whisper-model base --no-tts --no-tracking
```

### How It Works

1. **See** - Captures frame from BCC950 camera
2. **Track** - YOLO detects people, auto-pans/tilts to follow
3. **Listen** - Records 4 seconds of audio from BCC950 mic
4. **Think** - Sends transcript + frame to Ollama (llava:7b)
5. **Speak** - Piper TTS reads response aloud
6. **Loop** - Back to step 1

## Vision Demos

### Dependencies

```bash
pip install opencv-python opencv-contrib-python numpy
```

### Motion Tracker

Detects the largest moving object using background subtraction and automatically
pans/tilts the camera to follow it.

```bash
python demos/vision/motion_tracker.py
python demos/vision/motion_tracker.py --dead-zone 0.15 --move-duration 0.08
```

Controls: `q` quit, `r` reset

### Movement Verifier

Interactive tool for testing PTZ with real-time optical flow verification.

```bash
python demos/vision/movement_verifier.py
```

Controls: `a/d` pan, `w/s` tilt, `+/-` zoom, `r` reset, `q` quit

### Calibration

ArUco marker-based pan/tilt calibration.

```bash
python demos/vision/calibration.py
python demos/vision/calibration.py --output my_calibration.json
```

## Voice Demos

### Voice Control

Listens to microphone input, transcribes speech with Whisper, and parses natural
language commands to control the camera.

```bash
python demos/voice/voice_control.py
python demos/voice/voice_control.py --whisper-model large-v3
```

Supported commands: "look left", "pan right for 2 seconds", "zoom to 300", "reset", "quit"

### Narrator

Describes what the camera sees, either using Haar cascades or an Ollama vision model.

```bash
# AI narration via Ollama
python demos/voice/narrator.py --use-ollama
python demos/voice/narrator.py --use-ollama --model gemma3:4b

# Classic Haar cascade mode (no AI)
python demos/voice/narrator.py

# With video overlay
python demos/voice/narrator.py --show
```
