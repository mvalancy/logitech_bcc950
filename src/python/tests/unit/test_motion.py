"""Unit tests for MotionController."""

import threading
import pytest
from unittest.mock import MagicMock, call, patch

from bcc950.motion import MotionController
from bcc950.position import PositionTracker
from bcc950.v4l2_backend import V4L2Backend
from bcc950.constants import (
    CTRL_PAN_SPEED,
    CTRL_TILT_SPEED,
    CTRL_ZOOM_ABSOLUTE,
    ZOOM_MAX,
    ZOOM_MIN,
)


DEVICE = "/dev/video99"


@pytest.fixture
def backend():
    return MagicMock(spec=V4L2Backend)


@pytest.fixture
def position():
    return PositionTracker()


@pytest.fixture
def motion(backend, position):
    return MotionController(backend, DEVICE, position)


# ---------------------------------------------------------------------------
# Pan
# ---------------------------------------------------------------------------

class TestPan:
    def test_pan_right_duration(self, motion, backend):
        """Pan right: set speed +1, sleep, stop, update position."""
        with patch("bcc950.motion.time.sleep") as mock_sleep:
            motion.pan(1, duration=0.5)

        backend.set_control.assert_any_call(DEVICE, CTRL_PAN_SPEED, 1)
        backend.set_control.assert_any_call(DEVICE, CTRL_PAN_SPEED, 0)
        mock_sleep.assert_called_once_with(0.5)
        assert motion.position.pan == pytest.approx(0.5)

    def test_pan_left_duration(self, motion, backend):
        with patch("bcc950.motion.time.sleep") as mock_sleep:
            motion.pan(-1, duration=0.3)

        backend.set_control.assert_any_call(DEVICE, CTRL_PAN_SPEED, -1)
        backend.set_control.assert_any_call(DEVICE, CTRL_PAN_SPEED, 0)
        mock_sleep.assert_called_once_with(0.3)
        assert motion.position.pan == pytest.approx(-0.3)

    def test_pan_call_order(self, motion, backend):
        """set_control(speed) must happen before set_control(0)."""
        with patch("bcc950.motion.time.sleep"):
            motion.pan(1, duration=0.1)

        calls = backend.set_control.call_args_list
        assert calls[0] == call(DEVICE, CTRL_PAN_SPEED, 1)
        assert calls[1] == call(DEVICE, CTRL_PAN_SPEED, 0)


# ---------------------------------------------------------------------------
# Tilt
# ---------------------------------------------------------------------------

class TestTilt:
    def test_tilt_up_duration(self, motion, backend):
        with patch("bcc950.motion.time.sleep") as mock_sleep:
            motion.tilt(1, duration=0.4)

        backend.set_control.assert_any_call(DEVICE, CTRL_TILT_SPEED, 1)
        backend.set_control.assert_any_call(DEVICE, CTRL_TILT_SPEED, 0)
        mock_sleep.assert_called_once_with(0.4)
        assert motion.position.tilt == pytest.approx(0.4)

    def test_tilt_down_duration(self, motion, backend):
        with patch("bcc950.motion.time.sleep") as mock_sleep:
            motion.tilt(-1, duration=0.2)

        backend.set_control.assert_any_call(DEVICE, CTRL_TILT_SPEED, -1)
        backend.set_control.assert_any_call(DEVICE, CTRL_TILT_SPEED, 0)
        mock_sleep.assert_called_once_with(0.2)
        assert motion.position.tilt == pytest.approx(-0.2)


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------

class TestZoom:
    def test_zoom_absolute_normal(self, motion, backend):
        motion.zoom_absolute(250)
        backend.set_control.assert_called_once_with(DEVICE, CTRL_ZOOM_ABSOLUTE, 250)
        assert motion.position.zoom == 250

    def test_zoom_absolute_clamps_low(self, motion, backend):
        motion.zoom_absolute(0)
        backend.set_control.assert_called_once_with(DEVICE, CTRL_ZOOM_ABSOLUTE, ZOOM_MIN)
        assert motion.position.zoom == ZOOM_MIN

    def test_zoom_absolute_clamps_high(self, motion, backend):
        motion.zoom_absolute(9999)
        backend.set_control.assert_called_once_with(DEVICE, CTRL_ZOOM_ABSOLUTE, ZOOM_MAX)
        assert motion.position.zoom == ZOOM_MAX

    def test_zoom_relative_positive(self, motion, backend):
        motion.zoom_relative(50)
        backend.set_control.assert_called_once_with(DEVICE, CTRL_ZOOM_ABSOLUTE, ZOOM_MIN + 50)
        assert motion.position.zoom == ZOOM_MIN + 50

    def test_zoom_relative_clamps_at_min(self, motion, backend):
        """Negative delta from minimum should stay at ZOOM_MIN."""
        motion.zoom_relative(-50)
        backend.set_control.assert_called_once_with(DEVICE, CTRL_ZOOM_ABSOLUTE, ZOOM_MIN)
        assert motion.position.zoom == ZOOM_MIN

    def test_zoom_relative_clamps_at_max(self, motion, backend):
        motion.position.zoom = ZOOM_MAX
        motion.zoom_relative(100)
        backend.set_control.assert_called_once_with(DEVICE, CTRL_ZOOM_ABSOLUTE, ZOOM_MAX)
        assert motion.position.zoom == ZOOM_MAX


