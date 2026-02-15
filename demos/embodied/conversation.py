#!/usr/bin/env python3
"""Embodied AI conversation demo for the Logitech BCC950.

Amy is an AI that sees through the camera, hears via the microphone,
speaks with Piper TTS, and moves the camera with PTZ controls.

Usage:
    python demos/embodied/conversation.py
    python demos/embodied/conversation.py --device /dev/video0
    python demos/embodied/conversation.py --model gemma3:4b
    python demos/embodied/conversation.py --whisper-model base --no-tts
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "python"))

from bcc950 import BCC950Controller


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Amy: Embodied AI conversation demo for the BCC950"
    )
    parser.add_argument("--device", default=None, help="V4L2 device path (auto-detect if omitted)")
    parser.add_argument("--model", default="qwen3-vl:32b", help="Ollama vision model (default: qwen3-vl:32b)")
    parser.add_argument("--whisper-model", default="large-v3", help="Whisper model (default: large-v3)")
    parser.add_argument("--record-seconds", type=float, default=4.0, help="Recording duration per turn")
    parser.add_argument("--no-tts", action="store_true", help="Disable TTS (text-only output)")
    parser.add_argument("--audio-device", type=int, default=None, help="Audio input device index")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  Amy - Embodied AI Demo")
    print("  Logitech BCC950 Camera")
    print("=" * 50)
    print()

    # Initialize camera controller
    print("Initializing camera...")
    cam = BCC950Controller(device=args.device)
    if args.device is None:
        device = cam.find_camera()
        if device:
            print(f"  Found camera at {device}")
        else:
            print("  Could not auto-detect camera. Use --device /dev/videoN")
            sys.exit(1)
    else:
        print(f"  Using device {args.device}")

    # Reset camera to center
    print("  Resetting camera position...")
    cam.reset_position()
    time.sleep(0.5)

    # Initialize vision (OpenCV capture)
    # Support running from project root or demos/embodied/ directory
    demo_dir = os.path.dirname(os.path.abspath(__file__))
    if demo_dir not in sys.path:
        sys.path.insert(0, os.path.dirname(demo_dir))
    from embodied.vision import Vision
    vision = Vision(device=cam.device)
    if not vision.open():
        print(f"  Could not open camera for video capture at {cam.device}")
        sys.exit(1)
    print("  Camera video stream opened.")

    # Initialize listener (Whisper STT)
    print("Initializing speech recognition...")
    from embodied.listener import Listener
    listener = Listener(model_name=args.whisper_model, audio_device=args.audio_device)

    # Initialize speaker (Piper TTS)
    from embodied.speaker import Speaker
    speaker = Speaker()
    if args.no_tts or not speaker.available:
        if not args.no_tts:
            print("  Piper TTS not available, running in text-only mode.")
        use_tts = False
    else:
        use_tts = True
        print("  Piper TTS ready (Amy voice).")

    # Initialize agent (Ollama)
    from embodied.agent import Agent
    agent = Agent(controller=cam, model=args.model)
    print(f"  Ollama model: {args.model}")

    print()
    print("=" * 50)
    print("  Amy is ready! Speak to her.")
    print("  Press Ctrl+C to exit.")
    print("=" * 50)
    print()

    # Startup greeting
    greeting = "Hello! I'm Amy. I can see through this camera, hear you speaking, and move around. What would you like to talk about?"
    print(f'  Amy: "{greeting}"')
    if use_tts:
        speaker.speak_sync(greeting)

    # Main conversation loop
    turn = 0
    try:
        while True:
            turn += 1
            print(f"\n--- Turn {turn} ---")

            # Listen
            print("  Listening...")
            transcript = listener.listen(duration=args.record_seconds)

            if transcript:
                print(f'  You: "{transcript}"')

                # Check for exit commands
                lower = transcript.lower().strip()
                if any(word in lower for word in ["quit", "exit", "goodbye", "shut down"]):
                    farewell = "Goodbye! It was nice talking to you."
                    print(f'  Amy: "{farewell}"')
                    if use_tts:
                        speaker.speak_sync(farewell)
                    break
            else:
                print("  (silence)")
                # Only do periodic awareness every 3rd silent turn
                if turn % 3 != 0:
                    continue

            # See
            print("  Capturing frame...")
            image_b64 = vision.capture_base64()

            # Think
            print(f"  Thinking ({args.model})...")
            response = agent.process_turn(
                transcript=transcript,
                image_base64=image_b64,
            )

            # Speak
            print(f'  Amy: "{response}"')
            if use_tts:
                speaker.speak(response)

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        print("Shutting down...")
        cam.stop()
        vision.close()
        speaker.shutdown()
        print("Done.")


if __name__ == "__main__":
    main()
