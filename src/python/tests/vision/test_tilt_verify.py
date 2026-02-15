"""Vision-based verification tests for tilt movement.

These tests use optical flow analysis to confirm that the camera
actually moved when tilt commands are issued.

Run with: pytest --run-vision --device /dev/videoN
"""

import time

import cv2
import numpy as np
import pytest

from .cv_utils import compute_frame_difference, compute_sparse_flow

TILT_DURATION = 1.0
MIN_MEDIAN_DY = 3.0
CONSISTENCY_THRESHOLD = 0.70
MIN_FRAME_DIFF = 5.0


@pytest.mark.vision
class TestTiltUpOpticalFlow:
    """When the camera tilts up, scene features should shift down."""

    def test_tilt_up_optical_flow(self, camera_capture, hardware_controller):
        # Capture before
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before tilt"
        gray_before = cv2.cvtColor(frame_before, cv2.COLOR_BGR2GRAY)

        # Execute tilt up
        hardware_controller.tilt_up(duration=TILT_DURATION)
        time.sleep(0.2)

        # Capture after
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after tilt"
        gray_after = cv2.cvtColor(frame_after, cv2.COLOR_BGR2GRAY)

        # Compute sparse optical flow
        dx, dy = compute_sparse_flow(gray_before, gray_after)
        assert len(dy) > 0, "No feature points tracked"

        # When camera tilts up, scene features shift down (positive dy)
        median_dy = float(np.median(dy))
        assert median_dy > MIN_MEDIAN_DY, (
            f"Expected median dy > {MIN_MEDIAN_DY} for tilt-up, "
            f"got median_dy={median_dy:.2f}"
        )

        # Check consistency: at least 70% of features should shift down
        consistent = float(np.mean(dy > 0))
        assert consistent >= CONSISTENCY_THRESHOLD, (
            f"Expected >= {CONSISTENCY_THRESHOLD*100:.0f}% features shifting down, "
            f"got {consistent*100:.1f}%"
        )


@pytest.mark.vision
class TestTiltDownOpticalFlow:
    """When the camera tilts down, scene features should shift up."""

    def test_tilt_down_optical_flow(self, camera_capture, hardware_controller):
        # Capture before
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before tilt"
        gray_before = cv2.cvtColor(frame_before, cv2.COLOR_BGR2GRAY)

        # Execute tilt down
        hardware_controller.tilt_down(duration=TILT_DURATION)
        time.sleep(0.2)

        # Capture after
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after tilt"
        gray_after = cv2.cvtColor(frame_after, cv2.COLOR_BGR2GRAY)

        # Compute sparse optical flow
        dx, dy = compute_sparse_flow(gray_before, gray_after)
        assert len(dy) > 0, "No feature points tracked"

        # When camera tilts down, scene features shift up (negative dy)
        median_dy = float(np.median(dy))
        assert median_dy < -MIN_MEDIAN_DY, (
            f"Expected median dy < {-MIN_MEDIAN_DY} for tilt-down, "
            f"got median_dy={median_dy:.2f}"
        )

        # Check consistency: at least 70% of features should shift up
        consistent = float(np.mean(dy < 0))
        assert consistent >= CONSISTENCY_THRESHOLD, (
            f"Expected >= {CONSISTENCY_THRESHOLD*100:.0f}% features shifting up, "
            f"got {consistent*100:.1f}%"
        )


@pytest.mark.vision
class TestTiltFrameDifference:
    """Tilting should produce a visible change in the image."""

    def test_tilt_frame_difference(self, camera_capture, hardware_controller):
        # Capture before
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before tilt"

        # Tilt up for a visible change
        hardware_controller.tilt_up(duration=TILT_DURATION)
        time.sleep(0.2)

        # Capture after
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after tilt"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected mean pixel difference > {MIN_FRAME_DIFF} after tilt, "
            f"got {mean_diff:.2f}"
        )
