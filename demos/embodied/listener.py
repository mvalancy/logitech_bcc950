"""Audio recording + Whisper speech-to-text for the embodied AI demo.

Records at the device's native sample rate and resamples to 16kHz
for Whisper, since not all devices support 16kHz directly (e.g. the
BCC950 ConferenceCam mic runs at 44100Hz).
"""

from __future__ import annotations

import re

import numpy as np
import sounddevice as sd
import whisper

WHISPER_RATE = 16000
SILENCE_PEAK_THRESHOLD = 0.015  # peak amplitude
SILENCE_RMS_THRESHOLD = 0.004   # RMS energy


def find_bcc950_mic() -> int | None:
    """Auto-detect the BCC950 ConferenceCam microphone by name.

    Device indices change between reboots, so we search by name.
    Returns the device index, or None if not found.
    """
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and "BCC950" in dev.get("name", ""):
            return i
    return None


class Listener:
    """Records audio from a microphone and transcribes it with Whisper.

    Records at the device's native sample rate and resamples to 16kHz
    for Whisper compatibility.
    """

    def __init__(self, model_name: str = "large-v3", audio_device: int | None = None):
        # Auto-detect BCC950 mic if no device specified
        if audio_device is None:
            audio_device = find_bcc950_mic()
            if audio_device is not None:
                print(f"  Auto-detected BCC950 mic at device {audio_device}")
            else:
                print("  WARNING: BCC950 mic not found, using default device")
        self.audio_device = audio_device

        # Determine the device's native sample rate
        if audio_device is not None:
            dev_info = sd.query_devices(audio_device)
            self.device_rate = int(dev_info["default_samplerate"])
        else:
            self.device_rate = WHISPER_RATE
        self.whisper_rate = WHISPER_RATE
        self._needs_resample = self.device_rate != WHISPER_RATE

        print(f"  Loading Whisper model '{model_name}'...")
        self.model = whisper.load_model(model_name)
        print(f"  Whisper '{model_name}' loaded.")

    def record(self, duration: float = 4.0) -> np.ndarray:
        """Record audio from the microphone at native rate, resample to 16kHz."""
        samples = int(duration * self.device_rate)
        audio = sd.rec(
            samples,
            samplerate=self.device_rate,
            channels=1,
            dtype="float32",
            device=self.audio_device,
        )
        sd.wait()
        audio = audio.flatten()

        if self._needs_resample:
            # Resample from device rate to 16kHz for Whisper
            target_len = int(len(audio) * self.whisper_rate / self.device_rate)
            # Simple linear interpolation (fast, good enough for speech)
            indices = np.linspace(0, len(audio) - 1, target_len)
            audio = np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

        return audio

    def is_silence(self, audio: np.ndarray) -> bool:
        """Check if the audio is near-silent using both peak and RMS energy."""
        peak = float(np.max(np.abs(audio)))
        if peak < SILENCE_PEAK_THRESHOLD:
            return True
        # Use float64 to avoid overflow warnings
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        return rms < SILENCE_RMS_THRESHOLD

    # --- Hallucination filtering ---
    # Whisper hallucinates these phrases on near-silence / background noise.

    HALLUCINATIONS = {
        "thank you", "thank you.", "thanks for watching",
        "thank you for watching", "thank you for watching!",
        "thanks for watching!", "thank you so much",
        "thank you so much for watching",
        "you", "bye", "bye.", "the end", "the end.",
        "subscribe", "like and subscribe",
        "...", "\u2026",
    }

    HALLUCINATION_PATTERNS = [
        re.compile(r"welcome to (my|our|the) channel", re.I),
        re.compile(r"today (i|we) will (show|teach|make|learn)", re.I),
        re.compile(r"(delicious|simple|easy).{0,30}recipe", re.I),
        re.compile(r"(like|hit).{0,15}subscribe", re.I),
        re.compile(r"don'?t forget to", re.I),
        re.compile(r"see you (in the |in |next )", re.I),
        re.compile(r"please (subscribe|like|share|comment)", re.I),
        re.compile(r"chicken (breast|with)", re.I),
        re.compile(r"(this|the|my) video", re.I),
        re.compile(r"links? (in |below)", re.I),
        re.compile(r"in the description", re.I),
    ]

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text using Whisper with hallucination filtering.

        Uses segment-level confidence metrics to reject low-quality
        transcriptions that are almost certainly hallucinations.
        """
        result = self.model.transcribe(
            audio,
            fp16=False,
            language="en",
            condition_on_previous_text=False,  # prevents hallucination cascading
        )
        text = result.get("text", "").strip()
        if not text:
            return ""

        # Exact match hallucination filter
        if text.lower().rstrip(".!?,") in self.HALLUCINATIONS:
            print(f"  [STT filtered (hallucination): {text!r}]")
            return ""

        # Pattern-based hallucination filter
        for pat in self.HALLUCINATION_PATTERNS:
            if pat.search(text):
                print(f"  [STT filtered (pattern): {text!r}]")
                return ""

        # Segment-level confidence checks (match Whisper's own defaults)
        segments = result.get("segments", [])
        if segments:
            avg_no_speech = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
            avg_logprob = sum(s.get("avg_logprob", 0) for s in segments) / len(segments)
            # High no_speech_prob = Whisper thinks it's silence
            if avg_no_speech > 0.6:
                print(f"  [STT filtered (no_speech={avg_no_speech:.2f}): {text!r}]")
                return ""
            # Very low avg_logprob = low confidence output
            if avg_logprob < -1.0:
                print(f"  [STT filtered (logprob={avg_logprob:.2f}): {text!r}]")
                return ""

        return text

    def listen(self, duration: float = 4.0) -> str | None:
        """Record and transcribe. Returns None if silence."""
        audio = self.record(duration)
        if self.is_silence(audio):
            return None
        text = self.transcribe(audio)
        return text if text else None
