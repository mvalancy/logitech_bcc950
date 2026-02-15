"""Vision-based verification tests for zoom movement.

These tests verify that zoom commands actually change the hardware zoom
level and produce visible frame changes.

Run with: pytest --run-vision --device /dev/videoN
"""

import time

import cv2
import pytest

from .cv_utils import compute_frame_difference, flush_buffer

ZOOM_SETTLE_TIME = 1.0
MIN_FRAME_DIFF = 5.0


@pytest.mark.vision
class TestZoomInFOV:
    """Zooming in should change the hardware zoom value upward."""

    def test_zoom_in_fov_change(self, camera_capture, hardware_controller):
        # Set zoom to a known baseline
        hardware_controller.zoom_to(100)
        time.sleep(ZOOM_SETTLE_TIME)

        zoom_before = hardware_controller.get_zoom()

        # Zoom in
        hardware_controller.zoom_to(250)
        time.sleep(ZOOM_SETTLE_TIME)

        zoom_after = hardware_controller.get_zoom()

        assert zoom_after > zoom_before, (
            f"Expected zoom to increase, got before={zoom_before} after={zoom_after}"
        )


@pytest.mark.vision
class TestZoomOutFOV:
    """Zooming out should change the hardware zoom value downward."""

    def test_zoom_out_fov_change(self, camera_capture, hardware_controller):
        # Set zoom to a higher baseline
        hardware_controller.zoom_to(250)
        time.sleep(ZOOM_SETTLE_TIME)

        zoom_before = hardware_controller.get_zoom()

        # Zoom out
        hardware_controller.zoom_to(100)
        time.sleep(ZOOM_SETTLE_TIME)

        zoom_after = hardware_controller.get_zoom()

        assert zoom_after < zoom_before, (
            f"Expected zoom to decrease, got before={zoom_before} after={zoom_after}"
        )


@pytest.mark.vision
class TestZoomFrameDifference:
    """Zooming should produce a visible change in the image."""

    def test_zoom_frame_difference(self, camera_capture, hardware_controller):
        # Start at baseline zoom
        hardware_controller.zoom_to(100)
        time.sleep(ZOOM_SETTLE_TIME)
        flush_buffer(camera_capture)

        ret, frame_before = camera_capture.read()
        assert ret, "Failed to capture frame before zoom"

        # Zoom in significantly
        hardware_controller.zoom_to(300)
        time.sleep(ZOOM_SETTLE_TIME)
        flush_buffer(camera_capture)

        ret, frame_after = camera_capture.read()
        assert ret, "Failed to capture frame after zoom"

        mean_diff = compute_frame_difference(frame_before, frame_after)
        assert mean_diff > MIN_FRAME_DIFF, (
            f"Expected mean pixel difference > {MIN_FRAME_DIFF} after zoom, "
            f"got {mean_diff:.2f}"
        )
