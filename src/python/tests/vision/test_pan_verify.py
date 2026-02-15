"""Vision-based verification tests for pan movement.

These tests use optical flow analysis to confirm that the camera
actually moved when pan commands are issued.

Run with: pytest --run-vision --device /dev/videoN
"""

import time

import cv2
import numpy as np
import pytest

from .cv_utils import compute_frame_difference, compute_sparse_flow

PAN_DURATION = 1.0
MIN_MEDIAN_DX = 3.0
CONSISTENCY_THRESHOLD = 0.70
MIN_FRAME_DIFF = 5.0


@pytest.mark.vision
class TestPanLeftOpticalFlow:
    """When the camera pans left, scene features should shift right."""

    def test_pan_left_optical_flow(self, camera_capture, hardware_controller):
        # Capture the "before" frame
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before pan"
        gray_before = cv2.cvtColor(frame_before, cv2.COLOR_BGR2GRAY)

        # Execute pan left
        hardware_controller.pan_left(duration=PAN_DURATION)
        time.sleep(0.2)  # settle time

        # Capture the "after" frame
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after pan"
        gray_after = cv2.cvtColor(frame_after, cv2.COLOR_BGR2GRAY)

        # Compute sparse optical flow
        dx, dy = compute_sparse_flow(gray_before, gray_after)
        assert len(dx) > 0, "No feature points tracked"

        # When camera pans left, scene features shift right (positive dx)
        median_dx = float(np.median(dx))
        assert median_dx > MIN_MEDIAN_DX, (
            f"Expected median dx > {MIN_MEDIAN_DX} for pan-left, "
            f"got median_dx={median_dx:.2f}"
        )

        # Check consistency: at least 70% of features should shift right
        consistent = float(np.mean(dx > 0))
        assert consistent >= CONSISTENCY_THRESHOLD, (
            f"Expected >= {CONSISTENCY_THRESHOLD*100:.0f}% features shifting right, "
            f"got {consistent*100:.1f}%"
        )


@pytest.mark.vision
class TestPanRightOpticalFlow:
    """When the camera pans right, scene features should shift left."""

    def test_pan_right_optical_flow(self, camera_capture, hardware_controller):
        # Capture the "before" frame
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before pan"
        gray_before = cv2.cvtColor(frame_before, cv2.COLOR_BGR2GRAY)

        # Execute pan right
        hardware_controller.pan_right(duration=PAN_DURATION)
        time.sleep(0.2)

        # Capture the "after" frame
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after pan"
        gray_after = cv2.cvtColor(frame_after, cv2.COLOR_BGR2GRAY)

        # Compute sparse optical flow
        dx, dy = compute_sparse_flow(gray_before, gray_after)
        assert len(dx) > 0, "No feature points tracked"

        # When camera pans right, scene features shift left (negative dx)
        median_dx = float(np.median(dx))
        assert median_dx < -MIN_MEDIAN_DX, (
            f"Expected median dx < {-MIN_MEDIAN_DX} for pan-right, "
            f"got median_dx={median_dx:.2f}"
        )

        # Check consistency: at least 70% of features should shift left
        consistent = float(np.mean(dx < 0))
        assert consistent >= CONSISTENCY_THRESHOLD, (
            f"Expected >= {CONSISTENCY_THRESHOLD*100:.0f}% features shifting left, "
            f"got {consistent*100:.1f}%"
        )


@pytest.mark.vision
class TestPanFrameDifference:
    """Panning should produce a visible change in the image."""

    def test_pan_frame_difference(self, camera_capture, hardware_controller):
        # Capture before
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before pan"

        # Pan left for a visible change
        hardware_controller.pan_left(duration=PAN_DURATION)
        time.sleep(0.2)

        # Capture after
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after pan"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected mean pixel difference > {MIN_FRAME_DIFF} after pan, "
            f"got {mean_diff:.2f}"
        )
