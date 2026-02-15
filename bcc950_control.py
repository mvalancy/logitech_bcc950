#!/usr/bin/env python3
"""
Logitech BCC950 Camera Control Script (Legacy Entrypoint)

This script is preserved for backward compatibility. For new usage,
install the package from src/python/ and use:

    bcc950 --help

Or import directly:

    from bcc950 import BCC950Controller

Author: Matthew Valancy
"""

import sys
from pathlib import Path

# Add the new package to the path
_pkg_dir = Path(__file__).parent / "src" / "python"
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

from bcc950.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
