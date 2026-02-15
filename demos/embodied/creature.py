#!/usr/bin/env python3
"""Amy — an autonomous embodied AI creature living in a BCC950 camera.

She looks around on her own, notices things, responds to speech, and
feels alive.  Uses motor programs for smooth autonomous movement with
an LLM (Ollama) on top for perception and conversation.

Usage:
    python demos/embodied/creature.py
    python demos/embodied/creature.py --device /dev/video0
    python demos/embodied/creature.py --model gemma3:4b --no-tts
"""

from __future__ import annotations

import argparse
import base64
import enum
import os
import queue
import random
import re
import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "python"))

from bcc950 import BCC950Controller, MotionVerifier


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventType(enum.Enum):
    SPEECH_DETECTED = "speech_detected"
    TRANSCRIPT_READY = "transcript_ready"
    SILENCE = "silence"
    CURIOSITY_TICK = "curiosity_tick"
    MOTOR_DONE = "motor_done"
    PERSON_ARRIVED = "person_arrived"
    PERSON_LEFT = "person_left"
    SHUTDOWN = "shutdown"


class CreatureState(enum.Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"


class Event:
    __slots__ = ("type", "data")

    def __init__(self, event_type: EventType, data: object = None):
        self.type = event_type
        self.data = data


# ---------------------------------------------------------------------------
# Thread-safe VideoCapture wrapper
# ---------------------------------------------------------------------------

class LockedMotionVerifier(MotionVerifier):
    """MotionVerifier that acquires a shared lock around frame grabs.

    The BCC950 controller's MotionController already holds its own lock
    around move-verify sequences, but we need a *second* lock shared with
    the main thread's ``capture_frame()`` calls so the two never fight
    over the VideoCapture.
    """

    def __init__(self, cap: cv2.VideoCapture, cap_lock: threading.Lock, **kwargs):
        super().__init__(cap, **kwargs)
        self._cap_lock = cap_lock

    def grab_gray(self) -> np.ndarray:
        with self._cap_lock:
            return super().grab_gray()

    def grab_frame(self) -> np.ndarray:
        with self._cap_lock:
            return super().grab_frame()


# ---------------------------------------------------------------------------
# Audio thread
# ---------------------------------------------------------------------------

class AudioThread:
    """Continuous audio recording in a background thread.

    Posts SPEECH_DETECTED (immediately on non-silence) and
    TRANSCRIPT_READY (after transcription) events to the queue.
    """

    def __init__(
        self,
        listener,
        event_queue: queue.Queue,
        chunk_duration: float = 4.0,
    ):
        self.listener = listener
        self.queue = event_queue
        self.chunk_duration = chunk_duration
        self._enabled = threading.Event()
        self._enabled.set()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def disable(self) -> None:
        """Disable recording (e.g. while TTS is playing)."""
        self._enabled.clear()

    def enable(self) -> None:
        """Re-enable recording."""
        self._enabled.set()

    def stop(self) -> None:
        self._stop.set()
        self._enabled.set()  # unblock
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._enabled.wait()
            if self._stop.is_set():
                break

            try:
                audio = self.listener.record(self.chunk_duration)
            except Exception as e:
                print(f"  [audio error: {e}]")
                self._stop.wait(timeout=2)
                continue

            if self.listener.is_silence(audio):
                self.queue.put(Event(EventType.SILENCE))
                continue

            # Non-silent audio detected
            self.queue.put(Event(EventType.SPEECH_DETECTED))

            # Transcribe (slower)
            text = self.listener.transcribe(audio)
            if text:
                self.queue.put(Event(EventType.TRANSCRIPT_READY, data=text))
            else:
                # Non-silent but no words (noise, cough, etc.)
                self.queue.put(Event(EventType.SILENCE))


# ---------------------------------------------------------------------------
# Curiosity timer
# ---------------------------------------------------------------------------

class CuriosityTimer:
    """Fires CURIOSITY_TICK events at random intervals."""

    def __init__(
        self,
        event_queue: queue.Queue,
        min_interval: float = 15.0,
        max_interval: float = 25.0,
    ):
        self.queue = event_queue
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.is_set():
            delay = random.uniform(self.min_interval, self.max_interval)
            if self._stop.wait(timeout=delay):
                break
            self.queue.put(Event(EventType.CURIOSITY_TICK))


# ---------------------------------------------------------------------------
# Frame buffer — single reader to avoid lock contention
# ---------------------------------------------------------------------------

class FrameBuffer:
    """Continuously reads frames from VideoCapture into a shared buffer.

    All consumers (MJPEG stream, YOLO, deep think) read from the buffer
    instead of the camera directly.  This eliminates lock contention and
    ensures the video feed never freezes.

    Uses non-blocking acquire on ``cap_lock`` so it coexists with
    MotionVerifier — if the lock is held (during motor verification),
    the buffer simply serves the cached frame.
    """

    def __init__(self, cap: cv2.VideoCapture, cap_lock: threading.Lock):
        self._cap = cap
        self._cap_lock = cap_lock
        self._frame: np.ndarray | None = None
        self._jpeg: bytes | None = None
        self._frame_time: float = 0.0
        self._frame_id: int = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    @property
    def frame(self) -> np.ndarray | None:
        """Get the latest frame (thread-safe copy)."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    @property
    def jpeg(self) -> bytes | None:
        """Get the latest JPEG-encoded frame."""
        with self._lock:
            return self._jpeg

    @property
    def frame_id(self) -> int:
        """Monotonic counter incremented on each new frame."""
        with self._lock:
            return self._frame_id

    @property
    def frame_age(self) -> float:
        """Seconds since the last frame was captured."""
        with self._lock:
            return time.monotonic() - self._frame_time if self._frame_time > 0 else float("inf")

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._cap_lock.acquire(blocking=False):
                try:
                    ret, frame = self._cap.read()
                finally:
                    self._cap_lock.release()
                if ret and frame is not None:
                    # Copy frame — OpenCV may reuse internal buffer
                    frame = frame.copy()
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    with self._lock:
                        self._frame = frame
                        self._jpeg = buf.tobytes()
                        self._frame_time = time.monotonic()
                        self._frame_id += 1
            time.sleep(0.033)  # ~30 fps


# ---------------------------------------------------------------------------
# YOLO vision thread
# ---------------------------------------------------------------------------

class VisionThread:
    """Continuous YOLO object detection in a background thread.

    Grabs frames (non-blocking) from the shared VideoCapture, runs YOLOv8
    at ~3 fps, and maintains a live scene summary that gets injected into
    the LLM context.  Publishes detection events to the EventBus.
    """

    # Classes we care about for scene awareness
    TRACKED_CLASSES = {
        0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
        14: "bird", 15: "cat", 16: "dog",
        24: "backpack", 25: "umbrella",
        39: "bottle", 41: "cup", 56: "chair",
        62: "tv", 63: "laptop", 64: "mouse", 66: "keyboard",
        67: "cell phone", 73: "book",
    }

    def __init__(
        self,
        frame_buffer: FrameBuffer,
        event_bus,
        event_queue: queue.Queue | None = None,
        model_name: str = "yolo11n.pt",
        interval: float = 0.33,
    ):
        self._frame_buffer = frame_buffer
        self._event_bus = event_bus
        self._event_queue = event_queue
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._scene_lock = threading.Lock()
        self._scene_summary: str = "No detections yet."
        self._prev_people_count: int = 0
        self._empty_frames: int = 0  # consecutive frames with 0 people
        self._latest_detections: list[dict] = []
        self._detection_lock = threading.Lock()
        self._person_target: tuple[float, float] | None = None
        self._target_lock = threading.Lock()

        # Load model eagerly in main thread.
        # Prefer TensorRT engine > PyTorch GPU > ONNX CPU (fallback).
        from ultralytics import YOLO
        import torch
        engine_path = model_name.replace(".pt", ".engine")
        onnx_path = model_name.replace(".pt", ".onnx")
        if os.path.exists(engine_path):
            self._model = YOLO(engine_path, task="detect")
            self._yolo_backend = "TensorRT"
        elif torch.cuda.is_available():
            self._model = YOLO(model_name)
            self._yolo_backend = "PyTorch CUDA"
        elif os.path.exists(onnx_path):
            self._model = YOLO(onnx_path, task="detect")
            self._yolo_backend = "ONNX CPU"
        else:
            self._model = YOLO(model_name)
            self._yolo_backend = "PyTorch CPU"
        self._warmed_up = False

    @property
    def scene_summary(self) -> str:
        """Current scene description (thread-safe read)."""
        with self._scene_lock:
            return self._scene_summary

    @property
    def person_target(self) -> tuple[float, float] | None:
        """Centroid (cx, cy) of the closest person, or None."""
        with self._target_lock:
            return self._person_target

    @property
    def latest_detections(self) -> list[dict]:
        """Latest YOLO detection boxes [{x1,y1,x2,y2,label,conf}, ...]."""
        with self._detection_lock:
            return list(self._latest_detections)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        # Deferred warmup — runs on background thread instead of blocking boot
        if not self._warmed_up:
            t0 = time.monotonic()
            self._model(np.zeros((480, 640, 3), dtype=np.uint8), verbose=False)
            dt = time.monotonic() - t0
            self._warmed_up = True
            print(f"        YOLO warmup: done ({dt:.1f}s, {self._yolo_backend})")
        while not self._stop.is_set():
            frame = self._grab_frame()
            if frame is not None:
                self._detect(self._model, frame)
            self._stop.wait(timeout=self._interval)

    def _grab_frame(self) -> np.ndarray | None:
        """Get latest frame from the shared FrameBuffer (never blocks)."""
        return self._frame_buffer.frame

    def _detect(self, model, frame: np.ndarray) -> None:
        """Run YOLO detection and update scene summary + tracking data."""
        results = model(frame, verbose=False, conf=0.4)

        if not results or len(results[0].boxes) == 0:
            with self._scene_lock:
                self._scene_summary = "Scene is empty — nothing detected."
            with self._detection_lock:
                self._latest_detections = []
            with self._target_lock:
                self._person_target = None
            if self._prev_people_count > 0:
                self._empty_frames += 1
                # Hysteresis: only fire PERSON_LEFT after 3 consecutive
                # empty frames (~1s at 3fps) to avoid flicker
                if self._empty_frames >= 3:
                    self._event_bus.publish("event", {"text": "[everyone left]"})
                    if self._event_queue is not None:
                        self._event_queue.put(Event(EventType.PERSON_LEFT))
                    self._prev_people_count = 0
                    self._empty_frames = 0
            return

        counts: dict[str, int] = {}
        positions: list[str] = []
        detections: list[dict] = []
        person_centroids: list[tuple[float, float, float]] = []
        boxes = results[0].boxes
        h, w = frame.shape[:2]

        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i])
            cls_name = self.TRACKED_CLASSES.get(cls_id)
            if cls_name is None:
                cls_name = results[0].names.get(cls_id, f"object_{cls_id}")
            conf = float(boxes.conf[i])
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()

            counts[cls_name] = counts.get(cls_name, 0) + 1

            # Store normalized box for MJPEG overlay
            detections.append({
                "x1": x1 / w, "y1": y1 / h,
                "x2": x2 / w, "y2": y2 / h,
                "label": cls_name, "conf": conf,
            })

            if cls_id == 0:
                cx = (x1 + x2) / 2 / w
                cy = (y1 + y2) / 2 / h
                size = (x2 - x1) * (y2 - y1) / (w * h)
                pos = "left" if cx < 0.33 else ("right" if cx > 0.67 else "center")
                dist = "close" if size > 0.15 else ("far" if size < 0.03 else "nearby")
                positions.append(f"{dist} {pos}")
                person_centroids.append((cx, cy, size))

        # Store detection boxes for MJPEG overlay
        with self._detection_lock:
            self._latest_detections = detections

        # Track the closest (largest) person for camera centering
        if person_centroids:
            best = max(person_centroids, key=lambda p: p[2])
            with self._target_lock:
                self._person_target = (best[0], best[1])
        else:
            with self._target_lock:
                self._person_target = None

        # Build summary text
        parts = []
        people = counts.pop("person", 0)
        if people:
            if people == 1:
                parts.append(f"1 person ({positions[0]})")
            else:
                parts.append(f"{people} people ({', '.join(positions)})")

        for name, count in sorted(counts.items()):
            if count == 1:
                parts.append(name)
            else:
                parts.append(f"{count} {name}s")

        summary = "Visible: " + ", ".join(parts) + "." if parts else "Scene is empty."

        with self._scene_lock:
            self._scene_summary = summary

        # Publish change events + notify creature event loop
        if people > 0:
            self._empty_frames = 0  # reset hysteresis counter
        if people != self._prev_people_count:
            if people > self._prev_people_count:
                self._event_bus.publish("event", {
                    "text": f"[YOLO: {people} person(s) detected]",
                })
                if self._event_queue is not None:
                    self._event_queue.put(Event(EventType.PERSON_ARRIVED, data=people))
            elif people == 0:
                self._event_bus.publish("event", {"text": "[everyone left]"})
                if self._event_queue is not None:
                    self._event_queue.put(Event(EventType.PERSON_LEFT))
            self._prev_people_count = people

        # Publish detection data for dashboard
        self._event_bus.publish("detections", {
            "summary": summary,
            "people": people,
            "boxes": detections,
        })


# ---------------------------------------------------------------------------
# Creature
# ---------------------------------------------------------------------------

class Creature:
    """The main creature — ties together motor, audio, vision, and LLM."""

    def __init__(
        self,
        device: str | None = None,
        model: str = "llava:7b",
        chat_model: str = "gemma3:4b",
        whisper_model: str = "large-v3",
        use_tts: bool = True,
        audio_device: int | None = None,
        web_port: int = 8950,
        no_dashboard: bool = False,
        wake_word: str | None = "amy",
    ):
        self._event_queue: queue.Queue[Event] = queue.Queue()
        self._cap_lock = threading.Lock()
        self._state = CreatureState.IDLE
        self._last_frame: bytes | None = None
        self.web_port = web_port
        self.no_dashboard = no_dashboard
        self.wake_word = wake_word.lower().strip() if wake_word else None
        self._awake = False  # True after wake word heard, waiting for query
        self._last_person_seen: float = 0.0  # monotonic time
        self._person_greeted = False  # avoid re-greeting same person
        self._person_greet_cooldown: float = 0.0  # prevent re-greeting rapidly
        self._last_spoke: float = 0.0  # when Amy last said something
        self._auto_chat = False  # auto-conversation mode for testing
        self._auto_chat_stop = threading.Event()

        # --- [1/9] Camera + PTZ ---
        print("  [1/9] Camera + PTZ control")
        try:
            from bcc950.native_backend import NativeV4L2Backend, is_available
            if is_available():
                backend = NativeV4L2Backend()
                self.controller = BCC950Controller(device=device, backend=backend)
                print("        Backend: native (C++)")
            else:
                self.controller = BCC950Controller(device=device)
                print("        Backend: subprocess (v4l2-ctl)")
        except ImportError:
            self.controller = BCC950Controller(device=device)
            print("        Backend: subprocess (v4l2-ctl)")
        if device is None:
            found = self.controller.find_camera()
            if found:
                print(f"        Device: {found}")
            else:
                print("        FAILED — could not auto-detect camera")
                print("        Use --device /dev/videoN")
                sys.exit(1)
        else:
            print(f"        Device: {device}")
        self.controller.reset_position()
        time.sleep(0.5)

        self._cap = cv2.VideoCapture(self.controller.device)
        if not self._cap.isOpened():
            print(f"        FAILED — could not open video stream")
            sys.exit(1)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimize latency
        print("        Video stream: OK")
        print("        PTZ motor: OK (motion-verified)")

        verifier = LockedMotionVerifier(self._cap, self._cap_lock)
        self.controller._motion.verifier = verifier

        # Frame buffer — single reader for all consumers
        self._frame_buffer = FrameBuffer(self._cap, self._cap_lock)

        from .motor import MotorThread, idle_scan
        self.motor = MotorThread(self.controller)

        # --- EventBus (needed before YOLO + dashboard) ---
        from .web import EventBus, DashboardServer
        self.event_bus = EventBus()

        # --- Long-term memory ---
        from .memory import Memory
        self.memory = Memory()
        self._memory_save_interval = 60  # save every 60 seconds
        self._last_memory_save: float = 0.0
        if not self.no_dashboard:
            self.dashboard = DashboardServer(self, self.event_bus, port=self.web_port)
        else:
            self.dashboard = None

        # --- [2/9] Speech-to-text (load first, warm up before YOLO) ---
        print(f"  [2/9] Speech-to-text")
        from .listener import Listener
        self.listener = Listener(model_name=whisper_model, audio_device=audio_device)
        # Warm up Whisper with a silent buffer so first real transcription
        # doesn't cause memory allocation conflicts with YOLO.
        _warmup = np.zeros(16000, dtype=np.float32)
        self.listener.transcribe(_warmup)
        print(f"        Model: Whisper {whisper_model}")
        actual_dev = self.listener.audio_device
        print(f"        Audio input: device {actual_dev} ({self.listener.device_rate}Hz)")
        ww_label = f'"{wake_word}"' if wake_word else "disabled"
        print(f"        Wake word: {ww_label}")
        print(f"        Warmup: done")

        # --- [3/9] YOLO object detection (loaded after Whisper warmup) ---
        print("  [3/9] YOLO object detection")
        self.vision_thread = VisionThread(
            self._frame_buffer, self.event_bus,
            event_queue=self._event_queue,
        )
        print(f"        Model: yolo11n ({self.vision_thread._yolo_backend})")
        print("        Role: continuous scene scanning (~3 fps)")
        print("        Tracks: people, animals, objects")

        # --- [4/9] Text-to-speech + pre-cached acknowledgments ---
        print("  [4/9] Text-to-speech")
        from .speaker import Speaker
        self.speaker = Speaker()
        self.use_tts = use_tts and self.speaker.available
        self._ack_wavs: list[bytes] = []
        if self.use_tts:
            print("        Engine: Piper TTS")
            print("        Voice: Amy (en_US)")
            # Pre-cache wake word acknowledgments for instant response
            ack_phrases = ["Yes?", "Hmm?", "I'm here!", "What's up?"]
            for phrase in ack_phrases:
                wav = self.speaker.synthesize_raw(phrase)
                if wav:
                    self._ack_wavs.append(wav)
            if self._ack_wavs:
                print(f"        Pre-cached {len(self._ack_wavs)} acknowledgments")
        else:
            print("        TTS: disabled (text-only mode)")

        # --- [5/9] Sensorium (sensor fusion) ---
        print("  [5/9] Sensorium (sensor fusion)")
        from .sensorium import Sensorium
        self.sensorium = Sensorium()
        print("        Role: temporal awareness, scene narrative")
        print("        Window: 120s sliding window, 30 events max")

        # --- [6/9] Chat model (fast, text-only) ---
        print(f"  [6/9] Chat model (fast)")
        from .agent import Agent, CREATURE_SYSTEM_PROMPT
        self.chat_agent = Agent(
            controller=self.controller,
            model=chat_model,
            system_prompt=CREATURE_SYSTEM_PROMPT,
            use_tools=False,
        )
        print(f"        Model: {chat_model} (Ollama)")
        print(f"        Role: conversation, tool use")
        print(f"        Context: YOLO detections + deep observations")

        # --- [7/9] Deep vision model (background) ---
        print(f"  [7/9] Deep vision model (async)")
        self.deep_model = model
        self._deep_observation: str = ""
        self._deep_lock = threading.Lock()
        print(f"        Model: {model} (Ollama)")
        print(f"        Role: scene understanding (background)")
        print(f"        Runs on: curiosity ticks, clear frames only")

        # --- [8/9] Thinking thread (continuous) ---
        print(f"  [8/9] Thinking thread (continuous)")
        from .thinking import ThinkingThread
        self.thinking = ThinkingThread(self, model=chat_model)
        print(f"        Model: {chat_model} (Ollama)")
        print(f"        Role: inner monologue, Lua-structured decisions")
        print(f"        Interval: {self.thinking._interval}s between thoughts")

        # --- [9/9] Threads ---
        print("  [9/9] Starting subsystem threads")
        self.audio_thread = AudioThread(self.listener, self._event_queue)
        self.curiosity_timer = CuriosityTimer(
            self._event_queue, min_interval=45.0, max_interval=90.0,
        )
        print("        Audio listener: ready")
        print("        Curiosity timer: 45-90s interval")
        print("        Motor programs: idle scan, breathe, nod")

        self._running = False

    # --- Frame capture (thread-safe) ---

    def capture_base64(self) -> str | None:
        """Capture a frame from the FrameBuffer (never blocks)."""
        frame = self._frame_buffer.frame
        if frame is None:
            return None
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode("utf-8")

    # --- MJPEG frame grab (non-blocking) ---

    def grab_mjpeg_frame(self) -> bytes | None:
        """Grab a JPEG frame for the MJPEG stream (never blocks).

        Fast path: if no YOLO detections, return the pre-encoded JPEG
        from FrameBuffer (zero extra encode cost — ~80% of frames).
        Slow path: draw YOLO boxes, encode once.
        """
        if not hasattr(self, "vision_thread") or not self.vision_thread.latest_detections:
            # Fast path: no overlay needed, use pre-encoded JPEG
            jpeg = self._frame_buffer.jpeg
            if jpeg is not None:
                self._last_frame = jpeg
            return self._last_frame
        # Slow path: draw YOLO boxes, encode once
        frame = self._frame_buffer.frame
        if frame is not None:
            frame = self._draw_yolo_overlay(frame)
            _, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
            )
            self._last_frame = buf.tobytes()
        return self._last_frame

    def _draw_yolo_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Draw YOLO bounding boxes + labels on a frame."""
        if not hasattr(self, "vision_thread"):
            return frame
        detections = self.vision_thread.latest_detections
        if not detections:
            return frame
        h, w = frame.shape[:2]
        for det in detections:
            x1 = int(det["x1"] * w)
            y1 = int(det["y1"] * h)
            x2 = int(det["x2"] * w)
            y2 = int(det["y2"] * h)
            label = det["label"]
            conf = det["conf"]
            # Green for person, orange for others
            color = (0, 255, 0) if label == "person" else (0, 180, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, text, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        return frame

    # --- State + event helpers ---

    def _set_state(self, new_state: CreatureState) -> None:
        """Update creature state and publish to dashboard."""
        self._state = new_state
        self.event_bus.publish("state_change", {"state": new_state.value})

    def _publish_position(self) -> None:
        """Read controller position and publish to dashboard."""
        pos = self.controller.position
        self.event_bus.publish("position_update", {
            "pan": pos.pan,
            "tilt": pos.tilt,
            "zoom": pos.zoom,
            "pan_min": pos.pan_min,
            "pan_max": pos.pan_max,
            "tilt_min": pos.tilt_min,
            "tilt_max": pos.tilt_max,
        })

    # --- Wake word ---

    def _check_wake_word(self, transcript: str) -> str | None:
        """Check transcript for wake word. Returns query text or None.

        Supports patterns like:
        - "Hey Amy, what do you see?" → returns "what do you see?"
        - "Amy" alone → sets _awake, waits for follow-up
        - Follow-up while _awake → returns full transcript

        Handles Whisper variations: "Hey, Amy", "hey Amy", "Hey Amie",
        "Hey, Aimee", etc.

        Returns None if no wake word and not awake (ignore this speech).
        """
        if self.wake_word is None:
            return transcript  # no wake word filtering

        lower = transcript.lower().strip()

        # Whisper often mis-transcribes "Amy" — match common variants
        # Also handle punctuation between "hey" and the name
        ww = re.escape(self.wake_word)
        # Match: hey/hi/okay + optional punctuation/space + wake word (or close variants)
        pattern = rf'(?:(?:hey|hi|okay|ok)[,.\s!?]*)?{ww}[,.\s!?]*'
        match = re.search(pattern, lower)

        if match:
            # Extract everything after the wake word
            query = transcript[match.end():].strip()
            if query:
                print(f'  [wake word + query: "{query}"]')
                return query
            else:
                # Just the wake word alone — wait for follow-up
                print("  [wake word detected — listening...]")
                self._awake = True
                self.event_bus.publish("event", {"text": "[listening...]"})
                return None

        if self._awake:
            # Already awake from previous wake word
            print(f'  [follow-up: "{transcript}"]')
            return transcript

        # No wake word, not awake — ignore
        print("  [no wake word — ignoring]")
        return None

    # --- Speech output ---

    def say(self, text: str) -> None:
        """Speak text aloud (or print if TTS disabled)."""
        print(f'  Amy: "{text}"')
        self._last_spoke = time.monotonic()
        self._set_state(CreatureState.SPEAKING)
        self.event_bus.publish("transcript", {"speaker": "amy", "text": text})
        if self.use_tts:
            self.audio_thread.disable()
            try:
                self.speaker.speak_sync(text)
            finally:
                time.sleep(0.2)  # let PortAudio settle before re-enabling
                self.audio_thread.enable()
        self._set_state(CreatureState.IDLE)

    # --- Main loop ---

    def _publish_context(self) -> None:
        """Publish Amy's current evolving context to the dashboard."""
        scene = self.vision_thread.scene_summary if hasattr(self, "vision_thread") else ""
        with self._deep_lock:
            deep_obs = self._deep_observation
        target = self.vision_thread.person_target if hasattr(self, "vision_thread") else None

        # Chat history summary (last 3 exchanges)
        history_preview = []
        for msg in self.chat_agent.history[-6:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                preview = content[:120] + ("..." if len(content) > 120 else "")
                history_preview.append(f"{role}: {preview}")

        # Memory data
        mem_data = self.memory.get_dashboard_data()

        # Sensorium data
        sensorium_narrative = self.sensorium.narrative() if hasattr(self, "sensorium") else ""
        sensorium_summary = self.sensorium.summary() if hasattr(self, "sensorium") else ""
        sensorium_mood = self.sensorium.mood if hasattr(self, "sensorium") else "neutral"
        thinking_suppressed = self.thinking.suppressed if hasattr(self, "thinking") else False

        self.event_bus.publish("context_update", {
            "scene": scene,
            "deep_observation": deep_obs,
            "tracking": f"({target[0]:.2f}, {target[1]:.2f})" if target else "none",
            "state": self._state.value,
            "history_len": len(self.chat_agent.history),
            "history_preview": history_preview,
            "memory": mem_data,
            "auto_chat": self._auto_chat,
            "sensorium_narrative": sensorium_narrative,
            "sensorium_summary": sensorium_summary,
            "mood": sensorium_mood,
            "thinking_suppressed": thinking_suppressed,
        })

        # Periodic memory save
        now = time.monotonic()
        if now - self._last_memory_save > self._memory_save_interval:
            self.memory.save()
            self._last_memory_save = now

    def _default_motor(self):
        """Create the default motor program — auto-track + scan."""
        from .motor import auto_track
        return auto_track(self.controller, lambda: self.vision_thread.person_target)

    def run(self) -> None:
        """Start all threads and run the event loop."""
        from .motor import idle_scan, breathe, track_person, search_scan

        print()
        print("-" * 58)
        print("  All systems go. Bringing Amy online...")
        print("-" * 58)
        print()

        # Start dashboard
        if self.dashboard is not None:
            self.dashboard.start()
            print(f"  Web dashboard: http://localhost:{self.web_port}")

        # Start frame buffer first so video + YOLO have frames
        self._frame_buffer.start()

        # Start threads (YOLO deferred — starts after greeting)
        self.motor.set_program(self._default_motor())
        self.motor.start()
        self.audio_thread.start()
        self.curiosity_timer.start()
        self._running = True

        ww = f'"hey {self.wake_word}"' if self.wake_word else "any speech"
        print(f"  Listening for: {ww}")
        print()
        print("=" * 58)
        print("  Amy is alive. Ctrl+C or say 'goodbye' to stop.")
        print("=" * 58)
        print()

        # Greeting
        self.say("Hello! I'm Amy. I can see you through this camera. I'll be looking around on my own, but say hey Amy anytime to talk to me.")

        # Start YOLO after greeting settles — avoids memory conflicts
        # with Whisper's first real transcription.
        time.sleep(3)
        self.vision_thread.start()
        print("  YOLO detection: running")

        # Start thinking thread after YOLO so sensorium has data
        self.thinking.start()
        print("  Thinking thread: running")

        # Resume scanning after greeting
        self.motor.set_program(self._default_motor())

        listening_since: float | None = None

        try:
            while self._running:
                try:
                    event = self._event_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if event.type == EventType.SHUTDOWN:
                    break

                elif event.type == EventType.SPEECH_DETECTED:
                    # Someone is talking — auto_track already centers on them
                    print("  [speech detected]")
                    self._set_state(CreatureState.LISTENING)
                    listening_since = time.monotonic()

                elif event.type == EventType.TRANSCRIPT_READY:
                    transcript = event.data
                    print(f'  You: "{transcript}"')
                    self.event_bus.publish("transcript", {"speaker": "user", "text": transcript})
                    self.sensorium.push("audio", f'User said: "{transcript[:60]}"', importance=0.8)
                    listening_since = None

                    # Check for exit commands
                    lower = transcript.lower().strip()
                    if any(w in lower for w in ("quit", "exit", "goodbye", "shut down")):
                        self.say("Goodbye! It was nice seeing you.")
                        break

                    # Wake word gate
                    query = self._check_wake_word(transcript)
                    if query is None:
                        # No wake word — ignore, resume scanning
                        self.motor.set_program(self._default_motor())
                        self._set_state(CreatureState.IDLE)
                        continue

                    # === WAKE WORD REFLEX (L2 Instinct — zero LLM) ===

                    # INSTANT: play pre-cached acknowledgment (sub-100ms)
                    if self._ack_wavs:
                        wav = random.choice(self._ack_wavs)
                        self.audio_thread.disable()
                        self.speaker.play_raw(wav, rate=self.speaker.sample_rate)
                        self.audio_thread.enable()

                    # REFLEX: find the speaker
                    target = self.vision_thread.person_target
                    if target is None:
                        # Can't see anyone — search
                        from .motor import search_scan
                        self.motor.set_program(search_scan(self.controller))
                        # Wait briefly for YOLO to find someone
                        for _ in range(10):  # ~3 seconds at 0.3s per check
                            time.sleep(0.3)
                            target = self.vision_thread.person_target
                            if target is not None:
                                break
                        if target is None:
                            self.say("Who's there? I can hear you but I can't see you.")

                    # RESPOND: fast LLM with sensorium context
                    self._respond(transcript=query)
                    self._awake = False

                    # Resume scanning
                    self.motor.set_program(self._default_motor())
                    self._set_state(CreatureState.IDLE)
                    self._publish_position()

                elif event.type == EventType.SILENCE:
                    self.sensorium.push("audio", "Silence")
                    # If we were listening and it's been quiet, go back to scanning
                    if listening_since and (time.monotonic() - listening_since) > 4.0:
                        print("  [silence — resuming scan]")
                        self.motor.set_program(self._default_motor())
                        self._set_state(CreatureState.IDLE)
                        self._awake = False
                        listening_since = None

                elif event.type == EventType.PERSON_ARRIVED:
                    people = event.data
                    self._last_person_seen = time.monotonic()
                    # auto_track already centers on them
                    self.sensorium.push("yolo", f"{people} person(s) appeared", importance=0.8)
                    self.memory.add_event("person_arrived", f"{people} person(s) detected")
                    # Greeting cooldown: don't re-greet within 60 seconds
                    now = time.monotonic()
                    if (now - self._person_greet_cooldown) > 60:
                        print(f"  [YOLO: {people} person(s) — greeting]")
                        self._person_greeted = True
                        self._person_greet_cooldown = now
                        scene = self.vision_thread.scene_summary
                        with self._deep_lock:
                            deep_obs = self._deep_observation
                        ctx = scene
                        if deep_obs:
                            ctx += f"\n[Recent observation]: {deep_obs}"
                        ctx += "\n[A person just appeared in your view. Greet them warmly but briefly.]"
                        response = self.chat_agent.process_turn(
                            transcript=None,
                            scene_context=ctx,
                        )
                        if response and response.strip().strip(".") != "":
                            self.say(response)

                elif event.type == EventType.PERSON_LEFT:
                    print("  [YOLO: everyone left]")
                    self.sensorium.push("yolo", "Everyone left", importance=0.7)
                    # Don't reset _person_greeted immediately — the cooldown
                    # timer handles re-greeting appropriately.
                    self.memory.add_event("person_left", "Everyone left the scene")

                elif event.type == EventType.CURIOSITY_TICK:
                    print("  [curiosity tick — deep think]")
                    self.event_bus.publish("event", {"text": "[curiosity tick]"})
                    self._deep_think()
                    self._publish_position()
                    self._publish_context()

        except KeyboardInterrupt:
            print("\n\nInterrupted.")
        finally:
            self.shutdown()

    def _respond(self, transcript: str) -> None:
        """Fast chat response — text-only model with YOLO + deep obs context."""
        self._set_state(CreatureState.THINKING)
        # Suppress thinking thread during conversation
        self.thinking.suppress(15)
        # auto_track keeps us centered on the person while thinking

        # Build scene context from YOLO + accumulated deep observations
        scene = self.vision_thread.scene_summary
        with self._deep_lock:
            deep_obs = self._deep_observation

        scene_ctx = scene
        if deep_obs:
            scene_ctx += f"\n[Recent observation]: {deep_obs}"

        # Add sensorium narrative for temporal context
        narrative = self.sensorium.narrative()
        if narrative and narrative != "No recent observations.":
            scene_ctx += f"\n[Recent awareness]:\n{narrative}"

        # Add long-term memory context
        pos = self.controller.position
        mem_ctx = self.memory.build_context(pan=pos.pan, tilt=pos.tilt)
        if mem_ctx:
            scene_ctx += f"\n{mem_ctx}"

        print(f"  [responding ({self.chat_agent.model})]...")
        print(f"  [scene: {scene}]")

        response = self.chat_agent.process_turn(
            transcript=transcript,
            scene_context=scene_ctx,
        )

        # Log conversation to memory and sensorium
        self.memory.add_event("conversation", f"User: {transcript} → Amy: {response[:80]}")
        self.sensorium.push("audio", f'Amy said: "{response[:60]}"')

        # Publish context state to dashboard
        self._publish_context()

        self.say(response)

    def _deep_think(self) -> None:
        """Background deep thinking — vision model analyzes the scene.

        Runs the deep model on a camera frame in a background thread so
        the main event loop stays responsive.  The observation gets stored
        as context for future chat responses.
        """
        # Don't stack up deep thinks
        if hasattr(self, '_deep_thread') and self._deep_thread.is_alive():
            print("  [deep think already running — skipping]")
            return

        self._deep_thread = threading.Thread(target=self._deep_think_worker, daemon=True)
        self._deep_thread.start()

    @staticmethod
    def _frame_sharpness(frame: np.ndarray) -> float:
        """Measure frame sharpness using Laplacian variance.

        Higher = sharper.  Typical values: <50 = blurry (camera moving),
        >100 = acceptably sharp.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def _capture_clear_frame(self, min_sharpness: float = 50.0, max_tries: int = 5) -> str | None:
        """Capture a frame that isn't motion-blurred.

        Tries up to ``max_tries`` times, waiting briefly between attempts
        for the camera to settle.  Returns base64 JPEG or None.
        """
        for attempt in range(max_tries):
            frame = self._frame_buffer.frame
            if frame is None:
                time.sleep(0.2)
                continue
            sharpness = self._frame_sharpness(frame)
            if sharpness >= min_sharpness:
                _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return base64.b64encode(buffer).decode("utf-8")
            if attempt < max_tries - 1:
                time.sleep(0.3)  # wait for camera to settle
        # Fallback: use whatever we have
        frame = self._frame_buffer.frame
        if frame is None:
            return None
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode("utf-8")

    def _deep_think_worker(self) -> None:
        """Worker for background deep thinking."""
        from .vision import ollama_chat

        print(f"  [deep think ({self.deep_model})]...")
        image_b64 = self._capture_clear_frame()
        if image_b64 is None:
            return

        scene = self.vision_thread.scene_summary

        try:
            response = ollama_chat(
                model=self.deep_model,
                messages=[
                    {"role": "system", "content": (
                        "You are observing a scene through a camera. "
                        "Describe what you see briefly (1-2 sentences). "
                        "Focus on people, activity, mood, and anything noteworthy. "
                        "If nothing interesting, say '...'"
                    )},
                    {"role": "user", "content": f"[YOLO detections]: {scene}\n[Camera frame attached]",
                     "images": [image_b64]},
                ],
            )
            observation = response.get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"  [deep think error: {e}]")
            return

        if observation and observation.strip(".") != "":
            with self._deep_lock:
                self._deep_observation = observation
            self.sensorium.push("deep", observation[:100], importance=0.7)
            print(f'  [deep observation]: "{observation}"')
            self.event_bus.publish("event", {"text": f"[deep]: {observation}"})

            # Store in long-term spatial memory
            pos = self.controller.position
            self.memory.add_observation(pos.pan, pos.tilt, observation)
            self.memory.add_event("observation", observation[:100])

            # Every 5th observation, update the room summary
            total_obs = sum(len(v) for v in self.memory.spatial.values())
            if total_obs > 0 and total_obs % 5 == 0:
                self._update_room_summary()

            # Speak if idle and haven't spoken recently (10s cooldown)
            idle = self._state == CreatureState.IDLE
            quiet_long_enough = (time.monotonic() - self._last_spoke) > 10
            if idle and quiet_long_enough:
                scene_ctx = f"{scene}\n[You just noticed]: {observation}"
                scene_ctx += "\n[Share a brief, natural observation about what you see. 1 sentence max.]"
                comment = self.chat_agent.process_turn(
                    transcript=None,
                    scene_context=scene_ctx,
                )
                if comment and comment.strip().strip(".") != "":
                    self.say(comment)
        else:
            print("  [deep think: nothing noteworthy]")

    # --- Room understanding ---

    def _update_room_summary(self) -> None:
        """Use the LLM to build an evolving understanding of the room."""
        spatial_data = self.memory.get_spatial_summary()
        if not spatial_data:
            return
        old_summary = self.memory.room_summary

        prompt = (
            "Based on these camera observations from different angles, "
            "write a brief (2-3 sentence) summary of the room and what's in it. "
            "Merge with any existing knowledge.\n\n"
            f"Previous understanding: {old_summary or 'None yet'}\n\n"
            f"Observations:\n{spatial_data}"
        )

        from .vision import ollama_chat
        try:
            response = ollama_chat(
                model=self.chat_agent.model,
                messages=[
                    {"role": "system", "content": "You summarize room observations into a concise description."},
                    {"role": "user", "content": prompt},
                ],
            )
            summary = response.get("message", {}).get("content", "").strip()
            if summary:
                self.memory.update_room_summary(summary)
                print(f"  [room summary updated]: {summary[:80]}...")
                self.event_bus.publish("event", {"text": f"[room]: {summary[:80]}..."})
        except Exception as e:
            print(f"  [room summary error: {e}]")

    # --- Auto-chat mode (testing) ---

    def toggle_auto_chat(self) -> bool:
        """Toggle auto-conversation mode. Returns new state."""
        self._auto_chat = not self._auto_chat
        if self._auto_chat:
            self._auto_chat_stop.clear()
            t = threading.Thread(target=self._auto_chat_loop, daemon=True)
            t.start()
            print("  [auto-chat: ON]")
            self.event_bus.publish("event", {"text": "[auto-chat enabled]"})
        else:
            self._auto_chat_stop.set()
            print("  [auto-chat: OFF]")
            self.event_bus.publish("event", {"text": "[auto-chat disabled]"})
        return self._auto_chat

    def _auto_chat_loop(self) -> None:
        """Background loop: an imaginary friend talks to Amy.

        Generates friend speech with Piper (pitch-shifted), plays it out loud,
        then feeds the audio directly to Whisper to verify STT works.
        Amy responds to whatever Whisper transcribes.
        """
        from .vision import ollama_chat

        friend_history: list[dict] = [
            {"role": "system", "content": (
                "You are a person having a casual conversation with Amy, an AI "
                "creature living in a camera. You are curious about what she sees "
                "and thinks. Keep responses to 1 sentence. Always start with "
                "'Hey Amy' to trigger her wake word. Be friendly and curious."
            )},
        ]

        self._auto_chat_stop.wait(timeout=5)

        while not self._auto_chat_stop.is_set():
            try:
                # Generate friend's message
                friend_prompt = "[Say something to Amy. Start with 'Hey Amy'.]"
                if self._deep_observation:
                    friend_prompt = (
                        f"[Amy recently observed: {self._deep_observation}. "
                        f"Ask her about it. Start with 'Hey Amy'.]"
                    )

                friend_history.append({"role": "user", "content": friend_prompt})
                response = ollama_chat(
                    model=self.chat_agent.model,
                    messages=friend_history,
                )
                friend_text = response.get("message", {}).get("content", "").strip()
                if not friend_text:
                    friend_text = "Hey Amy, what can you see right now?"

                # Ensure it starts with Hey Amy
                lower = friend_text.lower()
                if "amy" not in lower:
                    friend_text = "Hey Amy, " + friend_text

                friend_history.append({"role": "assistant", "content": friend_text})
                if len(friend_history) > 15:
                    friend_history = [friend_history[0]] + friend_history[-10:]

                print(f'  Friend: "{friend_text}"')
                self.event_bus.publish("transcript", {
                    "speaker": "friend", "text": friend_text,
                })

                # Synthesize, play, and feed to Whisper
                whisper_text = self._speak_and_transcribe_friend(friend_text)

                if self._auto_chat_stop.is_set():
                    break

                if whisper_text:
                    print(f'  [STT heard]: "{whisper_text}"')
                    self.event_bus.publish("event", {
                        "text": f"[STT]: {whisper_text}",
                    })
                    # Feed through the normal wake word + response pipeline
                    query = self._check_wake_word(whisper_text)
                    if query:
                        self._respond(transcript=query)
                    else:
                        # Wake word not detected — respond to original text
                        print("  [auto-chat: wake word missed, using original text]")
                        self.event_bus.publish("event", {
                            "text": "[STT missed wake word — using original text]",
                        })
                        self._respond(transcript=friend_text)
                else:
                    # Whisper returned nothing — use original text
                    print("  [auto-chat: STT returned nothing, using original text]")
                    self._respond(transcript=friend_text)

                delay = random.uniform(10, 20)
                if self._auto_chat_stop.wait(timeout=delay):
                    break

            except Exception as e:
                print(f"  [auto-chat error: {e}]")
                self._auto_chat_stop.wait(timeout=10)

    def _speak_and_transcribe_friend(self, text: str) -> str | None:
        """Synthesize friend speech with Piper, play it, and feed to Whisper.

        Returns the Whisper transcription of the audio (tests STT pipeline).
        Uses aplay for playback to avoid sounddevice conflicts.
        """
        import subprocess

        if not self.speaker.available:
            return None

        try:
            # Synthesize with Piper (slightly faster = different voice)
            proc = subprocess.run(
                [self.speaker.piper_bin, "--model", self.speaker.voice_model,
                 "--output-raw", "--length-scale", "0.85"],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0 or not proc.stdout:
                return None

            raw_audio = proc.stdout

            # Play through speakers via aplay (no sounddevice conflict)
            self.audio_thread.disable()
            try:
                self.speaker.play_raw(raw_audio, rate=self.speaker.sample_rate)
            finally:
                time.sleep(0.2)
                self.audio_thread.enable()

            # Parse audio and resample to 16kHz for Whisper
            audio_22k = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
            from scipy.signal import resample
            target_len = int(len(audio_22k) * 16000 / self.speaker.sample_rate)
            audio_16k = resample(audio_22k, target_len).astype(np.float32)

            # Feed to Whisper (test the STT pipeline)
            transcription = self.listener.transcribe(audio_16k)
            return transcription if transcription else None

        except Exception as e:
            print(f"  [friend TTS/STT error: {e}]")
            return None

    def shutdown(self) -> None:
        """Clean up all threads and resources."""
        print("Shutting down...")
        self._running = False
        self._auto_chat_stop.set()
        self.thinking.stop()
        self.memory.add_event("shutdown", "Amy shutting down")
        self.memory.save()
        print("  [memory saved]")
        if self.dashboard is not None:
            self.dashboard.stop()
        self.vision_thread.stop()
        self.curiosity_timer.stop()
        self.audio_thread.stop()
        self.motor.stop()
        self._frame_buffer.stop()
        self.controller.stop()
        self.speaker.shutdown()
        if self._cap is not None:
            self._cap.release()
        print("Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Amy: an autonomous embodied AI creature in a BCC950 camera"
    )
    parser.add_argument("--device", default=None, help="V4L2 device path (auto-detect if omitted)")
    parser.add_argument("--model", default="llava:7b", help="Deep vision model for background scene analysis (default: llava:7b)")
    parser.add_argument("--chat-model", default="gemma3:4b", help="Fast chat model for conversation (default: gemma3:4b)")
    parser.add_argument("--whisper-model", default="large-v3", help="Whisper model (default: large-v3)")
    parser.add_argument("--no-tts", action="store_true", help="Disable TTS (text-only output)")
    parser.add_argument("--audio-device", type=int, default=None, help="Audio input device index")
    parser.add_argument("--port", type=int, default=8950, help="Web dashboard port (default: 8950)")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable web dashboard")
    parser.add_argument("--wake-word", default="amy", help="Wake word (default: 'amy')")
    parser.add_argument("--no-wake-word", action="store_true", help="Respond to all speech (no wake word)")
    args = parser.parse_args()

    print()
    print("=" * 58)
    print("       Amy — Embodied AI Creature")
    print("       Logitech BCC950 ConferenceCam")
    print("=" * 58)
    print()
    print("  Booting subsystems...")
    print()

    creature = Creature(
        device=args.device,
        model=args.model,
        chat_model=args.chat_model,
        whisper_model=args.whisper_model,
        use_tts=not args.no_tts,
        audio_device=args.audio_device,
        web_port=args.port,
        no_dashboard=args.no_dashboard,
        wake_word=None if args.no_wake_word else args.wake_word,
    )
    creature.run()


if __name__ == "__main__":
    main()
