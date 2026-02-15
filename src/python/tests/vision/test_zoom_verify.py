"""Vision-based verification tests for zoom movement.

These tests use ORB feature matching and inter-feature distance analysis
to confirm that the camera actually zoomed when zoom commands are issued.

Run with: pytest --run-vision --device /dev/videoN
"""

import time

import cv2
import numpy as np
import pytest

from .cv_utils import compute_frame_difference, estimate_fov_change

ZOOM_SETTLE_TIME = 0.5
MIN_FOV_RATIO_ZOOM_IN = 1.05
MAX_FOV_RATIO_ZOOM_OUT = 0.95
MIN_FRAME_DIFF = 5.0


@pytest.mark.vision
class TestZoomInFOV:
    """Zooming in should cause features to spread apart."""

    def test_zoom_in_fov_change(self, camera_capture, hardware_controller):
        # Set zoom to a known baseline
        hardware_controller.zoom_to(100)
        time.sleep(ZOOM_SETTLE_TIME)

        # Capture before
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before zoom"
        gray_before = cv2.cvtColor(frame_before, cv2.COLOR_BGR2GRAY)

        # Zoom in
        hardware_controller.zoom_to(200)
        time.sleep(ZOOM_SETTLE_TIME)

        # Capture after
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after zoom"
        gray_after = cv2.cvtColor(frame_after, cv2.COLOR_BGR2GRAY)

        # ORB feature spread ratio: > 1.0 means features spread out (zoom in)
        ratio = estimate_fov_change(gray_before, gray_after)
        assert ratio > MIN_FOV_RATIO_ZOOM_IN, (
            f"Expected FOV change ratio > {MIN_FOV_RATIO_ZOOM_IN} for zoom-in, "
            f"got ratio={ratio:.4f}"
        )


@pytest.mark.vision
class TestZoomOutFOV:
    """Zooming out should cause features to come closer together."""

    def test_zoom_out_fov_change(self, camera_capture, hardware_controller):
        # Set zoom to a higher baseline
        hardware_controller.zoom_to(200)
        time.sleep(ZOOM_SETTLE_TIME)

        # Capture before
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before zoom"
        gray_before = cv2.cvtColor(frame_before, cv2.COLOR_BGR2GRAY)

        # Zoom out
        hardware_controller.zoom_to(100)
        time.sleep(ZOOM_SETTLE_TIME)

        # Capture after
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after zoom"
        gray_after = cv2.cvtColor(frame_after, cv2.COLOR_BGR2GRAY)

        # ORB feature spread ratio: < 1.0 means features came closer (zoom out)
        ratio = estimate_fov_change(gray_before, gray_after)
        assert ratio < MAX_FOV_RATIO_ZOOM_OUT, (
            f"Expected FOV change ratio < {MAX_FOV_RATIO_ZOOM_OUT} for zoom-out, "
            f"got ratio={ratio:.4f}"
        )


@pytest.mark.vision
class TestZoomFrameDifference:
    """Zooming should produce a visible change in the image."""

    def test_zoom_frame_difference(self, camera_capture, hardware_controller):
        # Start at baseline zoom
        hardware_controller.zoom_to(100)
        time.sleep(ZOOM_SETTLE_TIME)

        # Capture before
        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before zoom"

        # Zoom in significantly
        hardware_controller.zoom_to(300)
        time.sleep(ZOOM_SETTLE_TIME)

        # Capture after
        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after zoom"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected mean pixel difference > {MIN_FRAME_DIFF} after zoom, "
            f"got {mean_diff:.2f}"
        )
