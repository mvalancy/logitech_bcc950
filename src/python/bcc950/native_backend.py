"""Native C++ backend via pybind11 bindings (optional).

Falls back gracefully if the native module is not available.
"""

from __future__ import annotations

_NATIVE_AVAILABLE = False

try:
    import _bcc950_native

    _NATIVE_AVAILABLE = True
except ImportError:
    _bcc950_native = None  # type: ignore[assignment]


def is_available() -> bool:
    """Check if the native C++ backend is available."""
    return _NATIVE_AVAILABLE


class NativeV4L2Backend:
    """V4L2 backend using the C++ pybind11 module.

    Only usable when _bcc950_native is importable.
    """

    def __init__(self) -> None:
        if not _NATIVE_AVAILABLE:
            raise RuntimeError(
                "Native backend not available. "
                "Build with BUILD_PYTHON_BINDINGS=ON."
            )
        self._device_handles: dict[str, object] = {}

    def _get_device(self, device: str) -> object:
        if device not in self._device_handles:
            self._device_handles[device] = _bcc950_native.V4L2Device(device)
        return self._device_handles[device]

    def set_control(self, device: str, control: str, value: int) -> None:
        dev = self._get_device(device)
        dev.set_control(control, value)  # type: ignore[union-attr]

    def get_control(self, device: str, control: str) -> int:
        dev = self._get_device(device)
        return dev.get_control(control)  # type: ignore[union-attr]

    def list_controls(self, device: str) -> str:
        dev = self._get_device(device)
        return dev.list_controls()  # type: ignore[union-attr]

    def list_devices(self) -> str:
        return _bcc950_native.list_devices()  # type: ignore[union-attr]
