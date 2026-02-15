"""Position tracking for BCC950 (estimated, no absolute readback)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import EST_PAN_RANGE, EST_TILT_RANGE, ZOOM_DEFAULT, ZOOM_MAX, ZOOM_MIN


@dataclass
class PositionTracker:
    """Tracks estimated camera position based on movement-seconds.

    The BCC950 has no absolute pan/tilt readback, so we accumulate
    movement duration * speed to estimate position.
    """

    pan: float = 0.0
    tilt: float = 0.0
    zoom: int = field(default=ZOOM_DEFAULT)

    pan_range: tuple[float, float] = field(default=EST_PAN_RANGE)
    tilt_range: tuple[float, float] = field(default=EST_TILT_RANGE)

    def update_pan(self, speed: int, duration: float) -> None:
        """Update pan estimate: speed * duration added to position."""
        self.pan += speed * duration
        self.pan = max(self.pan_range[0], min(self.pan_range[1], self.pan))

    def update_tilt(self, speed: int, duration: float) -> None:
        """Update tilt estimate: speed * duration added to position."""
        self.tilt += speed * duration
        self.tilt = max(self.tilt_range[0], min(self.tilt_range[1], self.tilt))

    def update_zoom(self, value: int) -> None:
        """Update zoom to an absolute value (clamped)."""
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, value))

    def distance_to(self, other: PositionTracker) -> float:
        """Euclidean distance to another position (pan/tilt only)."""
        dp = self.pan - other.pan
        dt = self.tilt - other.tilt
        return (dp**2 + dt**2) ** 0.5

    def reset(self) -> None:
        """Reset to origin."""
        self.pan = 0.0
        self.tilt = 0.0
        self.zoom = ZOOM_DEFAULT
