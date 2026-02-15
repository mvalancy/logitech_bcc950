"""Configuration file management for BCC950."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_DEVICE,
    DEFAULT_PAN_SPEED,
    DEFAULT_TILT_SPEED,
    DEFAULT_ZOOM_STEP,
)


class Config:
    """Manages BCC950 configuration load/save from ~/.bcc950_config."""

    DEFAULTS: dict[str, Any] = {
        "DEVICE": DEFAULT_DEVICE,
        "PAN_SPEED": DEFAULT_PAN_SPEED,
        "TILT_SPEED": DEFAULT_TILT_SPEED,
        "ZOOM_STEP": DEFAULT_ZOOM_STEP,
    }

    INT_KEYS = {"PAN_SPEED", "TILT_SPEED", "ZOOM_STEP"}

    def __init__(self, config_path: Path | None = None):
        self.path = config_path or (Path.home() / DEFAULT_CONFIG_FILENAME)
        self._data: dict[str, Any] = dict(self.DEFAULTS)

    @property
    def device(self) -> str:
        return self._data["DEVICE"]

    @device.setter
    def device(self, value: str) -> None:
        self._data["DEVICE"] = value

    @property
    def pan_speed(self) -> int:
        return self._data["PAN_SPEED"]

    @pan_speed.setter
    def pan_speed(self, value: int) -> None:
        self._data["PAN_SPEED"] = value

    @property
    def tilt_speed(self) -> int:
        return self._data["TILT_SPEED"]

    @tilt_speed.setter
    def tilt_speed(self, value: int) -> None:
        self._data["TILT_SPEED"] = value

    @property
    def zoom_step(self) -> int:
        return self._data["ZOOM_STEP"]

    @zoom_step.setter
    def zoom_step(self, value: int) -> None:
        self._data["ZOOM_STEP"] = value

    def load(self) -> None:
        """Load config from file. Missing file is silently ignored."""
        if not self.path.exists():
            return
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key in self._data:
                        if key in self.INT_KEYS:
                            self._data[key] = int(value)
                        else:
                            self._data[key] = value

    def save(self) -> None:
        """Save current config to file."""
        with open(self.path, "w") as f:
            for key, value in self._data.items():
                f.write(f"{key}={value}\n")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
