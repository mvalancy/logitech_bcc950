"""Motion primitives for BCC950 pan/tilt/zoom control."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from .motion_verify import MotionVerifier


class MotionController:
    """Thread-safe motion control for the BCC950.

    All movement methods acquire a mutex so that start-sleep-stop
    sequences are atomic.  When a *verifier* is provided, frame
    comparison is used to detect whether the camera actually moved,
    enabling automatic limit discovery.
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
        self.verifier: MotionVerifier | None = None

    def pan(
        self,
        direction: int,
        duration: float = DEFAULT_MOVE_DURATION,
        verifier: MotionVerifier | None = None,
    ) -> bool:
        """Pan camera. direction: -1 (left) or 1 (right).

        Returns True if the camera actually moved (or if no verifier).
        """
        speed = max(-1, min(1, direction))
        v = verifier or self.verifier
        with self._lock:
            before = v.grab_gray() if v else None
            self._backend.set_control(self._device, CTRL_PAN_SPEED, speed)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_PAN_SPEED, 0)
            moved = True
            if v and before is not None:
                after = v.grab_gray()
                moved = v.did_pan(before, after)
            self.position.update_pan(speed, duration, moved)
            return moved

    def tilt(
        self,
        direction: int,
        duration: float = DEFAULT_MOVE_DURATION,
        verifier: MotionVerifier | None = None,
    ) -> bool:
        """Tilt camera. direction: 1 (up) or -1 (down).

        Returns True if the camera actually moved (or if no verifier).
        """
        speed = max(-1, min(1, direction))
        v = verifier or self.verifier
        with self._lock:
            before = v.grab_gray() if v else None
            self._backend.set_control(self._device, CTRL_TILT_SPEED, speed)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, 0)
            moved = True
            if v and before is not None:
                after = v.grab_gray()
                moved = v.did_tilt(before, after)
            self.position.update_tilt(speed, duration, moved)
            return moved

    def combined_move(
        self,
        pan_dir: int,
        tilt_dir: int,
        duration: float = DEFAULT_MOVE_DURATION,
        verifier: MotionVerifier | None = None,
    ) -> tuple[bool, bool]:
        """Simultaneous pan + tilt.

        Returns (pan_moved, tilt_moved).
        """
        pan_speed = max(-1, min(1, pan_dir))
        tilt_speed = max(-1, min(1, tilt_dir))
        v = verifier or self.verifier
        with self._lock:
            before = v.grab_gray() if v else None
            self._backend.set_control(self._device, CTRL_PAN_SPEED, pan_speed)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, tilt_speed)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_PAN_SPEED, 0)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, 0)
            pan_moved = True
            tilt_moved = True
            if v and before is not None:
                after = v.grab_gray()
                pan_moved = v.did_pan(before, after)
                tilt_moved = v.did_tilt(before, after)
            self.position.update_pan(pan_speed, duration, pan_moved)
            self.position.update_tilt(tilt_speed, duration, tilt_moved)
            return pan_moved, tilt_moved

    def combined_move_with_zoom(
        self,
        pan_dir: int,
        tilt_dir: int,
        zoom_target: int,
        duration: float = DEFAULT_MOVE_DURATION,
        verifier: MotionVerifier | None = None,
    ) -> tuple[bool, bool]:
        """Simultaneous pan + tilt + zoom to target.

        Returns (pan_moved, tilt_moved).
        """
        pan_speed = max(-1, min(1, pan_dir))
        tilt_speed = max(-1, min(1, tilt_dir))
        zoom_target = max(ZOOM_MIN, min(ZOOM_MAX, zoom_target))
        v = verifier or self.verifier
        with self._lock:
            before = v.grab_gray() if v else None
            self._backend.set_control(self._device, CTRL_PAN_SPEED, pan_speed)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, tilt_speed)
            self._backend.set_control(self._device, CTRL_ZOOM_ABSOLUTE, zoom_target)
            time.sleep(duration)
            self._backend.set_control(self._device, CTRL_PAN_SPEED, 0)
            self._backend.set_control(self._device, CTRL_TILT_SPEED, 0)
            pan_moved = True
            tilt_moved = True
            if v and before is not None:
                after = v.grab_gray()
                pan_moved = v.did_pan(before, after)
                tilt_moved = v.did_tilt(before, after)
            self.position.update_pan(pan_speed, duration, pan_moved)
            self.position.update_tilt(tilt_speed, duration, tilt_moved)
            self.position.update_zoom(zoom_target)
            return pan_moved, tilt_moved

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
