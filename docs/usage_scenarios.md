# Usage Scenarios

Detailed guides for each way to use the BCC950 camera system.

## 1. Basic PTZ Control

Direct camera control via CLI or Python API.

```mermaid
flowchart LR
    User -->|CLI command| CLI["bcc950 CLI"]
    CLI --> Ctrl["BCC950Controller"]
    Ctrl --> Motion["MotionController"]
    Motion -->|v4l2-ctl| Camera["BCC950"]
```

### CLI Usage

```bash
source .venv/bin/activate

# Single movements
bcc950 --pan-left
bcc950 --pan-right --duration 0.5
bcc950 --tilt-up
bcc950 --zoom-value 300

# Combined movement
bcc950 --move -1 1 1.0    # pan left + tilt up for 1s

# Presets
bcc950 --save-preset "desk"
bcc950 --recall-preset "desk"
bcc950 --list-presets

# Info
bcc950 --info
bcc950 --list
bcc950 --reset
```

### Python API

```python
from bcc950 import BCC950Controller

cam = BCC950Controller()
cam.find_camera()          # Auto-detect BCC950

cam.pan_left(0.5)          # Pan left for 0.5s
cam.tilt_up(0.3)           # Tilt up for 0.3s
cam.zoom_to(300)           # Zoom to 300/500
cam.move(-1, 1, 1.0)       # Combined: pan left + tilt up

cam.save_preset("view1")   # Save position
cam.recall_preset("view1") # Return to saved position
print(cam.position)        # Show estimated position
cam.reset_position()       # Reset to center
```

**Prerequisites**: v4l-utils, bcc950 package
**Setup time**: 2 minutes

---

## 2. Vision-Verified Movement

Use OpenCV to confirm the camera actually moved by analyzing optical flow.

```mermaid
sequenceDiagram
    participant User
    participant Verifier as Movement Verifier
    participant Camera as BCC950
    participant CV as OpenCV

    User->>Verifier: Press 'a' (pan left)
    Verifier->>Camera: pan_left(0.3)
    Verifier->>CV: Capture frame before
    Note over Camera: Motor runs 0.3s
    Verifier->>CV: Capture frame after
    CV->>CV: Lucas-Kanade optical flow
    CV->>Verifier: Flow vectors (dx, dy)
    Verifier->>User: Overlay arrows on feed
```

### Run

```bash
source .venv/bin/activate

# Interactive PTZ with live optical flow
python demos/vision/movement_verifier.py --device /dev/video0

# Motion tracking (auto-follow objects)
python demos/vision/motion_tracker.py --device /dev/video0

# ArUco marker calibration
python demos/vision/calibration.py --device /dev/video0
```

**Controls**: `a/d` pan, `w/s` tilt, `+/-` zoom, `r` reset, `q` quit

**Prerequisites**: OpenCV, NumPy, v4l-utils, bcc950
**Setup time**: 5 minutes

---

## 3. Voice-Controlled Camera

Speak commands and the camera obeys using Whisper STT.

```mermaid
sequenceDiagram
    participant Human
    participant Mic as BCC950 Mic
    participant Whisper as Whisper STT
    participant Parser as Command Parser
    participant Camera as BCC950

    loop Every 4 seconds
        Mic->>Whisper: Audio chunk (16kHz)
        Whisper->>Parser: "look left"
        Parser->>Camera: pan_left(0.3)
        Camera->>Human: Camera pans left
    end
```

### Run

```bash
source .venv/bin/activate
python demos/voice/voice_control.py

# With options
python demos/voice/voice_control.py --device /dev/video0 --whisper-model base
```

### Supported Commands

| Say this | Camera does |
|---------|-------------|
| "look left" / "pan left" | Pan left |
| "look right" / "pan right" | Pan right |
| "look up" / "tilt up" | Tilt up |
| "look down" / "tilt down" | Tilt down |
| "pan left for 2 seconds" | Timed pan |
| "zoom in" / "zoom out" | Zoom |
| "zoom to 300" | Absolute zoom |
| "reset" / "center" | Reset position |
| "quit" / "exit" | Exit |

**Prerequisites**: Whisper, sounddevice, NumPy, v4l-utils, bcc950
**Setup time**: 10 minutes (Whisper model download)

