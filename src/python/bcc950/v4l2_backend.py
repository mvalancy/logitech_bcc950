"""V4L2 backend protocol and subprocess implementation."""

from __future__ import annotations

import subprocess
from typing import Protocol, runtime_checkable


@runtime_checkable
class V4L2Backend(Protocol):
    """Protocol defining the V4L2 control interface.

    This is the mockable boundary for testing.
    """

    def set_control(self, device: str, control: str, value: int) -> None:
        """Set a V4L2 control to a specific value."""
        ...

    def get_control(self, device: str, control: str) -> int:
        """Get the current value of a V4L2 control."""
        ...

    def list_controls(self, device: str) -> str:
        """List available controls for a device."""
        ...

    def list_devices(self) -> str:
        """List all V4L2 devices."""
        ...


class SubprocessV4L2Backend:
    """V4L2 backend using subprocess calls to v4l2-ctl.

    Uses list args (no shell=True) for security.
    """

    def set_control(self, device: str, control: str, value: int) -> None:
        subprocess.run(
            ["v4l2-ctl", "-d", device, "-c", f"{control}={value}"],
            check=True,
            capture_output=True,
            text=True,
        )

    def get_control(self, device: str, control: str) -> int:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, f"--get-ctrl={control}"],
            check=True,
            capture_output=True,
            text=True,
        )
        # Output format: "control_name: value" or "control_name=value"
        output = result.stdout.strip()
        for sep in (":", "="):
            if sep in output:
                return int(output.split(sep)[-1].strip())
        raise ValueError(f"Unexpected v4l2-ctl output: {output}")

    def list_controls(self, device: str) -> str:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "--list-ctrls"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def list_devices(self) -> str:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
