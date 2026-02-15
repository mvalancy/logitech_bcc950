"""Unit tests for PresetManager."""

import json
import pytest

from bcc950.presets import PresetManager
from bcc950.position import PositionTracker


# ---------------------------------------------------------------------------
# Save / Recall
# ---------------------------------------------------------------------------

class TestSaveRecall:
    def test_save_and_recall(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        pos = PositionTracker(pan=1.0, tilt=-0.5, zoom=200)
        pm.save_preset("home", pos)

        recalled = pm.recall_preset("home")
        assert recalled is not None
        assert recalled.pan == pytest.approx(1.0)
        assert recalled.tilt == pytest.approx(-0.5)
        assert recalled.zoom == 200

    def test_recall_nonexistent_returns_none(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        assert pm.recall_preset("nope") is None

    def test_save_overwrites_existing(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        pm.save_preset("spot", PositionTracker(pan=1.0, tilt=0.0, zoom=100))
        pm.save_preset("spot", PositionTracker(pan=2.0, tilt=1.0, zoom=300))

        recalled = pm.recall_preset("spot")
        assert recalled is not None
        assert recalled.pan == pytest.approx(2.0)
        assert recalled.tilt == pytest.approx(1.0)
        assert recalled.zoom == 300


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_existing(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        pm.save_preset("temp", PositionTracker())
        assert pm.delete_preset("temp") is True
        assert pm.recall_preset("temp") is None

    def test_delete_nonexistent(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        assert pm.delete_preset("nope") is False


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestList:
    def test_list_empty(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        assert pm.list_presets() == []

    def test_list_after_saves(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        pm.save_preset("a", PositionTracker())
        pm.save_preset("b", PositionTracker())
        pm.save_preset("c", PositionTracker())
        assert sorted(pm.list_presets()) == ["a", "b", "c"]

    def test_list_after_delete(self, tmp_path):
        pm = PresetManager(tmp_path / "presets.json")
        pm.save_preset("keep", PositionTracker())
        pm.save_preset("remove", PositionTracker())
        pm.delete_preset("remove")
        assert pm.list_presets() == ["keep"]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_survives_new_instance(self, tmp_path):
        """Presets saved by one manager instance should be loadable by another."""
        path = tmp_path / "presets.json"

        pm1 = PresetManager(path)
        pm1.save_preset("office", PositionTracker(pan=2.0, tilt=1.0, zoom=250))

        # Create a completely new manager instance pointing at the same file
        pm2 = PresetManager(path)
        recalled = pm2.recall_preset("office")
        assert recalled is not None
        assert recalled.pan == pytest.approx(2.0)
        assert recalled.tilt == pytest.approx(1.0)
        assert recalled.zoom == 250

    def test_file_is_valid_json(self, tmp_path):
        """The presets file should be valid JSON."""
        path = tmp_path / "presets.json"
        pm = PresetManager(path)
        pm.save_preset("test", PositionTracker(pan=0.5, tilt=-0.5, zoom=150))

        with open(path) as f:
            data = json.load(f)

        assert "test" in data
        assert data["test"]["pan"] == pytest.approx(0.5)
        assert data["test"]["tilt"] == pytest.approx(-0.5)
        assert data["test"]["zoom"] == 150

    def test_delete_persists(self, tmp_path):
        """Deleting a preset should persist the deletion to disk."""
        path = tmp_path / "presets.json"

        pm1 = PresetManager(path)
        pm1.save_preset("gone", PositionTracker())
        pm1.delete_preset("gone")

        pm2 = PresetManager(path)
        assert pm2.recall_preset("gone") is None
        assert "gone" not in pm2.list_presets()

    def test_multiple_presets_persist(self, tmp_path):
        path = tmp_path / "presets.json"

        pm1 = PresetManager(path)
        pm1.save_preset("p1", PositionTracker(pan=1.0, tilt=0.0, zoom=100))
        pm1.save_preset("p2", PositionTracker(pan=-1.0, tilt=2.0, zoom=400))

        pm2 = PresetManager(path)
        assert sorted(pm2.list_presets()) == ["p1", "p2"]
        r1 = pm2.recall_preset("p1")
        r2 = pm2.recall_preset("p2")
        assert r1.pan == pytest.approx(1.0)
        assert r2.pan == pytest.approx(-1.0)
        assert r2.zoom == 400
