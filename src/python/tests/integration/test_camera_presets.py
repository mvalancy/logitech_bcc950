"""Integration tests for BCC950 preset save/recall on real hardware.

These tests require a physical BCC950 camera connected to the system.
Run with: pytest --run-hardware --device /dev/videoN
"""

import pytest

from bcc950.controller import BCC950Controller
from bcc950.v4l2_backend import SubprocessV4L2Backend


@pytest.fixture
def hw_controller(request, tmp_path):
    """Create a BCC950Controller connected to real hardware with temp presets."""
    device = request.config.getoption("--device")
    backend = SubprocessV4L2Backend()
    presets_path = tmp_path / "test_presets.json"
    return BCC950Controller(
        device=device,
        backend=backend,
        presets_path=presets_path,
    )


@pytest.mark.hardware
class TestPresets:
    """Verify preset save and recall on real hardware."""

    def test_save_and_recall_preset(self, hw_controller):
        # Move to a known zoom position and save
        hw_controller.zoom_to(200)
        hw_controller.save_preset("test_pos")

        # Move away
        hw_controller.zoom_to(100)

        # Recall should succeed and restore zoom
        result = hw_controller.recall_preset("test_pos")
        assert result is True

        zoom_after = hw_controller.get_zoom()
        assert zoom_after == 200, (
            f"Expected zoom=200 after recalling preset, got {zoom_after}"
        )

    def test_list_presets(self, hw_controller):
        # Initially empty
        assert hw_controller.list_presets() == []

        # Save a couple of presets
        hw_controller.zoom_to(150)
        hw_controller.save_preset("pos_a")

        hw_controller.zoom_to(250)
        hw_controller.save_preset("pos_b")

        presets = hw_controller.list_presets()
        assert "pos_a" in presets
        assert "pos_b" in presets
        assert len(presets) == 2
