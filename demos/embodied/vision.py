"""Camera frame capture + Ollama vision for the embodied AI demo."""

from __future__ import annotations

import base64
import json
import urllib.request

import cv2
import numpy as np


class Vision:
    """Captures frames from the BCC950 camera and sends them to Ollama for analysis."""

    def __init__(self, device: str = "/dev/video0"):
        self.device = device
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        """Open the camera. Returns True if successful."""
        self._cap = cv2.VideoCapture(self.device)
        return self._cap.isOpened()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def capture_frame(self) -> np.ndarray | None:
        """Capture a single frame. Returns None on failure."""
        if self._cap is None or not self._cap.isOpened():
            return None
        ret, frame = self._cap.read()
        return frame if ret else None

    def frame_to_base64(self, frame: np.ndarray) -> str:
        """Encode a frame as base64 JPEG for the Ollama multimodal API."""
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode("utf-8")

    def capture_base64(self) -> str | None:
        """Capture a frame and return as base64 string."""
        frame = self.capture_frame()
        if frame is None:
            return None
        return self.frame_to_base64(frame)


def ollama_chat(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    base_url: str = "http://localhost:11434",
) -> dict:
    """Call Ollama's chat API with optional tools and images."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))
