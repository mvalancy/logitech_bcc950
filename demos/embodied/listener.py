"""Audio recording + Whisper speech-to-text for the embodied AI demo."""

from __future__ import annotations

import numpy as np
import sounddevice as sd
import whisper

SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.01


class Listener:
    """Records audio from a microphone and transcribes it with Whisper."""

    def __init__(self, model_name: str = "large-v3", audio_device: int | None = None):
        self.audio_device = audio_device
        self.sample_rate = SAMPLE_RATE
        print(f"  Loading Whisper model '{model_name}'...")
        self.model = whisper.load_model(model_name)
        print(f"  Whisper '{model_name}' loaded.")

    def record(self, duration: float = 4.0) -> np.ndarray:
        """Record audio from the microphone."""
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.audio_device,
        )
        sd.wait()
        return audio.flatten()

    def is_silence(self, audio: np.ndarray) -> bool:
        """Check if the audio is near-silent."""
        return float(np.max(np.abs(audio))) < SILENCE_THRESHOLD

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text using Whisper."""
        result = self.model.transcribe(audio, fp16=False, language="en")
        return result.get("text", "").strip()

    def listen(self, duration: float = 4.0) -> str | None:
        """Record and transcribe. Returns None if silence."""
        audio = self.record(duration)
        if self.is_silence(audio):
            return None
        text = self.transcribe(audio)
        return text if text else None
