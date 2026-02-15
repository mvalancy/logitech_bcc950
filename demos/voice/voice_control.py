#!/usr/bin/env python3
"""Voice-controlled camera demo for the Logitech BCC950.

Uses OpenAI Whisper for speech-to-text, captures microphone input, parses
natural language commands, and drives the camera accordingly.

Usage:
    python voice_control.py
    python voice_control.py --device /dev/video2
    python voice_control.py --whisper-model small

Supported commands:
    "look left" / "look right" / "look up" / "look down"
    "pan left" / "pan right" / "tilt up" / "tilt down"
    "pan left for 2 seconds"
    "zoom in" / "zoom out"
    "zoom to 300"
    "reset" / "center"
    "stop"
    "quit" / "exit"

Extension points:
    - Add new commands by extending COMMAND_PATTERNS in parse_command()
    - Replace Whisper with another STT engine (Vosk, DeepSpeech, etc.)
    - Add wake word detection before processing commands
    - Integrate an LLM for more flexible natural language understanding
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "python"))

# Check for audio dependencies
try:
    import numpy as np
except ImportError:
    print("Error: NumPy is required for this demo.")
    print("Install it with:  pip install numpy")
    sys.exit(1)

try:
    import sounddevice as sd
except ImportError:
    print("Error: sounddevice is required for this demo.")
    print("Install it with:  pip install sounddevice")
    sys.exit(1)

try:
    import whisper
except ImportError:
    print("Error: OpenAI Whisper is required for this demo.")
    print("Install it with:  pip install openai-whisper")
    sys.exit(1)

from bcc950 import BCC950Controller

# --- Configuration ---
SAMPLE_RATE = 16000  # Whisper expects 16kHz
RECORD_SECONDS = 4  # Duration of each recording chunk
DEFAULT_WHISPER_MODEL = "large-v3"
DEFAULT_MOVE_DURATION = 0.3


# --- Command patterns ---
# Each pattern is (regex, handler_name, description).
# Handler names map to functions in execute_command().
#
# Extension point: add new patterns here for additional commands.
COMMAND_PATTERNS: list[tuple[str, str]] = [
    # Directional movement with optional duration
    (r"(?:look|pan|turn|go)\s+left(?:\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:seconds?)?)?", "pan_left"),
    (r"(?:look|pan|turn|go)\s+right(?:\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:seconds?)?)?", "pan_right"),
    (r"(?:look|tilt|turn|go)\s+up(?:\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:seconds?)?)?", "tilt_up"),
    (r"(?:look|tilt|turn|go)\s+down(?:\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:seconds?)?)?", "tilt_down"),
    # Zoom
    (r"zoom\s+in", "zoom_in"),
    (r"zoom\s+out", "zoom_out"),
    (r"zoom\s+(?:to|at)\s+(\d+)", "zoom_to"),
    # Reset / stop
    (r"(?:reset|center|home)", "reset"),
    (r"stop", "stop"),
    # Quit
    (r"(?:quit|exit|bye|goodbye|shut\s*down)", "quit"),
]


def find_bcc950_audio_device() -> int | None:
    """Find the BCC950 microphone in sounddevice's device list."""
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        name = d.get("name", "").lower()
        if d["max_input_channels"] > 0 and ("bcc950" in name or "conferencecam" in name):
            return i
    return None


def record_audio(duration: float, sample_rate: int, device: int | None = None) -> np.ndarray:
    """Record audio from the microphone.

    If device is None, uses the default input device.
    Extension point: replace with a streaming VAD (voice activity
    detection) approach for more responsive interaction.
    """
    print(f"  Listening for {duration}s...")
    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    return audio.flatten()


def transcribe(model: whisper.Whisper, audio: np.ndarray) -> str:
    """Transcribe audio using Whisper.

    Extension point: replace with Vosk, DeepSpeech, or a streaming
    STT engine for lower latency.
    """
    result = model.transcribe(audio, fp16=False, language="en")
    text = result.get("text", "").strip().lower()
    return text


