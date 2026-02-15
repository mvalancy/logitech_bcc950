"""Unit tests for Config."""

import pytest

from bcc950.config import Config
from bcc950.constants import (
    DEFAULT_DEVICE,
    DEFAULT_PAN_SPEED,
    DEFAULT_TILT_SPEED,
    DEFAULT_ZOOM_STEP,
)


# ---------------------------------------------------------------------------
# Load / Save round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_save_then_load_preserves_values(self, tmp_path):
        path = tmp_path / "config"

        cfg1 = Config(path)
        cfg1.device = "/dev/video5"
        cfg1.pan_speed = 3
        cfg1.tilt_speed = 2
        cfg1.zoom_step = 25
        cfg1.save()

        cfg2 = Config(path)
        cfg2.load()

        assert cfg2.device == "/dev/video5"
        assert cfg2.pan_speed == 3
        assert cfg2.tilt_speed == 2
        assert cfg2.zoom_step == 25

    def test_round_trip_defaults(self, tmp_path):
        """Saving defaults and loading should give back defaults."""
        path = tmp_path / "config"

        cfg1 = Config(path)
        cfg1.save()

        cfg2 = Config(path)
        cfg2.load()

        assert cfg2.device == DEFAULT_DEVICE
        assert cfg2.pan_speed == DEFAULT_PAN_SPEED
        assert cfg2.tilt_speed == DEFAULT_TILT_SPEED
        assert cfg2.zoom_step == DEFAULT_ZOOM_STEP

    def test_save_and_reload_multiple_times(self, tmp_path):
        """Multiple save/load cycles should not corrupt data."""
        path = tmp_path / "config"

        for i in range(3):
            cfg = Config(path)
            cfg.load()
            cfg.pan_speed = i + 1
            cfg.save()

        final = Config(path)
        final.load()
        assert final.pan_speed == 3


# ---------------------------------------------------------------------------
# Missing file handling
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_load_missing_file_uses_defaults(self, tmp_path):
        path = tmp_path / "nonexistent_config"
        cfg = Config(path)
        cfg.load()

        assert cfg.device == DEFAULT_DEVICE
        assert cfg.pan_speed == DEFAULT_PAN_SPEED
        assert cfg.tilt_speed == DEFAULT_TILT_SPEED
        assert cfg.zoom_step == DEFAULT_ZOOM_STEP

    def test_load_missing_file_does_not_raise(self, tmp_path):
        path = tmp_path / "missing"
        cfg = Config(path)
        cfg.load()  # Should not raise


# ---------------------------------------------------------------------------
# Integer parsing
# ---------------------------------------------------------------------------

class TestIntegerParsing:
    def test_int_keys_parsed_as_int(self, tmp_path):
        path = tmp_path / "config"
        path.write_text("PAN_SPEED=5\nTILT_SPEED=3\nZOOM_STEP=20\n")

        cfg = Config(path)
        cfg.load()

        assert isinstance(cfg.pan_speed, int)
        assert isinstance(cfg.tilt_speed, int)
        assert isinstance(cfg.zoom_step, int)
        assert cfg.pan_speed == 5
        assert cfg.tilt_speed == 3
        assert cfg.zoom_step == 20

    def test_device_parsed_as_string(self, tmp_path):
        path = tmp_path / "config"
        path.write_text("DEVICE=/dev/video3\n")

        cfg = Config(path)
        cfg.load()

        assert isinstance(cfg.device, str)
        assert cfg.device == "/dev/video3"

    def test_comments_and_whitespace_ignored(self, tmp_path):
        path = tmp_path / "config"
        path.write_text(
            "# This is a comment\n"
            "  \n"
            "PAN_SPEED = 7\n"
            "# Another comment\n"
            "TILT_SPEED = 4\n"
        )

        cfg = Config(path)
        cfg.load()

        assert cfg.pan_speed == 7
        assert cfg.tilt_speed == 4

    def test_unknown_keys_ignored(self, tmp_path):
        path = tmp_path / "config"
        path.write_text("UNKNOWN_KEY=999\nPAN_SPEED=2\n")

        cfg = Config(path)
        cfg.load()

        assert cfg.pan_speed == 2
        assert cfg.get("UNKNOWN_KEY") is None

    def test_get_and_set(self, tmp_path):
        path = tmp_path / "config"
        cfg = Config(path)
        cfg.set("PAN_SPEED", 42)
        assert cfg.get("PAN_SPEED") == 42

    def test_get_default(self, tmp_path):
        path = tmp_path / "config"
        cfg = Config(path)
        assert cfg.get("NONEXISTENT", "fallback") == "fallback"
