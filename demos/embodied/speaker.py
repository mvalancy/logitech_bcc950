"""Piper TTS output for the embodied AI demo."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import queue

import numpy as np
import sounddevice as sd

DEFAULT_PIPER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models", "piper")
DEFAULT_PIPER_BIN = os.path.join(DEFAULT_PIPER_DIR, "piper")
DEFAULT_VOICE_MODEL = os.path.join(DEFAULT_PIPER_DIR, "en_US-amy-medium.onnx")


class Speaker:
    """Text-to-speech using Piper with queued playback."""

    def __init__(
        self,
        piper_bin: str = DEFAULT_PIPER_BIN,
        voice_model: str = DEFAULT_VOICE_MODEL,
        sample_rate: int = 22050,
    ):
        self.piper_bin = os.path.abspath(piper_bin)
        self.voice_model = os.path.abspath(voice_model)
        self.sample_rate = sample_rate
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    @property
    def available(self) -> bool:
        return os.path.isfile(self.piper_bin) and os.path.isfile(self.voice_model)

    def speak(self, text: str) -> None:
        """Queue text for speech. Non-blocking."""
        self._queue.put(text)

    def speak_sync(self, text: str) -> None:
        """Speak text synchronously (blocks until done)."""
        self._synthesize_and_play(text)

    def shutdown(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)

    def _worker(self) -> None:
        while True:
            text = self._queue.get()
            if text is None:
                break
            self._synthesize_and_play(text)

    def _synthesize_and_play(self, text: str) -> None:
        if not self.available:
            print(f'  [TTS unavailable] "{text}"')
            return

        try:
            proc = subprocess.run(
                [self.piper_bin, "--model", self.voice_model, "--output-raw"],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                print(f"  [TTS error] {proc.stderr.decode()[:200]}")
                return

            raw_audio = proc.stdout
            if not raw_audio:
                return

            audio_array = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(audio_array, samplerate=self.sample_rate)
            sd.wait()
        except subprocess.TimeoutExpired:
            print("  [TTS timeout]")
        except Exception as e:
            print(f"  [TTS error] {e}")