def parse_command(text: str) -> tuple[str, list[str]]:
    """Parse transcribed text into a command and arguments.

    Returns:
        (command_name, [arg1, arg2, ...]) or ("unknown", [])

    Extension point: add entries to COMMAND_PATTERNS at the module level,
    or replace this with an LLM-based intent parser for more flexible
    natural language understanding.
    """
    text = text.strip().lower()

    for pattern, command_name in COMMAND_PATTERNS:
        match = re.search(pattern, text)
        if match:
            args = [g for g in match.groups() if g is not None]
            return command_name, args

    return "unknown", []


def execute_command(
    cam: BCC950Controller,
    command: str,
    args: list[str],
    default_duration: float,
) -> bool:
    """Execute a parsed command on the camera.

    Returns False if the quit command was issued, True otherwise.

    Extension point: add new elif branches for custom commands.
    """
    if command == "pan_left":
        duration = float(args[0]) if args else default_duration
        print(f"  -> Pan left ({duration}s)")
        cam.pan_left(duration)

    elif command == "pan_right":
        duration = float(args[0]) if args else default_duration
        print(f"  -> Pan right ({duration}s)")
        cam.pan_right(duration)

    elif command == "tilt_up":
        duration = float(args[0]) if args else default_duration
        print(f"  -> Tilt up ({duration}s)")
        cam.tilt_up(duration)

    elif command == "tilt_down":
        duration = float(args[0]) if args else default_duration
        print(f"  -> Tilt down ({duration}s)")
        cam.tilt_down(duration)

    elif command == "zoom_in":
        print("  -> Zoom in")
        cam.zoom_in()

    elif command == "zoom_out":
        print("  -> Zoom out")
        cam.zoom_out()

    elif command == "zoom_to":
        value = int(args[0]) if args else 100
        print(f"  -> Zoom to {value}")
        cam.zoom_to(value)

    elif command == "reset":
        print("  -> Reset to center")
        cam.reset_position()

    elif command == "stop":
        print("  -> Stop")
        cam.stop()

    elif command == "quit":
        print("  -> Goodbye!")
        return False

    elif command == "unknown":
        print("  -> Command not recognized.")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Voice-controlled Logitech BCC950 camera."
    )
    parser.add_argument(
        "--device", default="/dev/video0", help="V4L2 device path (default: /dev/video0)"
    )
    parser.add_argument(
        "--whisper-model",
        default=DEFAULT_WHISPER_MODEL,
        help=f"Whisper model size (default: {DEFAULT_WHISPER_MODEL})",
    )
    parser.add_argument(
        "--record-seconds",
        type=float,
        default=RECORD_SECONDS,
        help=f"Recording duration per chunk in seconds (default: {RECORD_SECONDS})",
    )
    parser.add_argument(
        "--move-duration",
        type=float,
        default=DEFAULT_MOVE_DURATION,
        help=f"Default movement duration in seconds (default: {DEFAULT_MOVE_DURATION})",
    )
    parser.add_argument(
        "--audio-device",
        type=int,
        default=None,
        help="Audio input device index (default: auto-detect BCC950, then system default)",
    )
    args = parser.parse_args()

    # Auto-detect BCC950 microphone
    if args.audio_device is None:
        bcc_dev = find_bcc950_audio_device()
        if bcc_dev is not None:
            args.audio_device = bcc_dev
            print(f"Auto-detected BCC950 microphone (device {bcc_dev})")

    print(f"Loading Whisper model '{args.whisper_model}'...")
    model = whisper.load_model(args.whisper_model)
    print("Model loaded.")

    cam = BCC950Controller(device=args.device)

    print()
    print("BCC950 Voice Control")
    print("====================")
    print(f"Device: {args.device}")
    print(f"Whisper model: {args.whisper_model}")
    print(f"Recording {args.record_seconds}s chunks")
    print()
    print("Say a command (e.g., 'look left', 'zoom in', 'quit').")
    print("Press Ctrl+C to exit.")
    print()

    running = True
    try:
        while running:
            audio = record_audio(args.record_seconds, SAMPLE_RATE, device=args.audio_device)

            # Skip near-silent audio
            if np.max(np.abs(audio)) < 0.01:
                continue

            text = transcribe(model, audio)
            if not text:
                continue

            print(f'  Heard: "{text}"')
            command, cmd_args = parse_command(text)
            running = execute_command(cam, command, cmd_args, args.move_duration)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        cam.stop()
        print("Voice control stopped.")


if __name__ == "__main__":
    main()
