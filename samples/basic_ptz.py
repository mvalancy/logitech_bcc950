#!/usr/bin/env python3
"""Basic PTZ control demo using the default subprocess backend.

Auto-detects the BCC950 camera, then runs through pan/tilt/zoom
movements. No C++ build required — uses v4l2-ctl under the hood.

Usage:
    python samples/basic_ptz.py
    python samples/basic_ptz.py --device /dev/video2
"""

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from bcc950 import BCC950Controller


def main() -> None:
    parser = argparse.ArgumentParser(description="BCC950 basic PTZ demo")
    parser.add_argument("--device", default=None, help="V4L2 device path")
    args = parser.parse_args()

    ctrl = BCC950Controller(device=args.device)
    if args.device is None:
        found = ctrl.find_camera()
        if not found:
            print("Could not auto-detect BCC950. Use --device /dev/videoN")
            sys.exit(1)
        print(f"Found camera: {found}")

    print("Resetting to home position...")
    ctrl.reset_position()
    time.sleep(1)

    print("Pan left...")
    ctrl.pan_left(duration=0.3)
    time.sleep(0.5)

    print("Pan right...")
    ctrl.pan_right(duration=0.6)
    time.sleep(0.5)

    print("Return to center...")
    ctrl.pan_left(duration=0.3)
    time.sleep(0.5)

    print("Tilt up...")
    ctrl.tilt_up(duration=0.3)
    time.sleep(0.5)

    print("Tilt down...")
    ctrl.tilt_down(duration=0.6)
    time.sleep(0.5)

    print("Return to center...")
    ctrl.tilt_up(duration=0.3)
    time.sleep(0.5)

    zoom = ctrl.get_zoom()
    print(f"Current zoom: {zoom}")
    print("Zoom in (3 steps)...")
    for _ in range(3):
        ctrl.zoom_in()
    time.sleep(0.5)
    print(f"Zoom now: {ctrl.get_zoom()}")

    print("Zoom out (3 steps)...")
    for _ in range(3):
        ctrl.zoom_out()
    time.sleep(0.5)
    print(f"Zoom now: {ctrl.get_zoom()}")

    print("Reset to home...")
    ctrl.reset_position()
    print("Done!")


if __name__ == "__main__":
    main()
