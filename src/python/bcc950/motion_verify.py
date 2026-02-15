"""Motion verification using frame comparison.

Answers the question: 'did the camera actually move?' after a command.
Uses phase correlation to detect global image shift between frames
captured before and after a move. A short move (0.3s) produces a
moderate pixel shift that phase correlation handles well.
"""

from __future__ import annotations

import cv2
import numpy as np


class MotionVerifier:
    """Verify camera movement by comparing frames before/after a move.

    Parameters
    ----------
    cap : cv2.VideoCapture
        Open video capture on the camera device.
    shift_threshold : float
        Minimum pixel shift to consider the camera as having moved.
    """

    def __init__(self, cap: cv2.VideoCapture, shift_threshold: float = 3.0):
        self._cap = cap
        self.shift_threshold = shift_threshold

    def grab_gray(self) -> np.ndarray:
        """Capture a fresh grayscale frame, flushing stale buffer."""
        for _ in range(3):
            self._cap.read()
        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise RuntimeError("Failed to capture frame")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def grab_frame(self) -> np.ndarray:
        """Capture a fresh color frame."""
        for _ in range(3):
            self._cap.read()
        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise RuntimeError("Failed to capture frame")
        return frame

    def did_move(self, before: np.ndarray, after: np.ndarray) -> bool:
        """Check if the camera moved between two grayscale frames."""
        dx, dy = self.measure_shift(before, after)
        return abs(dx) > self.shift_threshold or abs(dy) > self.shift_threshold

    def did_pan(self, before: np.ndarray, after: np.ndarray) -> bool:
        """Check if horizontal (pan) movement occurred."""
        dx, _ = self.measure_shift(before, after)
        return abs(dx) > self.shift_threshold

    def did_tilt(self, before: np.ndarray, after: np.ndarray) -> bool:
        """Check if vertical (tilt) movement occurred."""
        _, dy = self.measure_shift(before, after)
        return abs(dy) > self.shift_threshold

    @staticmethod
    def measure_shift(prev_gray: np.ndarray, curr_gray: np.ndarray) -> tuple[float, float]:
        """Measure global frame shift (dx, dy) using phase correlation.

        Returns (dx, dy) in pixels. Positive dx = image shifted right
        (camera panned left), positive dy = image shifted down (camera
        tilted up).
        """
        prev_f = prev_gray.astype(np.float64)
        curr_f = curr_gray.astype(np.float64)

        h, w = prev_gray.shape
        window = np.outer(np.hanning(h), np.hanning(w))
        prev_f *= window
        curr_f *= window

        (dx, dy), _ = cv2.phaseCorrelate(prev_f, curr_f)
        return dx, dy
