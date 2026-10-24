"""Fixtures for vision-based camera verification tests."""

import pytest

# OpenCV is the optional `vision` extra. conftest is imported during
# collection, which happens BEFORE the `-m 'not vision'` in addopts can
# deselect anything — so importing cv2 directly here turned "these tests are
# deselected" into "collection failed" on any machine without the extra.
# importorskip skips this directory cleanly instead.
cv2 = pytest.importorskip(
    "cv2", reason="vision tests need the optional 'vision' extra (opencv-python)"
)

from bcc950.controller import BCC950Controller  # noqa: E402
from bcc950.v4l2_backend import SubprocessV4L2Backend  # noqa: E402

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

    # Minimize internal frame buffer so reads return current frames
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
