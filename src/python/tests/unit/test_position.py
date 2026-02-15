"""Unit tests for PositionTracker."""

import pytest

from bcc950.position import PositionTracker
from bcc950.constants import (
    EST_PAN_RANGE,
    EST_TILT_RANGE,
    ZOOM_DEFAULT,
    ZOOM_MAX,
    ZOOM_MIN,
)


# ---------------------------------------------------------------------------
# Accumulation
# ---------------------------------------------------------------------------

class TestAccumulation:
    def test_pan_accumulates_positive(self):
        pos = PositionTracker()
        pos.update_pan(1, 0.5)
        assert pos.pan == pytest.approx(0.5)

    def test_pan_accumulates_negative(self):
        pos = PositionTracker()
        pos.update_pan(-1, 0.3)
        assert pos.pan == pytest.approx(-0.3)

    def test_pan_accumulates_multiple(self):
        pos = PositionTracker()
        pos.update_pan(1, 0.5)
        pos.update_pan(1, 0.5)
        assert pos.pan == pytest.approx(1.0)

    def test_tilt_accumulates_positive(self):
        pos = PositionTracker()
        pos.update_tilt(1, 0.4)
        assert pos.tilt == pytest.approx(0.4)

    def test_tilt_accumulates_negative(self):
        pos = PositionTracker()
        pos.update_tilt(-1, 0.2)
        assert pos.tilt == pytest.approx(-0.2)

    def test_tilt_accumulates_multiple(self):
        pos = PositionTracker()
        pos.update_tilt(-1, 0.5)
        pos.update_tilt(-1, 0.5)
        assert pos.tilt == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Clamping at range limits
# ---------------------------------------------------------------------------

class TestClamping:
    def test_pan_clamps_at_max(self):
        pos = PositionTracker()
        pos.update_pan(1, 100.0)  # Way beyond range
        assert pos.pan == pytest.approx(EST_PAN_RANGE[1])

    def test_pan_clamps_at_min(self):
        pos = PositionTracker()
        pos.update_pan(-1, 100.0)
        assert pos.pan == pytest.approx(EST_PAN_RANGE[0])

    def test_tilt_clamps_at_max(self):
        pos = PositionTracker()
        pos.update_tilt(1, 100.0)
        assert pos.tilt == pytest.approx(EST_TILT_RANGE[1])

    def test_tilt_clamps_at_min(self):
        pos = PositionTracker()
        pos.update_tilt(-1, 100.0)
        assert pos.tilt == pytest.approx(EST_TILT_RANGE[0])

    def test_pan_stays_clamped_after_further_movement(self):
        pos = PositionTracker()
        pos.update_pan(1, 100.0)
        pos.update_pan(1, 1.0)
        assert pos.pan == pytest.approx(EST_PAN_RANGE[1])

    def test_tilt_stays_clamped_after_further_movement(self):
        pos = PositionTracker()
        pos.update_tilt(1, 100.0)
        pos.update_tilt(1, 1.0)
        assert pos.tilt == pytest.approx(EST_TILT_RANGE[1])


# ---------------------------------------------------------------------------
# distance_to
# ---------------------------------------------------------------------------

class TestDistanceTo:
    def test_distance_to_same_position(self):
        a = PositionTracker()
        b = PositionTracker()
        assert a.distance_to(b) == pytest.approx(0.0)

    def test_distance_to_different_pan(self):
        a = PositionTracker(pan=3.0, tilt=0.0)
        b = PositionTracker(pan=0.0, tilt=0.0)
        assert a.distance_to(b) == pytest.approx(3.0)

    def test_distance_to_different_tilt(self):
        a = PositionTracker(pan=0.0, tilt=4.0)
        b = PositionTracker(pan=0.0, tilt=0.0)
        assert a.distance_to(b) == pytest.approx(4.0)

    def test_distance_to_pythagorean(self):
        a = PositionTracker(pan=3.0, tilt=4.0)
        b = PositionTracker(pan=0.0, tilt=0.0)
        assert a.distance_to(b) == pytest.approx(5.0)

    def test_distance_is_symmetric(self):
        a = PositionTracker(pan=1.0, tilt=2.0)
        b = PositionTracker(pan=-1.0, tilt=-1.0)
        assert a.distance_to(b) == pytest.approx(b.distance_to(a))

    def test_distance_ignores_zoom(self):
        """distance_to only considers pan/tilt, not zoom."""
        a = PositionTracker(pan=0.0, tilt=0.0, zoom=100)
        b = PositionTracker(pan=0.0, tilt=0.0, zoom=500)
        assert a.distance_to(b) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_restores_defaults(self):
        pos = PositionTracker(pan=2.5, tilt=-1.5, zoom=350)
        pos.reset()
        assert pos.pan == pytest.approx(0.0)
        assert pos.tilt == pytest.approx(0.0)
        assert pos.zoom == ZOOM_DEFAULT

    def test_reset_from_clamped_position(self):
        pos = PositionTracker()
        pos.update_pan(1, 100.0)
        pos.update_tilt(-1, 100.0)
        pos.update_zoom(ZOOM_MAX)
        pos.reset()
        assert pos.pan == pytest.approx(0.0)
        assert pos.tilt == pytest.approx(0.0)
        assert pos.zoom == ZOOM_DEFAULT


# ---------------------------------------------------------------------------
# Zoom update clamping
# ---------------------------------------------------------------------------

class TestZoomUpdate:
    def test_zoom_update_normal(self):
        pos = PositionTracker()
        pos.update_zoom(300)
        assert pos.zoom == 300

    def test_zoom_update_clamps_at_min(self):
        pos = PositionTracker()
        pos.update_zoom(0)
        assert pos.zoom == ZOOM_MIN

    def test_zoom_update_clamps_at_max(self):
        pos = PositionTracker()
        pos.update_zoom(9999)
        assert pos.zoom == ZOOM_MAX

    def test_zoom_update_exact_min(self):
        pos = PositionTracker()
        pos.update_zoom(ZOOM_MIN)
        assert pos.zoom == ZOOM_MIN

    def test_zoom_update_exact_max(self):
        pos = PositionTracker()
        pos.update_zoom(ZOOM_MAX)
        assert pos.zoom == ZOOM_MAX
