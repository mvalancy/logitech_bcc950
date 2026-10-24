"""Logitech BCC950 camera control library."""

from typing import TYPE_CHECKING

from .controller import BCC950Controller
from .position import PositionTracker
from .v4l2_backend import SubprocessV4L2Backend, V4L2Backend

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from .motion_verify import MotionVerifier

__all__ = [
    "BCC950Controller",
    "MotionVerifier",
    "PositionTracker",
    "SubprocessV4L2Backend",
    "V4L2Backend",
]


def __getattr__(name: str):
    """Resolve MotionVerifier lazily so OpenCV stays genuinely optional.

    motion_verify imports cv2 at module level, and OpenCV is declared as the
    optional `vision` extra in pyproject.toml. Importing MotionVerifier eagerly
    here made that extra mandatory in practice: `import bcc950` raised
    ModuleNotFoundError: No module named 'cv2' unless it was installed, which
    also blocked the default test run that deliberately excludes vision tests.

    controller.py and motion.py already keep cv2 behind TYPE_CHECKING and a
    function-level import; this brings the package root in line with them.
    `from bcc950 import MotionVerifier` still works wherever OpenCV is present.
    """
    if name == "MotionVerifier":
        from .motion_verify import MotionVerifier

        return MotionVerifier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
