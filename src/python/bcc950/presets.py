"""Named preset save/recall for BCC950 positions."""

from __future__ import annotations

import json
from pathlib import Path

from .constants import DEFAULT_PRESETS_FILENAME
from .position import PositionTracker


class PresetManager:
    """JSON-based named preset storage for camera positions."""

    def __init__(self, presets_path: Path | None = None):
        self.path = presets_path or (Path.home() / DEFAULT_PRESETS_FILENAME)
        self._presets: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        """Load presets from JSON file."""
        if self.path.exists():
            with open(self.path) as f:
                self._presets = json.load(f)

    def save(self) -> None:
        """Persist presets to JSON file."""
        with open(self.path, "w") as f:
            json.dump(self._presets, f, indent=2)

    def save_preset(self, name: str, position: PositionTracker) -> None:
        """Save a named preset from current position."""
        self._presets[name] = {
            "pan": position.pan,
            "tilt": position.tilt,
            "zoom": position.zoom,
        }
        self.save()

    def recall_preset(self, name: str) -> PositionTracker | None:
        """Recall a named preset. Returns None if not found."""
        data = self._presets.get(name)
        if data is None:
            return None
        return PositionTracker(
            pan=data["pan"],
            tilt=data["tilt"],
            zoom=data["zoom"],
        )

    def delete_preset(self, name: str) -> bool:
        """Delete a named preset. Returns True if it existed."""
        if name in self._presets:
            del self._presets[name]
            self.save()
            return True
        return False

    def list_presets(self) -> list[str]:
        """Return list of preset names."""
        return list(self._presets.keys())

    def get_all(self) -> dict[str, dict]:
        """Return all presets as a dict."""
        return dict(self._presets)