---

## 4. Embodied AI Conversation (Amy)

Full conversational AI that sees, hears, speaks, and moves.

```mermaid
sequenceDiagram
    participant Human
    participant Mic as BCC950 Mic
    participant Whisper as Whisper STT
    participant Vision as OpenCV
    participant Agent as Ollama (qwen3-vl)
    participant Tools as Tool Dispatch
    participant Camera as BCC950
    participant TTS as Piper (Amy)

    Note over Human,TTS: Startup
    TTS->>Human: "Hello! I'm Amy..."

    loop Conversation
        Mic->>Whisper: Record 4s audio
        Whisper->>Agent: "Can you look at the whiteboard?"
        Vision->>Agent: Camera frame (base64)
        Agent->>Tools: pan_camera(right, 0.5)
        Tools->>Camera: pan_right(0.5)
        Agent->>TTS: "I've panned right to look at the whiteboard. I can see..."
        TTS->>Human: Speaks response aloud
    end
```

### Run

```bash
source .venv/bin/activate

# Full demo (requires all components)
python demos/embodied/conversation.py

# With lightweight model
python demos/embodied/conversation.py --model gemma3:4b --whisper-model base

# Text-only (no TTS)
python demos/embodied/conversation.py --no-tts
```

### Architecture

```
conversation.py     Main loop: listen -> see -> think -> act -> speak
  listener.py       Whisper STT (records from BCC950 mic)
  vision.py         OpenCV capture + base64 encoding
  agent.py          Ollama chat with tool definitions
  tools.py          Maps tool calls to BCC950Controller
  speaker.py        Piper TTS with queued playback
```

**Prerequisites**: All of the above + Ollama + Piper TTS
**Setup time**: 30 minutes (model downloads)

---

## 5. AI-Narrated Camera

The camera describes what it sees using an Ollama vision model.

```mermaid
flowchart TD
    Camera["BCC950"] -->|frame| CV["OpenCV"]
    CV -->|base64 JPEG| Ollama["Ollama qwen3-vl:32b"]
    Ollama -->|description text| TTS["Piper Amy TTS"]
    TTS -->|audio| Speaker["Speaker"]
```

### Run

```bash
source .venv/bin/activate

# AI narration via Ollama vision model
python demos/voice/narrator.py --use-ollama

# With specific model
python demos/voice/narrator.py --use-ollama --model gemma3:4b

# Classic Haar cascade mode (no AI needed)
python demos/voice/narrator.py

# Show video feed with detection overlay
python demos/voice/narrator.py --show
```

**Prerequisites**: OpenCV, Ollama (for --use-ollama), Piper TTS (optional)
**Setup time**: 15 minutes

---

## 6. Development

### Run Tests

```bash
source .venv/bin/activate

# Unit tests (no hardware)
cd src/python && pytest -v

# Hardware integration tests
pytest --run-hardware --device /dev/video0 -v

# Vision verification tests
pytest --run-hardware --run-vision --device /dev/video0 -v

# C++ tests
cd src/cpp && mkdir -p build && cd build
cmake .. && make -j$(nproc) && ctest -v
```

### Generate System Report

```bash
python scripts/generate_report.py
# Opens report.html in browser
```

### Project Architecture

```mermaid
graph TD
    subgraph "User Interfaces"
        CLI["CLI (bcc950)"]
        DEMOS["Demos"]
        EMBODIED["Embodied AI"]
    end

    subgraph "Python Library"
        CTRL["BCC950Controller"]
        MOTION["MotionController"]
        POS["PositionTracker"]
        PRESETS["PresetManager"]
    end

    subgraph "AI Stack"
        WHISPER["Whisper STT"]
        OLLAMA["Ollama Vision"]
        PIPER["Piper TTS"]
    end

    subgraph "Hardware"
        V4L2["V4L2 Backend"]
        CAM["BCC950 Camera"]
    end

    CLI --> CTRL
    DEMOS --> CTRL
    EMBODIED --> CTRL
    EMBODIED --> WHISPER
    EMBODIED --> OLLAMA
    EMBODIED --> PIPER

    CTRL --> MOTION
    CTRL --> POS
    CTRL --> PRESETS
    MOTION --> V4L2
    V4L2 --> CAM
```
