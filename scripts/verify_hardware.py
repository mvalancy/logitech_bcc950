#!/usr/bin/env python3
"""Hardware verification script for the Logitech BCC950.

Proves the camera physically works by running a PTZ choreography,
capturing a frame, and reporting pass/fail for each step.

Usage:
    python scripts/verify_hardware.py
    python scripts/verify_hardware.py --device /dev/video0
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Ensure bcc950 package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))


def main() -> None:
    parser = argparse.ArgumentParser(description="BCC950 Hardware Verification")
    parser.add_argument("--device", default=None, help="V4L2 device path (auto-detect if omitted)")
    args = parser.parse_args()

    results: list[tuple[str, bool, str]] = []

    def check(name: str, passed: bool, detail: str = "") -> bool:
        results.append((name, passed, detail))
        status = "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
        line = f"  [{status}] {name}"
        if detail:
            line += f"  ({detail})"
        print(line)
        return passed

    print("=" * 50)
    print("  BCC950 Hardware Verification")
    print("=" * 50)
    print()

    # Step 1: Import bcc950
    try:
        from bcc950 import BCC950Controller
        check("Import bcc950 package", True)
    except ImportError as e:
        check("Import bcc950 package", False, str(e))
        print("\nInstall with: pip install -e src/python/")
        sys.exit(1)

    # Step 2: Create controller and find camera
    try:
        cam = BCC950Controller(device=args.device)
        if args.device is None:
            device = cam.find_camera()
            if device:
                check("Auto-detect camera", True, device)
            else:
                check("Auto-detect camera", False, "not found")
                print("\nSpecify device: --device /dev/videoN")
                sys.exit(1)
        else:
            check("Camera device", True, args.device)
    except Exception as e:
        check("Create controller", False, str(e))
        sys.exit(1)

    # Step 3: Check PTZ support
    try:
        has_ptz = cam.has_ptz_support()
        check("PTZ support", has_ptz, "pan_speed, tilt_speed, zoom_absolute")
    except Exception as e:
        check("PTZ support", False, str(e))

    # Step 4: List devices
    try:
        devices_output = cam.list_devices()
        has_devices = len(devices_output.strip()) > 0
        check("List V4L2 devices", has_devices)
    except Exception as e:
        check("List V4L2 devices", False, str(e))

    # Step 5: PTZ choreography
    print()
    print("  Running PTZ choreography...")
    print()

    # Pan left
    try:
        cam.pan_left(0.5)
        time.sleep(0.3)
        check("Pan left (0.5s)", True)
    except Exception as e:
        check("Pan left", False, str(e))

    # Pan right
    try:
        cam.pan_right(0.5)
        time.sleep(0.3)
        check("Pan right (0.5s)", True)
    except Exception as e:
        check("Pan right", False, str(e))

    # Tilt up
    try:
        cam.tilt_up(0.3)
        time.sleep(0.3)
        check("Tilt up (0.3s)", True)
    except Exception as e:
        check("Tilt up", False, str(e))

    # Tilt down
    try:
        cam.tilt_down(0.3)
        time.sleep(0.3)
        check("Tilt down (0.3s)", True)
    except Exception as e:
        check("Tilt down", False, str(e))

    # Zoom in
    try:
        cam.zoom_to(300)
        time.sleep(0.5)
        check("Zoom to 300", True)
    except Exception as e:
        check("Zoom to 300", False, str(e))

    # Zoom out
    try:
        cam.zoom_to(100)
        time.sleep(0.3)
        check("Zoom to 100 (reset)", True)
    except Exception as e:
        check("Zoom to 100", False, str(e))

    # Combined move
    try:
        cam.move(pan_dir=-1, tilt_dir=1, duration=0.3)
        time.sleep(0.2)
        cam.move(pan_dir=1, tilt_dir=-1, duration=0.3)
        check("Combined pan+tilt move", True)
    except Exception as e:
        check("Combined move", False, str(e))

    # Step 6: Frame capture via OpenCV
    print()
    try:
        import cv2
        cap = cv2.VideoCapture(cam.device)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                out_path = "/tmp/bcc950_test.jpg"
                cv2.imwrite(out_path, frame)
                check("Capture frame via OpenCV", True, f"{w}x{h} saved to {out_path}")
            else:
                check("Capture frame via OpenCV", False, "read() returned empty")
        else:
            check("Capture frame via OpenCV", False, f"could not open {cam.device}")
    except ImportError:
        check("Capture frame via OpenCV", False, "opencv-python not installed")
    except Exception as e:
        check("Capture frame via OpenCV", False, str(e))

    # Step 7: Read zoom from hardware
    try:
        zoom_val = cam.get_zoom()
        check("Read zoom value from hardware", True, f"zoom={zoom_val}")
    except Exception as e:
        check("Read zoom from hardware", False, str(e))

    # Summary
    print()
    print("=" * 50)
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    failed = total - passed
    if failed == 0:
        print(f"  \033[32mAll {total} checks passed!\033[0m")
    else:
        print(f"  {passed}/{total} passed, \033[31m{failed} failed\033[0m")
    print("=" * 50)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
