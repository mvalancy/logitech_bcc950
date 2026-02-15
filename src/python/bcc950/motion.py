"""Motion primitives for BCC950 pan/tilt/zoom control."""

from __future__ import annotations

import threading
import time

from .constants import (
    CTRL_PAN_SPEED,
    CTRL_TILT_SPEED,
    CTRL_ZOOM_ABSOLUTE,
    DEFAULT_MOVE_DURATION,
    ZOOM_MAX,
    ZOOM_MIN,
)
from .position import PositionTracker
from .v4l2_backend import V4L2Backend


class MotionController:
    """Thread-safe motion control for the BCC950.

    All movement methods acquire a mutex so that start-sleep-stop
    sequences are atomic.
    """

    def __init__(
        self,
        backend: V4L2Backend,
        device: str,
        position: PositionTracker | None = None,
    ):
        self._backend = backend
        self._device = device
        self._lock = threading.Lock()
        self.position = position or PositionTracker()

    def pan(self, direction: int, duration: float = DEFAULT_MOVE_DURATION) -> None:
        """Pan camera. direction: -1 (left) or 1 (right)."""
        speed = max(-1, min(1, direction))
        with self._lock:
            self._backend.set_control(self._device, CTRL_PAN_SPEED, speed)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_PAN_SPEED, 0)
            self.position.update_pan(speed, duration)

    def tilt(self, direction: int, duration: float = DEFAULT_MOVE_DURATION) -> None:
        """Tilt camera. direction: 1 (up) or -1 (down)."""
        speed = max(-1, min(1, direction))
        with self._lock:
            self._backend.set_control(self._device, CTRL_TILT_SPEED, speed)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, 0)
            self.position.update_tilt(speed, duration)

    def combined_move(
        self,
        pan_dir: int,
        tilt_dir: int,
        duration: float = DEFAULT_MOVE_DURATION,
    ) -> None:
        """Simultaneous pan + tilt."""
        pan_speed = max(-1, min(1, pan_dir))
        tilt_speed = max(-1, min(1, tilt_dir))
        with self._lock:
            self._backend.set_control(self._device, CTRL_PAN_SPEED, pan_speed)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, tilt_speed)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_PAN_SPEED, 0)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, 0)
            self.position.update_pan(pan_speed, duration)
            self.position.update_tilt(tilt_speed, duration)

    def combined_move_with_zoom(
        self,
        pan_dir: int,
        tilt_dir: int,
        zoom_target: int,
        duration: float = DEFAULT_MOVE_DURATION,
    ) -> None:
        """Simultaneous pan + tilt + zoom to target."""
        pan_speed = max(-1, min(1, pan_dir))
        tilt_speed = max(-1, min(1, tilt_dir))
        zoom_target = max(ZOOM_MIN, min(ZOOM_MAX, zoom_target))
        with self._lock:
            self._backend.set_control(self._device, CTRL_PAN_SPEED, pan_speed)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, tilt_speed)
            self._backend.set_control(self._device, CTRL_ZOOM_ABSOLUTE, zoom_target)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_PAN_SPEED, 0)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, 0)
            self.position.update_pan(pan_speed, duration)
            self.position.update_tilt(tilt_speed, duration)
            self.position.update_zoom(zoom_target)

    def zoom_absolute(self, value: int) -> None:
        """Set zoom to an absolute value (clamped to ZOOM_MIN..ZOOM_MAX)."""
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        with self._lock:
            self._backend.set_control(self._device, CTRL_ZOOM_ABSOLUTE, value)
            self.position.update_zoom(value)

    def zoom_relative(self, delta: int) -> None:
        """Adjust zoom by a relative delta from current position."""
        with self._lock:
            new_value = max(ZOOM_MIN, min(ZOOM_MAX, self.position.zoom + delta))
            self._backend.set_control(self._device, CTRL_ZOOM_ABSOLUTE, new_value)
            self.position.update_zoom(new_value)

    def stop(self) -> None:
        """Stop all movement."""
        with self._lock:
            self._backend.set_control(self._device, CTRL_PAN_SPEED, 0)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, 0)
