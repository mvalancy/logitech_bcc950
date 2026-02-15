#!/usr/bin/env python3
"""Basic embodied AI demo for BCC950 camera.

A simple ~200-line demo showing:
  - BCC950 camera + YOLO person tracking
  - Whisper speech-to-text
  - Piper text-to-speech
  - Basic see→hear→think→speak→move loop

For the full consciousness architecture (sensorium, thinking thread,
memory, autonomous behavior), see: https://github.com/scubasonar/tritium-sc

Usage:
    python demos/basic_embodied.py
    python demos/basic_embodied.py --no-tts --whisper-model base
"""

import argparse
import os
import subprocess
import sys
import threading
import time

import cv2
import numpy as np

# Ensure the bcc950 package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'build'))

from bcc950 import BCC950Controller


# --- Audio helpers ---

def find_bcc950_mic():
    """Auto-detect BCC950 microphone index."""
    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if 'bcc950' in d['name'].lower() and d['max_input_channels'] > 0:
                return i
    except Exception:
        pass
    return None


def record_audio(device_idx, duration=4.0):
    """Record audio from BCC950 mic, return 16kHz mono float32."""
    import sounddevice as sd
    native_rate = 44100
    channels = 2
    samples = int(native_rate * duration)
    audio = sd.rec(samples, samplerate=native_rate, channels=channels,
                   dtype='float32', device=device_idx)
    sd.wait()
    mono = audio[:, 0]
    # Resample 44100 → 16000
    target = int(len(mono) * 16000 / native_rate)
    resampled = np.interp(
        np.linspace(0, len(mono) - 1, target),
        np.arange(len(mono)),
        mono
    ).astype(np.float32)
    return resampled


def transcribe(model, audio):
    """Transcribe audio with Whisper. Returns text or empty string."""
    result = model.transcribe(audio, language='en', fp16=True)
    text = result.get('text', '').strip()
    # Filter hallucinations
    hallucinations = [
        'thank you', 'thanks for watching', 'subscribe',
        'you', 'bye', 'the end',
    ]
    if text.lower() in hallucinations or len(text) < 3:
        return ''
    return text


def speak(text, piper_dir=None):
    """Speak text using Piper TTS + aplay. Non-blocking."""
    if not piper_dir:
        piper_dir = os.path.expanduser('~/models/piper')
    piper_bin = os.path.join(piper_dir, 'piper')
    model_file = None
    for f in os.listdir(piper_dir):
        if f.endswith('.onnx') and 'amy' in f.lower():
            model_file = os.path.join(piper_dir, f)
            break
    if not model_file:
        for f in os.listdir(piper_dir):
            if f.endswith('.onnx'):
                model_file = os.path.join(piper_dir, f)
                break
    if not os.path.isfile(piper_bin) or not model_file:
        print(f'[TTS] Piper not found at {piper_dir}')
        return
    cmd = f'echo {repr(text)} | {piper_bin} --model {model_file} --output-raw | aplay -r 22050 -f S16_LE -t raw -c 1 -q'
    threading.Thread(target=lambda: subprocess.run(cmd, shell=True), daemon=True).start()


# --- Vision helpers ---

def load_yolo():
    """Load YOLOv8 model."""
    try:
        from ultralytics import YOLO
        model = YOLO('yolov8n.pt')
        return model
    except ImportError:
        print('[YOLO] ultralytics not installed, tracking disabled')
        return None


def detect_person(yolo, frame):
    """Detect largest person, return (cx, cy, w, h) or None."""
    if yolo is None:
        return None
    results = yolo(frame, verbose=False, conf=0.5)
    best = None
    best_area = 0
    for r in results:
        for box in r.boxes:
            if int(box.cls) == 0:  # person
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                w, h = x2 - x1, y2 - y1
                area = w * h
                if area > best_area:
                    best_area = area
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    best = (cx, cy, w, h)
    return best


