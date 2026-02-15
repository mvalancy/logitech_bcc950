"""Integration tests for basic BCC950 camera operations.

These tests require a physical BCC950 camera connected to the system.
Run with: pytest --run-hardware --device /dev/videoN
"""

import pytest

from bcc950.controller import BCC950Controller
from bcc950.v4l2_backend import SubprocessV4L2Backend


@pytest.fixture
def hw_controller(request):
    """Create a BCC950Controller connected to real hardware."""
    device = request.config.getoption("--device")
    backend = SubprocessV4L2Backend()
    return BCC950Controller(device=device, backend=backend)


@pytest.mark.hardware
class TestPanTiltNoRaise:
    """Verify that basic pan/tilt commands execute without raising."""

    def test_pan_left_no_raise(self, hw_controller):
        hw_controller.pan_left(duration=0.3)

    def test_pan_right_no_raise(self, hw_controller):
        hw_controller.pan_right(duration=0.3)

    def test_tilt_up_no_raise(self, hw_controller):
        hw_controller.tilt_up(duration=0.3)

    def test_tilt_down_no_raise(self, hw_controller):
        hw_controller.tilt_down(duration=0.3)


@pytest.mark.hardware
class TestZoom:
    """Verify zoom operations against real hardware."""

    def test_zoom_in_increases_value(self, hw_controller):
        # Reset zoom to minimum first
        hw_controller.zoom_to(100)
        before = hw_controller.get_zoom()
        hw_controller.zoom_in()
        after = hw_controller.get_zoom()
        assert after > before, (
            f"Expected zoom to increase after zoom_in, "
            f"but got before={before}, after={after}"
        )


@pytest.mark.hardware
class TestDiscovery:
    """Verify PTZ support detection on real hardware."""

    def test_has_ptz_support(self, hw_controller):
        assert hw_controller.has_ptz_support() is True


@pytest.mark.hardware
class TestCombinedMove:
    """Verify combined pan+tilt movement."""

    def test_combined_move(self, hw_controller):
        # Combined pan-left + tilt-up should not raise
        hw_controller.move(pan_dir=-1, tilt_dir=1, duration=0.3)
