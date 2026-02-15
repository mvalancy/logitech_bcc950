"""Fixtures for vision-based camera verification tests."""

import pytest
import cv2

from bcc950.controller import BCC950Controller
from bcc950.v4l2_backend import SubprocessV4L2Backend

WARMUP_FRAMES = 10


@pytest.fixture
def camera_capture(request):
    """OpenCV VideoCapture fixture with warmup frames.

    Opens the device specified by --device, reads and discards warmup
    frames so auto-exposure and white-balance can settle, then yields
    the capture object. Releases on teardown.
    """
    device = request.config.getoption("--device")
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        pytest.skip(f"Cannot open video device {device}")

    # Discard warmup frames to let auto-exposure settle
    for _ in range(WARMUP_FRAMES):
        cap.read()

    yield cap

    cap.release()


@pytest.fixture
def hardware_controller(request):
    """BCC950Controller fixture connected to real hardware."""
    device = request.config.getoption("--device")
    backend = SubprocessV4L2Backend()
    return BCC950Controller(device=device, backend=backend)
