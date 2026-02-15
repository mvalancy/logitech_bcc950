"""Unit tests for BCC950Controller."""

import pytest
from unittest.mock import MagicMock, call, patch

from bcc950.controller import BCC950Controller
from bcc950.constants import (
    CTRL_PAN_SPEED,
    CTRL_TILT_SPEED,
    CTRL_ZOOM_ABSOLUTE,
    ZOOM_MAX,
    ZOOM_MIN,
)


# ---------------------------------------------------------------------------
# Pan
# ---------------------------------------------------------------------------

class TestPan:
    def test_pan_left_sets_speed_then_stops(self, controller, mock_backend):
        """pan_left should set negative pan speed, sleep, then set speed to 0."""
        with patch("bcc950.motion.time.sleep"):
            controller.pan_left(duration=0.1)

        calls = mock_backend.set_control.call_args_list
        # First call: set pan speed to -1 (direction * config speed, clamped)
        assert calls[0] == call("/dev/video99", CTRL_PAN_SPEED, -1)
        # Second call: stop pan
        assert calls[1] == call("/dev/video99", CTRL_PAN_SPEED, 0)

    def test_pan_right_sets_speed_then_stops(self, controller, mock_backend):
        with patch("bcc950.motion.time.sleep"):
            controller.pan_right(duration=0.1)

        calls = mock_backend.set_control.call_args_list
        assert calls[0] == call("/dev/video99", CTRL_PAN_SPEED, 1)
        assert calls[1] == call("/dev/video99", CTRL_PAN_SPEED, 0)


# ---------------------------------------------------------------------------
# Tilt
# ---------------------------------------------------------------------------

class TestTilt:
    def test_tilt_up_sets_speed_then_stops(self, controller, mock_backend):
        with patch("bcc950.motion.time.sleep"):
            controller.tilt_up(duration=0.1)

        calls = mock_backend.set_control.call_args_list
        assert calls[0] == call("/dev/video99", CTRL_TILT_SPEED, 1)
        assert calls[1] == call("/dev/video99", CTRL_TILT_SPEED, 0)

    def test_tilt_down_sets_speed_then_stops(self, controller, mock_backend):
        with patch("bcc950.motion.time.sleep"):
            controller.tilt_down(duration=0.1)

        calls = mock_backend.set_control.call_args_list
        assert calls[0] == call("/dev/video99", CTRL_TILT_SPEED, -1)
        assert calls[1] == call("/dev/video99", CTRL_TILT_SPEED, 0)


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------

class TestZoom:
    def test_zoom_in_increases_zoom(self, controller, mock_backend):
        """zoom_in should increase zoom by the configured step."""
        with patch("bcc950.motion.time.sleep"):
            controller.zoom_in()

        mock_backend.set_control.assert_called_once_with(
            "/dev/video99", CTRL_ZOOM_ABSOLUTE, ZOOM_MIN + controller.config.zoom_step
        )

    def test_zoom_out_does_not_go_below_min(self, controller, mock_backend):
        """Zooming out from minimum should clamp at ZOOM_MIN."""
        with patch("bcc950.motion.time.sleep"):
            controller.zoom_out()

        mock_backend.set_control.assert_called_once_with(
            "/dev/video99", CTRL_ZOOM_ABSOLUTE, ZOOM_MIN
        )

    def test_zoom_in_clamps_at_max(self, controller, mock_backend):
        """Repeated zoom-in should not exceed ZOOM_MAX."""
        with patch("bcc950.motion.time.sleep"):
            # Set position zoom near max
            controller.position.zoom = ZOOM_MAX - 1
            controller.zoom_in()

        mock_backend.set_control.assert_called_once_with(
            "/dev/video99", CTRL_ZOOM_ABSOLUTE, ZOOM_MAX
        )


# ---------------------------------------------------------------------------
# Combined move
# ---------------------------------------------------------------------------

