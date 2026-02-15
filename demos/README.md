# BCC950 Demo Applications

Demo applications showcasing the Logitech BCC950 camera control library integrated
with computer vision, speech recognition, text-to-speech, and conversational AI.

## Project Structure

```
demos/
  embodied/
    conversation.py    - Full embodied AI: see, hear, speak, move
    listener.py        - Whisper STT audio recording
    speaker.py         - Piper TTS with queued playback
    vision.py          - OpenCV frame capture + Ollama vision
    agent.py           - Ollama agent with tool use
    tools.py           - Tool dispatch to BCC950Controller
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

## Embodied AI Demo (Amy)

**Amy is an AI embodied in the BCC950 camera.** She sees through the camera, hears
via the microphone, speaks with Piper TTS, and moves the camera using PTZ controls.

### Prerequisites

| Component | Purpose | Size |
|-----------|---------|------|
| Ollama + qwen3-vl:32b | Vision + language understanding | 21GB |
| Whisper large-v3 | Speech-to-text | ~3GB |
| Piper + Amy voice | Text-to-speech | ~50MB |
| OpenCV | Frame capture | ~50MB |
| sounddevice | Audio I/O | ~1MB |

### Run

```bash
# Full demo
python demos/embodied/conversation.py

# Lightweight (smaller models, no TTS)
python demos/embodied/conversation.py --model gemma3:4b --whisper-model base --no-tts

# Specify audio device
python demos/embodied/conversation.py --audio-device 2
```

### How It Works

1. **Listen** - Records 4 seconds of audio from BCC950 mic
2. **Transcribe** - Whisper converts speech to text
3. **See** - Captures camera frame via OpenCV
4. **Think** - Sends transcript + frame to Ollama (qwen3-vl:32b)
5. **Act** - Executes any tool calls (pan, tilt, zoom)
6. **Speak** - Piper TTS reads response aloud as Amy
7. **Loop** - Back to step 1

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
