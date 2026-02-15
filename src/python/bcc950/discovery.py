"""Camera detection and OS discovery for BCC950."""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

from .v4l2_backend import V4L2Backend


def detect_os() -> str:
    """Detect the current operating system ID."""
    os_release = Path("/etc/os-release")
    if os_release.exists():
        with open(os_release) as f:
            for line in f:
                if line.startswith("ID="):
                    return line.split("=")[1].strip().strip('"')
    return platform.system().lower()


def find_bcc950(backend: V4L2Backend) -> str | None:
    """Find the BCC950 camera device path.

    Returns the device path if found, None otherwise.
    """
    try:
        devices_output = backend.list_devices()
    except Exception:
        return None

    # Try to find BCC950 by name
    if "BCC950" in devices_output:
        match = re.search(
            r"BCC950.*?\n(.*?/dev/video\d+)", devices_output, re.DOTALL
        )
        if match:
            return match.group(1).strip()

    # Fall back to checking all video devices for PTZ support
    return _find_ptz_device(backend)


def _find_ptz_device(backend: V4L2Backend) -> str | None:
    """Find any video device with PTZ support."""
    video_devices = sorted(
        str(p) for p in Path("/dev").glob("video*")
    )
    for dev in video_devices:
        try:
            controls = backend.list_controls(dev)
            if "pan_speed" in controls:
                return dev
        except Exception:
            continue
    return None


def has_ptz_support(backend: V4L2Backend, device: str) -> bool:
    """Check if a device supports pan, tilt, and zoom controls."""
    if not os.path.exists(device):
        return False
    try:
        controls = backend.list_controls(device)
        return all(
            ctrl in controls
            for ctrl in ("pan_speed", "tilt_speed", "zoom_absolute")
        )
    except Exception:
        return False