class TestCombinedMove:
    def test_move_issues_pan_and_tilt_calls(self, controller, mock_backend):
        """move() should set both pan and tilt speeds, then stop both."""
        with patch("bcc950.motion.time.sleep"):
            controller.move(pan_dir=1, tilt_dir=-1, duration=0.2)

        calls = mock_backend.set_control.call_args_list
        # Start pan + tilt
        assert call("/dev/video99", CTRL_PAN_SPEED, 1) in calls
        assert call("/dev/video99", CTRL_TILT_SPEED, -1) in calls
        # Stop pan + tilt
        assert call("/dev/video99", CTRL_PAN_SPEED, 0) in calls
        assert call("/dev/video99", CTRL_TILT_SPEED, 0) in calls

    def test_move_with_zoom(self, controller, mock_backend):
        """move_with_zoom should set pan, tilt, and zoom, then stop."""
        with patch("bcc950.motion.time.sleep"):
            controller.move_with_zoom(pan_dir=1, tilt_dir=1, zoom_target=300, duration=0.1)

        calls = mock_backend.set_control.call_args_list
        assert call("/dev/video99", CTRL_PAN_SPEED, 1) in calls
        assert call("/dev/video99", CTRL_TILT_SPEED, 1) in calls
        assert call("/dev/video99", CTRL_ZOOM_ABSOLUTE, 300) in calls
        # Stops
        assert call("/dev/video99", CTRL_PAN_SPEED, 0) in calls
        assert call("/dev/video99", CTRL_TILT_SPEED, 0) in calls


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

class TestPresets:
    def test_save_and_recall_preset(self, controller, mock_backend):
        """Saving and recalling a preset should succeed."""
        with patch("bcc950.motion.time.sleep"):
            # Move to a position first
            controller.position.pan = 1.5
            controller.position.tilt = -0.5
            controller.position.zoom = 200

            controller.save_preset("home")
            result = controller.recall_preset("home")

        assert result is True

    def test_recall_nonexistent_preset(self, controller, mock_backend):
        result = controller.recall_preset("does_not_exist")
        assert result is False

    def test_list_presets(self, controller, mock_backend):
        with patch("bcc950.motion.time.sleep"):
            controller.save_preset("a")
            controller.save_preset("b")

        assert sorted(controller.list_presets()) == ["a", "b"]

    def test_delete_preset(self, controller, mock_backend):
        with patch("bcc950.motion.time.sleep"):
            controller.save_preset("temp")
        assert controller.delete_preset("temp") is True
        assert controller.delete_preset("temp") is False


# ---------------------------------------------------------------------------
# Reset position
# ---------------------------------------------------------------------------

class TestResetPosition:
    def test_reset_position_sequence(self, controller, mock_backend):
        """reset_position should pan R/L, tilt U/D, zoom min, then reset tracker."""
        with patch("bcc950.motion.time.sleep"):
            controller.reset_position()

        calls = mock_backend.set_control.call_args_list

        # Should have multiple set_control calls for pan/tilt movements + zoom
        # Pan right start, pan right stop, pan left start, pan left stop,
        # tilt up start, tilt up stop, tilt down start, tilt down stop,
        # zoom to min
        pan_calls = [c for c in calls if c[0][1] == CTRL_PAN_SPEED]
        tilt_calls = [c for c in calls if c[0][1] == CTRL_TILT_SPEED]
        zoom_calls = [c for c in calls if c[0][1] == CTRL_ZOOM_ABSOLUTE]

        # There should be pan starts and stops
        assert len(pan_calls) >= 4  # two starts + two stops
        # There should be tilt starts and stops
        assert len(tilt_calls) >= 4
        # Zoom should be set to minimum
        assert call("/dev/video99", CTRL_ZOOM_ABSOLUTE, ZOOM_MIN) in zoom_calls

        # Position tracker should be reset
        assert controller.position.pan == 0.0
        assert controller.position.tilt == 0.0
        assert controller.position.zoom == ZOOM_MIN
