#!/usr/bin/env python3
"""Camera narrator demo for the Logitech BCC950.

Captures frames from the camera, runs basic object detection (or delegates
to a vision model stub), and speaks a description of what it sees using
Piper TTS.

Usage:
    python narrator.py
    python narrator.py --device /dev/video2
    python narrator.py --interval 10
    python narrator.py --piper-model en_US-lessac-medium

Extension points:
    - Replace describe_frame() with a call to an LLM vision API
      (GPT-4V, Claude, Gemini) for richer descriptions
    - Add object tracking to describe movement and changes over time
    - Integrate with voice_control.py for a full conversational camera
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "python"))

try:
    import numpy as np
except ImportError:
    print("Error: NumPy is required for this demo.")
    print("Install it with:  pip install numpy")
    sys.exit(1)

try:
    import cv2
except ImportError:
    print("Error: OpenCV is required for this demo.")
    print("Install it with:  pip install opencv-python")
    sys.exit(1)

# Piper TTS is optional at import time; we check at runtime
_piper_available = False
try:
    from piper import PiperVoice

    _piper_available = True
except ImportError:
    pass

from bcc950 import BCC950Controller

# --- Configuration ---
DEFAULT_INTERVAL = 5  # seconds between narrations
DEFAULT_PIPER_MODEL = "en_US-lessac-medium"
DEFAULT_OLLAMA_MODEL = "qwen3-vl:32b"
# Haar cascade for basic face detection (ships with OpenCV)
HAAR_FACE_CASCADE = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
HAAR_BODY_CASCADE = cv2.data.haarcascades + "haarcascade_upperbody.xml"

# Piper binary path (setup.sh installs here)
PIPER_BIN = os.path.join(os.path.dirname(__file__), "..", "..", "models", "piper", "piper")
PIPER_AMY_MODEL = os.path.join(os.path.dirname(__file__), "..", "..", "models", "piper", "en_US-amy-medium.onnx")


def detect_objects(frame: np.ndarray) -> list[dict]:
    """Run basic object detection on a frame using Haar cascades.

    Returns a list of detected objects, each as:
        {"label": str, "bbox": (x, y, w, h), "confidence": float}

    Extension point: replace this with YOLO, MobileNet-SSD, or an LLM
    vision API call for much richer detection and scene understanding.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detections: list[dict] = []

    # Face detection
    face_cascade = cv2.CascadeClassifier(HAAR_FACE_CASCADE)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    for x, y, w, h in faces:
        detections.append({
            "label": "face",
            "bbox": (int(x), int(y), int(w), int(h)),
            "confidence": 0.8,
        })

    # Upper body detection
    body_cascade = cv2.CascadeClassifier(HAAR_BODY_CASCADE)
    bodies = body_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
    for x, y, w, h in bodies:
        detections.append({
            "label": "person",
            "bbox": (int(x), int(y), int(w), int(h)),
            "confidence": 0.6,
        })

    return detections


def describe_frame(frame: np.ndarray, detections: list[dict]) -> str:
    """Generate a natural language description using Haar cascades.

    This is the default fallback. Use --use-ollama for richer AI narration.
    """
    h, w = frame.shape[:2]

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = np.mean(gray)

    if brightness < 50:
        light_desc = "The scene is quite dark."
    elif brightness < 120:
        light_desc = "The lighting is moderate."
    else:
        light_desc = "The scene is well lit."

    if not detections:
        return f"I see an open area with no people detected. {light_desc}"

    label_counts: dict[str, int] = {}
    for det in detections:
        label = det["label"]
        label_counts[label] = label_counts.get(label, 0) + 1

    parts: list[str] = []

    face_count = label_counts.get("face", 0)
    person_count = label_counts.get("person", 0)

    if face_count == 1:
        det = next(d for d in detections if d["label"] == "face")
        x, y, bw, bh = det["bbox"]
        cx = x + bw // 2

        if cx < w // 3:
            position = "on the left side"
        elif cx > 2 * w // 3:
            position = "on the right side"
        else:
            position = "in the center"

        parts.append(f"I can see one person's face {position} of the frame")

    elif face_count > 1:
        parts.append(f"I can see {face_count} faces")

    if person_count > 0 and face_count == 0:
        parts.append(
            f"I detect {person_count} {'person' if person_count == 1 else 'people'}"
        )

    parts.append(light_desc)

    return ". ".join(parts) + "."