def track_person(ctrl, frame, detection):
    """Pan/tilt to center person in frame."""
    if detection is None:
        return
    cx, cy, _, _ = detection
    fh, fw = frame.shape[:2]
    dx = (cx / fw) - 0.5  # -0.5 to +0.5
    dy = (cy / fh) - 0.5
    dead_zone = 0.12
    if abs(dx) > dead_zone:
        dur = min(abs(dx) * 0.3, 0.15)
        if dx < 0:
            ctrl.pan_left(duration=dur)
        else:
            ctrl.pan_right(duration=dur)
    if abs(dy) > dead_zone:
        dur = min(abs(dy) * 0.3, 0.15)
        if dy < 0:
            ctrl.tilt_up(duration=dur)
        else:
            ctrl.tilt_down(duration=dur)


# --- LLM ---

def ask_ollama(prompt, image_b64=None, model='llava:7b', host='http://localhost:11434'):
    """Query Ollama with optional image. Returns text."""
    import json
    import urllib.request
    body = {
        'model': model,
        'prompt': prompt,
        'stream': False,
    }
    if image_b64:
        body['images'] = [image_b64]
    data = json.dumps(body).encode()
    req = urllib.request.Request(f'{host}/api/generate', data=data,
                                headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get('response', '')
    except Exception as e:
        return f'(LLM error: {e})'


# --- Main Loop ---

def main():
    parser = argparse.ArgumentParser(description='Basic embodied AI demo')
    parser.add_argument('--model', default='llava:7b', help='Ollama model')
    parser.add_argument('--whisper-model', default='large-v3', help='Whisper model size')
    parser.add_argument('--no-tts', action='store_true', help='Disable TTS')
    parser.add_argument('--no-tracking', action='store_true', help='Disable YOLO tracking')
    parser.add_argument('--device', type=int, help='Camera device index')
    args = parser.parse_args()

    # Init controller
    ctrl = BCC950Controller(device=args.device)
    print(f'[BCC950] Connected: {ctrl.device_path}')
    ctrl.reset_position()

    # Init camera
    dev_idx = int(ctrl.device_path.replace('/dev/video', ''))
    cap = cv2.VideoCapture(dev_idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print('[CAM] Failed to open camera')
        sys.exit(1)

    # Init YOLO
    yolo = None if args.no_tracking else load_yolo()

    # Init Whisper
    mic_idx = find_bcc950_mic()
    whisper_model = None
    if mic_idx is not None:
        try:
            import whisper
            print(f'[WHISPER] Loading {args.whisper_model}...')
            whisper_model = whisper.load_model(args.whisper_model)
            print(f'[MIC] Using device {mic_idx}')
        except ImportError:
            print('[WHISPER] Not installed, voice disabled')
    else:
        print('[MIC] BCC950 microphone not found, voice disabled')

    import base64
    print('\n--- Basic Embodied AI Demo ---')
    print('Camera running. Say something or press Ctrl+C to quit.\n')

    try:
        while True:
            # 1. See
            ret, frame = cap.read()
            if not ret:
                continue

            # 2. Track (YOLO)
            person = detect_person(yolo, frame)
            if person:
                track_person(ctrl, frame, person)

            # 3. Hear
            transcript = ''
            if whisper_model and mic_idx is not None:
                audio = record_audio(mic_idx, duration=4.0)
                energy = float(np.sqrt(np.mean(audio ** 2)))
                if energy > 0.005:
                    transcript = transcribe(whisper_model, audio)

            if not transcript:
                time.sleep(0.1)
                continue

            print(f'[YOU] {transcript}')

            # 4. Think — encode current frame + ask LLM
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            img_b64 = base64.b64encode(jpeg.tobytes()).decode()
            prompt = (
                f'You are Amy, an AI in a camera. The user said: "{transcript}"\n'
                f'What do you see in the image? Respond briefly (1-2 sentences).'
            )
            response = ask_ollama(prompt, image_b64=img_b64, model=args.model)
            print(f'[AMY] {response}')

            # 5. Speak
            if not args.no_tts:
                speak(response)

    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        cap.release()
        ctrl.reset_position()


if __name__ == '__main__':
    main()
