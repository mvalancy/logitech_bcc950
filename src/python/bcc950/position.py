"""Position tracking for BCC950 (estimated, no absolute readback).

The BCC950 has no pan/tilt position readback — only speed controls.
We track position by accumulating successful moves and detecting
limits when a move command produces no frame shift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import ZOOM_DEFAULT, ZOOM_MAX, ZOOM_MIN


@dataclass
class PositionTracker:
    """Tracks estimated camera position based on movement history.

    Position is tracked in arbitrary units (accumulated speed * duration).
    Limits are discovered dynamically when moves fail (camera doesn't shift).
    """

    pan: float = 0.0
    tilt: float = 0.0
    zoom: int = field(default=ZOOM_DEFAULT)

    # Limits: None means unknown (not yet discovered)
    pan_min: float | None = None
    pan_max: float | None = None
    tilt_min: float | None = None
    tilt_max: float | None = None

    def update_pan(self, speed: int, duration: float, moved: bool = True) -> None:
        """Update pan estimate after a move command.

        Parameters
        ----------
        speed : int
            Pan speed (-1 or 1).
        duration : float
            Duration of the move.
        moved : bool
            Whether the camera actually moved (from motion verification).
            If False, the current position is recorded as a limit.
        """
        if moved:
            self.pan += speed * duration
        else:
            # Hit a limit — record it
            if speed < 0:
                self.pan_min = self.pan
            elif speed > 0:
                self.pan_max = self.pan

    def update_tilt(self, speed: int, duration: float, moved: bool = True) -> None:
        """Update tilt estimate after a move command."""
        if moved:
            self.tilt += speed * duration
        else:
            if speed < 0:
                self.tilt_min = self.tilt
            elif speed > 0:
                self.tilt_max = self.tilt

    def update_zoom(self, value: int) -> None:
        """Update zoom to an absolute value (clamped)."""
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, value))

    @property
    def can_pan_left(self) -> bool:
        """True if we haven't hit the left limit (or haven't checked yet)."""
        return self.pan_min is None or self.pan > self.pan_min

    @property
    def can_pan_right(self) -> bool:
        """True if we haven't hit the right limit (or haven't checked yet)."""
        return self.pan_max is None or self.pan < self.pan_max

    @property
    def can_tilt_up(self) -> bool:
        return self.tilt_max is None or self.tilt < self.tilt_max

    @property
    def can_tilt_down(self) -> bool:
        return self.tilt_min is None or self.tilt > self.tilt_min

    def distance_to(self, other: PositionTracker) -> float:
        """Euclidean distance to another position (pan/tilt only)."""
        dp = self.pan - other.pan
        dt = self.tilt - other.tilt
        return (dp**2 + dt**2) ** 0.5

    def reset(self) -> None:
        """Reset position to origin. Keeps discovered limits."""
        self.pan = 0.0
        self.tilt = 0.0
        self.zoom = ZOOM_DEFAULT

    def clear_limits(self) -> None:
        """Clear all discovered limits."""
        self.pan_min = self.pan_max = None
        self.tilt_min = self.tilt_max = None

    def __str__(self) -> str:
        pan_range = f"[{self.pan_min:.1f}" if self.pan_min is not None else "[?"
        pan_range += f"..{self.pan_max:.1f}]" if self.pan_max is not None else "..?]"
        tilt_range = f"[{self.tilt_min:.1f}" if self.tilt_min is not None else "[?"
        tilt_range += f"..{self.tilt_max:.1f}]" if self.tilt_max is not None else "..?]"
        return (
            f"Position(pan={self.pan:.1f} {pan_range}, "
            f"tilt={self.tilt:.1f} {tilt_range}, "
            f"zoom={self.zoom})"
        )