def describe_frame_ollama(frame: np.ndarray, model: str = DEFAULT_OLLAMA_MODEL) -> str:
    """Generate a description using Ollama's vision model.

    Encodes the frame as base64 and sends it to the specified Ollama
    multimodal model for a natural language description.
    """
    import base64
    import json
    import urllib.request

    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    image_b64 = base64.b64encode(buffer).decode("utf-8")

    payload = json.dumps({
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Describe what you see in this image in 2-3 sentences. Be specific about people, objects, and the setting.",
                "images": [image_b64],
            }
        ],
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("message", {}).get("content", "I couldn't describe what I see.")
    except Exception as e:
        return f"Vision model error: {e}"


def speak_text(text: str, piper_model: str) -> None:
    """Speak text using Piper TTS.

    Falls back to printing if Piper is not available.

    Extension point: replace with another TTS engine (Coqui, espeak,
    gTTS, or a cloud API) by modifying this function.
    """
    print(f'  Narration: "{text}"')

    if not _piper_available:
        print("  (Piper TTS not installed - text only)")
        print("  Install with:  pip install piper-tts")
        return

    try:
        # Use piper CLI as a subprocess for simplicity
        # Piper reads text from stdin and outputs WAV to stdout
        process = subprocess.Popen(
            ["piper", "--model", piper_model, "--output-raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        raw_audio, stderr = process.communicate(input=text.encode("utf-8"))

        if process.returncode != 0:
            print(f"  Piper TTS error: {stderr.decode().strip()}")
            return

        # Play the raw audio using sounddevice if available
        try:
            import sounddevice as sd

            audio_array = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(audio_array, samplerate=22050)
            sd.wait()
        except ImportError:
            # Fall back to saving a temp file and playing with aplay
            with tempfile.NamedTemporaryFile(suffix=".raw", delete=True) as f:
                f.write(raw_audio)
                f.flush()
                subprocess.run(
                    ["aplay", "-r", "22050", "-f", "S16_LE", "-c", "1", f.name],
                    capture_output=True,
                )

    except FileNotFoundError:
        print("  Piper binary not found in PATH. Install with: pip install piper-tts")
    except Exception as e:
        print(f"  TTS error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Camera narrator: describes what the BCC950 sees using TTS."
    )
    parser.add_argument(
        "--device", default="/dev/video0", help="V4L2 device path (default: /dev/video0)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between narrations (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--piper-model",
        default=DEFAULT_PIPER_MODEL,
        help=f"Piper TTS model name (default: {DEFAULT_PIPER_MODEL})",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show camera feed with detection overlay",
    )
    parser.add_argument(
        "--use-ollama",
        action="store_true",
        help="Use Ollama vision model instead of Haar cascades",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OLLAMA_MODEL,
        help=f"Ollama model for --use-ollama (default: {DEFAULT_OLLAMA_MODEL})",
    )
    args = parser.parse_args()

    cam = BCC950Controller(device=args.device)
    cap = cv2.VideoCapture(args.device)

    if not cap.isOpened():
        print(f"Error: Could not open video device {args.device}")
        sys.exit(1)

    print("BCC950 Camera Narrator")
    print("======================")
    print(f"Device: {args.device}")
    print(f"Narration interval: {args.interval}s")
    print(f"Piper model: {args.piper_model}")
    if args.use_ollama:
        print(f"Vision: Ollama ({args.model})")
    else:
        print("Vision: Haar cascades (use --use-ollama for AI narration)")
    print()
    print("Press Ctrl+C to stop.")
    if args.show:
        print("Press 'q' in the video window to quit.")
    print()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Failed to capture frame.")
                break

            if args.use_ollama:
                description = describe_frame_ollama(frame, model=args.model)
                detections = []  # Skip Haar cascade when using Ollama
            else:
                detections = detect_objects(frame)
                description = describe_frame(frame, detections)
            speak_text(description, args.piper_model)

            if args.show:
                display = frame.copy()
                for det in detections:
                    x, y, w, h = det["bbox"]
                    label = f"{det['label']} ({det['confidence']:.0%})"
                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(
                        display, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                    )
                cv2.imshow("BCC950 Narrator", display)

            # Wait for the interval, checking for quit key if showing video
            wait_start = time.time()
            while time.time() - wait_start < args.interval:
                if args.show:
                    ret, frame = cap.read()
                    if ret:
                        cv2.imshow("BCC950 Narrator", frame)
                    key = cv2.waitKey(100) & 0xFF
                    if key == ord("q"):
                        raise KeyboardInterrupt
                else:
                    time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
