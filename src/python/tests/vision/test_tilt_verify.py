"""Vision-based verification tests for tilt movement.

These tests verify that tilt commands produce visible camera movement
by comparing frames before and after the command.

Run with: pytest --run-vision --device /dev/videoN
"""

import time

import cv2
import pytest

from .cv_utils import compute_frame_difference, flush_buffer

TILT_DURATION = 0.3
MIN_FRAME_DIFF = 5.0


@pytest.mark.vision
class TestTiltUpOpticalFlow:
    """Tilt up should produce a visible change in the image."""

    def test_tilt_up_optical_flow(self, camera_capture, hardware_controller):
        # Pre-position: ensure room to tilt up
        hardware_controller.tilt_down(duration=0.5)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before tilt"

        hardware_controller.tilt_up(duration=TILT_DURATION)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after tilt"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected visible change after tilt up, "
            f"got mean_diff={mean_diff:.2f}"
        )


@pytest.mark.vision
class TestTiltDownOpticalFlow:
    """Tilt down should produce a visible change in the image."""

    def test_tilt_down_optical_flow(self, camera_capture, hardware_controller):
        # Pre-position: ensure room to tilt down
        hardware_controller.tilt_up(duration=0.5)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before tilt"

        hardware_controller.tilt_down(duration=TILT_DURATION)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after tilt"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected visible change after tilt down, "
            f"got mean_diff={mean_diff:.2f}"
        )


@pytest.mark.vision
class TestTiltFrameDifference:
    """Tilting should produce a visible change in the image."""

    def test_tilt_frame_difference(self, camera_capture, hardware_controller):
        # Pre-position to ensure room to move
        hardware_controller.tilt_down(duration=0.5)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before tilt"

        hardware_controller.tilt_up(duration=TILT_DURATION)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after tilt"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected mean pixel difference > {MIN_FRAME_DIFF} after tilt, "
            f"got {mean_diff:.2f}"
        )
