"""High-level BCC950 controller tying all components together."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Config
from .constants import (
    CTRL_PAN_SPEED,
    CTRL_TILT_SPEED,
    CTRL_ZOOM_ABSOLUTE,
    DEFAULT_MOVE_DURATION,
    ZOOM_MAX,
    ZOOM_MIN,
)
from .discovery import find_bcc950, has_ptz_support
from .motion import MotionController
from .position import PositionTracker
from .presets import PresetManager
from .v4l2_backend import SubprocessV4L2Backend, V4L2Backend

if TYPE_CHECKING:
    import cv2


class BCC950Controller:
    """High-level controller for the Logitech BCC950 camera.

    Backward-compatible API (pan_left(), tilt_up(), etc.) plus new
    methods (move(), zoom_to(), save_preset(), recall_preset()).

    Call :meth:`attach_video` with an open ``cv2.VideoCapture`` to
    enable automatic motion verification and limit discovery.
    """

    def __init__(
        self,
        device: str | None = None,
        backend: V4L2Backend | None = None,
        config_path: Path | None = None,
        presets_path: Path | None = None,
    ):
        self._config = Config(config_path)
        self._config.load()

        self._backend = backend or SubprocessV4L2Backend()
        self._device = device or self._config.device
        self._position = PositionTracker()
        self._motion = MotionController(self._backend, self._device, self._position)
        self._presets = PresetManager(presets_path)

    # --- Video / motion verification ---

    def attach_video(self, cap: cv2.VideoCapture) -> None:
        """Attach a video capture for automatic motion verification.

        Once attached, every pan/tilt command compares frames before
        and after the move.  If the camera didn't shift, the current
        position is recorded as a mechanical limit.  Use
        ``position.can_pan_left`` etc. to query discovered limits.
        """
        from .motion_verify import MotionVerifier

        self._motion.verifier = MotionVerifier(cap)

    def detach_video(self) -> None:
        """Detach video capture; moves will no longer be verified."""
        self._motion.verifier = None

    @property
    def has_verifier(self) -> bool:
        """True if a motion verifier is attached."""
        return self._motion.verifier is not None

    @property
    def device(self) -> str:
        return self._device

    @device.setter
    def device(self, value: str) -> None:
        self._device = value
        self._motion._device = value

    @property
    def position(self) -> PositionTracker:
        return self._position

    @property
    def config(self) -> Config:
        return self._config

    # --- Backward-compatible API ---

    def pan_left(self, duration: float = DEFAULT_MOVE_DURATION) -> bool:
        """Pan camera left. Returns True if the camera moved."""
        return self._motion.pan(-self._config.pan_speed, duration)

    def pan_right(self, duration: float = DEFAULT_MOVE_DURATION) -> bool:
        """Pan camera right. Returns True if the camera moved."""
        return self._motion.pan(self._config.pan_speed, duration)

    def tilt_up(self, duration: float = DEFAULT_MOVE_DURATION) -> bool:
        """Tilt camera up. Returns True if the camera moved."""
        return self._motion.tilt(self._config.tilt_speed, duration)

    def tilt_down(self, duration: float = DEFAULT_MOVE_DURATION) -> bool:
        """Tilt camera down. Returns True if the camera moved."""
        return self._motion.tilt(-self._config.tilt_speed, duration)

    def zoom_in(self) -> None:
        """Zoom camera in by one step."""
        self._motion.zoom_relative(self._config.zoom_step)

    def zoom_out(self) -> None:
        """Zoom camera out by one step."""
        self._motion.zoom_relative(-self._config.zoom_step)

    def reset_position(self) -> None:
        """Reset camera to center and minimum zoom."""
        self._motion.pan(1, 0.1)
        self._motion.pan(-1, 0.1)
        self._motion.tilt(1, 0.1)
        self._motion.tilt(-1, 0.1)
        self._motion.zoom_absolute(ZOOM_MIN)
        self._position.reset()

    # --- New API ---

    def move(
        self,
        pan_dir: int = 0,
        tilt_dir: int = 0,
        duration: float = DEFAULT_MOVE_DURATION,
    ) -> tuple[bool, bool]:
        """Combined pan+tilt move. Returns (pan_moved, tilt_moved)."""
        return self._motion.combined_move(pan_dir, tilt_dir, duration)

    def zoom_to(self, value: int) -> None:
        """Set zoom to an absolute value."""
        self._motion.zoom_absolute(value)

    def move_with_zoom(
        self,
        pan_dir: int = 0,
        tilt_dir: int = 0,
        zoom_target: int = ZOOM_MIN,
        duration: float = DEFAULT_MOVE_DURATION,
    ) -> tuple[bool, bool]:
        """Combined pan + tilt + zoom. Returns (pan_moved, tilt_moved)."""
        return self._motion.combined_move_with_zoom(pan_dir, tilt_dir, zoom_target, duration)

    def save_preset(self, name: str) -> None:
        """Save current position as a named preset."""
        self._presets.save_preset(name, self._position)

    def recall_preset(self, name: str) -> bool:
        """Recall a named preset. Returns False if not found."""
        pos = self._presets.recall_preset(name)
        if pos is None:
            return False
        self._motion.zoom_absolute(pos.zoom)
        return True

    def delete_preset(self, name: str) -> bool:
        """Delete a named preset."""
        return self._presets.delete_preset(name)

    def list_presets(self) -> list[str]:
        """List all preset names."""
        return self._presets.list_presets()

    # --- Discovery / Setup ---

    def find_camera(self) -> str | None:
        """Auto-detect BCC950 camera device."""
        device = find_bcc950(self._backend)
        if device:
            self._device = device
            self._motion._device = device
            self._config.device = device
            self._config.save()
        return device

    def has_ptz_support(self) -> bool:
        """Check if the current device supports PTZ controls."""
        return has_ptz_support(self._backend, self._device)

    def list_devices(self) -> str:
        """List all V4L2 devices."""
        return self._backend.list_devices()

    def get_zoom(self) -> int:
        """Get current zoom value from hardware."""
        return self._backend.get_control(self._device, CTRL_ZOOM_ABSOLUTE)

    def stop(self) -> None:
        """Stop all movement."""
        self._motion.stop()