# ---------------------------------------------------------------------------
# Combined moves
# ---------------------------------------------------------------------------

class TestCombinedMove:
    def test_combined_move_sets_and_stops_both(self, motion, backend):
        with patch("bcc950.motion.time.sleep"):
            motion.combined_move(1, -1, duration=0.2)

        calls = backend.set_control.call_args_list
        # First two calls: set speeds
        assert calls[0] == call(DEVICE, CTRL_PAN_SPEED, 1)
        assert calls[1] == call(DEVICE, CTRL_TILT_SPEED, -1)
        # After sleep: stop both
        assert calls[2] == call(DEVICE, CTRL_PAN_SPEED, 0)
        assert calls[3] == call(DEVICE, CTRL_TILT_SPEED, 0)

    def test_combined_move_updates_position(self, motion, backend):
        with patch("bcc950.motion.time.sleep"):
            motion.combined_move(1, -1, duration=0.5)

        assert motion.position.pan == pytest.approx(0.5)
        assert motion.position.tilt == pytest.approx(-0.5)

    def test_combined_move_with_zoom(self, motion, backend):
        with patch("bcc950.motion.time.sleep"):
            motion.combined_move_with_zoom(1, 1, 300, duration=0.2)

        calls = backend.set_control.call_args_list
        assert call(DEVICE, CTRL_PAN_SPEED, 1) in calls
        assert call(DEVICE, CTRL_TILT_SPEED, 1) in calls
        assert call(DEVICE, CTRL_ZOOM_ABSOLUTE, 300) in calls
        # Stops
        assert call(DEVICE, CTRL_PAN_SPEED, 0) in calls
        assert call(DEVICE, CTRL_TILT_SPEED, 0) in calls
        # Position updated
        assert motion.position.pan == pytest.approx(0.2)
        assert motion.position.tilt == pytest.approx(0.2)
        assert motion.position.zoom == 300

    def test_combined_move_with_zoom_clamps(self, motion, backend):
        """Zoom target above ZOOM_MAX should be clamped."""
        with patch("bcc950.motion.time.sleep"):
            motion.combined_move_with_zoom(0, 0, 9999, duration=0.1)

        backend.set_control.assert_any_call(DEVICE, CTRL_ZOOM_ABSOLUTE, ZOOM_MAX)
        assert motion.position.zoom == ZOOM_MAX


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_moves_do_not_interleave(self, motion, backend):
        """Two concurrent pan calls should each complete their start-stop
        sequence without interleaving (ensured by the internal lock).

        We verify that set_control calls always appear in paired
        start/stop sequences -- never two starts in a row without a stop.
        """
        results = []
        barrier = threading.Barrier(2)

        def _pan_right():
            barrier.wait()
            with patch("bcc950.motion.time.sleep"):
                motion.pan(1, duration=0.05)

        def _pan_left():
            barrier.wait()
            with patch("bcc950.motion.time.sleep"):
                motion.pan(-1, duration=0.05)

        t1 = threading.Thread(target=_pan_right)
        t2 = threading.Thread(target=_pan_left)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        calls = backend.set_control.call_args_list
        pan_calls = [c for c in calls if c[0][1] == CTRL_PAN_SPEED]

        # Should have exactly 4 pan calls: start-stop, start-stop
        assert len(pan_calls) == 4

        # Verify pairing: calls at index 0,1 form a pair, 2,3 form a pair
        # First of each pair is non-zero, second is zero
        assert pan_calls[0][0][2] != 0  # first start
        assert pan_calls[1][0][2] == 0  # first stop
        assert pan_calls[2][0][2] != 0  # second start
        assert pan_calls[3][0][2] == 0  # second stop


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_zeros_both_axes(self, motion, backend):
        motion.stop()
        calls = backend.set_control.call_args_list
        assert call(DEVICE, CTRL_PAN_SPEED, 0) in calls
        assert call(DEVICE, CTRL_TILT_SPEED, 0) in calls
