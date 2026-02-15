"""Top-level conftest for BCC950 test suite."""

import pytest
from unittest.mock import MagicMock

from bcc950.v4l2_backend import V4L2Backend
from bcc950.controller import BCC950Controller


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Run tests that require physical BCC950 hardware",
    )
    parser.addoption(
        "--run-vision",
        action="store_true",
        default=False,
        help="Run tests that require camera vision / OpenCV",
    )
    parser.addoption(
        "--device",
        action="store",
        default="/dev/video0",
        help="V4L2 device path for hardware/vision tests (default: /dev/video0)",
    )


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: requires physical BCC950 camera")
    config.addinivalue_line("markers", "vision: requires camera feed / OpenCV")
    config.addinivalue_line("markers", "slow: marks tests as slow-running")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-hardware"):
        skip_hw = pytest.mark.skip(reason="need --run-hardware option to run")
        for item in items:
            if "hardware" in item.keywords:
                item.add_marker(skip_hw)

    if not config.getoption("--run-vision"):
        skip_vis = pytest.mark.skip(reason="need --run-vision option to run")
        for item in items:
            if "vision" in item.keywords:
                item.add_marker(skip_vis)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_backend():
    """Return a MagicMock that satisfies the V4L2Backend protocol."""
    backend = MagicMock(spec=V4L2Backend)
    return backend


@pytest.fixture
def controller(mock_backend, tmp_path):
    """Return a BCC950Controller wired to a mock backend with temp files."""
    config_path = tmp_path / "test_config"
    presets_path = tmp_path / "test_presets.json"
    return BCC950Controller(
        device="/dev/video99",
        backend=mock_backend,
        config_path=config_path,
        presets_path=presets_path,
    )
