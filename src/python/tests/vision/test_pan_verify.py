"""Vision-based verification tests for pan movement.

These tests verify that pan commands produce visible camera movement
by comparing frames before and after the command.

Run with: pytest --run-vision --device /dev/videoN
"""

import time

import cv2
import pytest

from .cv_utils import compute_frame_difference, flush_buffer

PAN_DURATION = 0.3
MIN_FRAME_DIFF = 5.0


@pytest.mark.vision
class TestPanLeftOpticalFlow:
    """Pan left should produce a visible change in the image."""

    def test_pan_left_optical_flow(self, camera_capture, hardware_controller):
        # Pre-position: ensure room to move left
        hardware_controller.pan_right(duration=0.5)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before pan"

        hardware_controller.pan_left(duration=PAN_DURATION)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after pan"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected visible change after pan left, "
            f"got mean_diff={mean_diff:.2f}"
        )


@pytest.mark.vision
class TestPanRightOpticalFlow:
    """Pan right should produce a visible change in the image."""

    def test_pan_right_optical_flow(self, camera_capture, hardware_controller):
        # Pre-position: ensure room to move right
        hardware_controller.pan_left(duration=0.5)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before pan"

        hardware_controller.pan_right(duration=PAN_DURATION)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after pan"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected visible change after pan right, "
            f"got mean_diff={mean_diff:.2f}"
        )


@pytest.mark.vision
class TestPanFrameDifference:
    """Panning should produce a visible change in the image."""

    def test_pan_frame_difference(self, camera_capture, hardware_controller):
        # Pre-position to ensure room to move
        hardware_controller.pan_right(duration=0.5)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before pan"

        hardware_controller.pan_left(duration=PAN_DURATION)
        time.sleep(0.5)
        flush_buffer(camera_capture)

        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after pan"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected mean pixel difference > {MIN_FRAME_DIFF} after pan, "
            f"got {mean_diff:.2f}"
        )
