#!/usr/bin/env python3
"""Auto-tune range of motion for the BCC950 camera.

Sweeps each axis (pan, tilt) to find the true mechanical limits using
phase correlation to detect camera motion. The motor runs continuously
while frames are sampled periodically — no jerky start-stop cycles.

Algorithm:
    1. Slam to one extreme (full left, continuous 10s)
    2. Start moving continuously in the opposite direction
    3. Sample frames every ~0.5s and compute phase correlation shift
    4. When shift drops to noise for 3 consecutive samples, camera hit limit
    5. Record total travel time; center = half of total
    6. Capture photos at extremes, corners, and center

Usage:
    python scripts/auto_tune.py
    python scripts/auto_tune.py --device /dev/video0
    python scripts/auto_tune.py --output calibration.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

try:
    import cv2
    import numpy as np
except ImportError:
    print("Error: OpenCV and NumPy are required.")
    print("Install them with:  pip install opencv-python numpy")
    sys.exit(1)

from bcc950 import BCC950Controller
from bcc950.constants import (
    CTRL_PAN_SPEED,
    CTRL_TILT_SPEED,
    ZOOM_MAX,
    ZOOM_MIN,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tuning parameters
SAMPLE_INTERVAL = 0.5     # seconds between frame samples during continuous movement
SHIFT_THRESHOLD = 3.0     # phase correlation shift (pixels) below this = stopped
CONSECUTIVE_STOPS = 3     # consecutive below-threshold samples to confirm limit
SLAM_DURATION = 10.0      # seconds to drive hard into a limit
WARMUP_FRAMES = 10        # frames to discard for auto-exposure
SETTLE_TIME = 0.5         # seconds to let camera settle after stopping


def capture_frame(cap: cv2.VideoCapture) -> np.ndarray:
    """Capture a single fresh frame."""
    # Flush stale buffer
    for _ in range(3):
        cap.read()
    ret, frame = cap.read()
    if not ret or frame is None:
        raise RuntimeError("Failed to capture frame")
    return frame


def capture_gray(cap: cv2.VideoCapture) -> np.ndarray:
    """Capture a grayscale frame."""
    return cv2.cvtColor(capture_frame(cap), cv2.COLOR_BGR2GRAY)


def save_photo(cap: cv2.VideoCapture, path: str, label: str) -> None:
    """Capture and save a photo."""
    time.sleep(SETTLE_TIME)
    frame = capture_frame(cap)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, frame)
    print(f"  Photo saved: {label} -> {os.path.relpath(path, PROJECT_ROOT)}")


def phase_shift(prev_gray: np.ndarray, curr_gray: np.ndarray, axis: str) -> float:
    """Estimate global camera shift between two frames using phase correlation.

    Returns shift in pixels along the axis ('pan' = horizontal, 'tilt' = vertical).
    """
    prev_f = prev_gray.astype(np.float64)
    curr_f = curr_gray.astype(np.float64)

    h, w = prev_gray.shape
    window = np.outer(np.hanning(h), np.hanning(w))
    prev_f *= window
    curr_f *= window

    (dx, dy), response = cv2.phaseCorrelate(prev_f, curr_f)
    return abs(dx) if axis == "pan" else abs(dy)


def set_speed(cam: BCC950Controller, control: str, value: int) -> None:
    """Set a raw V4L2 speed control directly (bypasses motion lock)."""
    cam._backend.set_control(cam.device, control, value)


def slam_to_limit(cam: BCC950Controller, control: str, speed: int, label: str) -> None:
    """Drive continuously into a mechanical limit."""
    print(f"  Slamming to {label} limit ({SLAM_DURATION}s)...")
    set_speed(cam, control, speed)
    time.sleep(SLAM_DURATION)
    set_speed(cam, control, 0)
    time.sleep(SETTLE_TIME)


def measure_continuous_sweep(
    cam: BCC950Controller,
    cap: cv2.VideoCapture,
    control: str,
    speed: int,
    axis: str,
    label: str,
) -> float:
    """Start continuous movement and sample frames until camera stops.

    The motor runs the entire time. We just capture frames periodically
    and check phase correlation to detect when movement has ceased.

    Returns total travel time in seconds.
    """
    print(f"  Sweeping {label} (continuous)...")
    stop_count = 0
    start_time = time.monotonic()

    # Start continuous movement
    set_speed(cam, control, speed)

    # Give motor a moment to get going
    time.sleep(0.3)

    prev_gray = capture_gray(cap)

    while True:
        time.sleep(SAMPLE_INTERVAL)
        curr_gray = capture_gray(cap)

        shift = phase_shift(prev_gray, curr_gray, axis)
        elapsed = time.monotonic() - start_time
        status = "MOVING" if shift >= SHIFT_THRESHOLD else "stopped"
        print(f"    {label}: {elapsed:.1f}s, shift={shift:.1f}px [{status}]")

        if shift < SHIFT_THRESHOLD:
            stop_count += 1
            if stop_count >= CONSECUTIVE_STOPS:
                break
        else:
            stop_count = 0

        prev_gray = curr_gray

        # Safety limit
        if elapsed > 45.0:
            print(f"  Safety limit reached at {elapsed:.1f}s")
            break

    # Stop the motor
    set_speed(cam, control, 0)
    total = time.monotonic() - start_time
    # Subtract the time spent confirming it was stopped
    actual = total - SAMPLE_INTERVAL * CONSECUTIVE_STOPS
    actual = max(0.0, actual)
    print(f"  Limit confirmed: {actual:.1f}s of travel")
    time.sleep(SETTLE_TIME)
    return actual


def go_to_center(cam: BCC950Controller, pan_total: float, tilt_total: float) -> None:
    """Move to center using measured ranges."""
    print("  Moving to center...")
    # Slam to left+down
    set_speed(cam, CTRL_PAN_SPEED, -1)
    set_speed(cam, CTRL_TILT_SPEED, -1)
    time.sleep(SLAM_DURATION)
    set_speed(cam, CTRL_PAN_SPEED, 0)
    set_speed(cam, CTRL_TILT_SPEED, 0)
    time.sleep(SETTLE_TIME)
    # Move half range to center
    set_speed(cam, CTRL_PAN_SPEED, 1)
    time.sleep(pan_total / 2)
    set_speed(cam, CTRL_PAN_SPEED, 0)
    set_speed(cam, CTRL_TILT_SPEED, 1)
    time.sleep(tilt_total / 2)
    set_speed(cam, CTRL_TILT_SPEED, 0)
    time.sleep(SETTLE_TIME)
    print("  At center.")


def run_auto_tune(device: str | None, output_path: str) -> dict:
    """Run the full auto-tune sequence."""
    cam = BCC950Controller(device=device)
    if device is None:
        found = cam.find_camera()
        if found:
            print(f"Auto-detected camera: {found}")
        else:
            print("Error: No BCC950 camera found.")
            sys.exit(1)

    cap = cv2.VideoCapture(cam.device)
    if not cap.isOpened():
        print(f"Error: Could not open video device {cam.device}")
        sys.exit(1)

    # Warmup
    print("Warming up camera...")
    for _ in range(WARMUP_FRAMES):
        cap.read()
    time.sleep(1.0)

    photos_dir = os.path.join(PROJECT_ROOT, "reports", "photos")
    os.makedirs(photos_dir, exist_ok=True)

    # Zoom to minimum for maximum FOV
    print("Setting zoom to minimum for maximum FOV...")
    cam.zoom_to(ZOOM_MIN)
    time.sleep(SETTLE_TIME)

    # =========================================
    # PHASE 1: Measure tilt range FIRST
    # (so camera ends at up-limit with good scene texture for pan)
    # =========================================
    print("\n=== Phase 1: Measure Tilt Range ===")
    slam_to_limit(cam, CTRL_TILT_SPEED, -1, "down")
    save_photo(cap, os.path.join(photos_dir, "full_down.jpg"), "Full Down")

    tilt_total = measure_continuous_sweep(
        cam, cap, CTRL_TILT_SPEED, 1, "tilt", "tilt (down->up)")
    save_photo(cap, os.path.join(photos_dir, "full_up.jpg"), "Full Up")
    # Camera is now at UP limit — well-lit scene with texture

    # =========================================
    # PHASE 2: Measure pan range (at up-limit for good texture)
    # =========================================
    print("\n=== Phase 2: Measure Pan Range ===")
    slam_to_limit(cam, CTRL_PAN_SPEED, -1, "left")
    save_photo(cap, os.path.join(photos_dir, "full_left.jpg"), "Full Left")

    pan_total = measure_continuous_sweep(
        cam, cap, CTRL_PAN_SPEED, 1, "pan", "pan (left->right)")
    save_photo(cap, os.path.join(photos_dir, "full_right.jpg"), "Full Right")

    # =========================================
    # PHASE 3: Zoom photos
    # =========================================
    print("\n=== Phase 3: Zoom ===")
    go_to_center(cam, pan_total, tilt_total)
    cam.zoom_to(ZOOM_MIN)
    time.sleep(SETTLE_TIME)
    save_photo(cap, os.path.join(photos_dir, "zoom_min.jpg"), "Zoom Min")

    cam.zoom_to(ZOOM_MAX)
    time.sleep(SETTLE_TIME)
    save_photo(cap, os.path.join(photos_dir, "zoom_max.jpg"), "Zoom Max")

    cam.zoom_to(ZOOM_MIN)
    time.sleep(SETTLE_TIME)

    # =========================================
    # PHASE 4: Corner + center photos
    # =========================================
    print("\n=== Phase 4: Corner Photos ===")
    corners = [
        ("upper_left", -1, 1),
        ("upper_right", 1, 1),
        ("lower_left", -1, -1),
        ("lower_right", 1, -1),
    ]
    for corner_name, pan_dir, tilt_dir in corners:
        set_speed(cam, CTRL_PAN_SPEED, pan_dir)
        set_speed(cam, CTRL_TILT_SPEED, tilt_dir)
        time.sleep(SLAM_DURATION)
        set_speed(cam, CTRL_PAN_SPEED, 0)
        set_speed(cam, CTRL_TILT_SPEED, 0)
        time.sleep(SETTLE_TIME)
        save_photo(
            cap,
            os.path.join(photos_dir, f"{corner_name}.jpg"),
            corner_name.replace("_", " ").title(),
        )

    # Center photo
    go_to_center(cam, pan_total, tilt_total)
    save_photo(cap, os.path.join(photos_dir, "center.jpg"), "Center")

    cam.zoom_to(ZOOM_MIN)
    cap.release()

    # =========================================
    # Save calibration
    # =========================================
    calibration = {
        "pan_total_seconds": round(pan_total, 1),
        "pan_left_seconds": round(pan_total / 2, 1),
        "pan_right_seconds": round(pan_total / 2, 1),
        "tilt_total_seconds": round(tilt_total, 1),
        "tilt_up_seconds": round(tilt_total / 2, 1),
        "tilt_down_seconds": round(tilt_total / 2, 1),
        "zoom_min": ZOOM_MIN,
        "zoom_max": ZOOM_MAX,
        "measured_at": datetime.datetime.now().isoformat(),
        "device": cam.device,
    }

    with open(output_path, "w") as f:
        json.dump(calibration, f, indent=2)

    return calibration


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-tune BCC950 range of motion using phase correlation."
    )
    parser.add_argument(
        "--device", default=None,
        help="V4L2 device path (auto-detect if omitted)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output calibration JSON path (default: calibration.json in project root)",
    )
    args = parser.parse_args()

    output = args.output or os.path.join(PROJECT_ROOT, "calibration.json")
    output = os.path.abspath(output)

    print("=" * 50)
    print("  BCC950 Auto-Tune: Range of Motion Discovery")
    print("=" * 50)

    calibration = run_auto_tune(args.device, output)

    print()
    print("=" * 50)
    print("  Results")
    print("=" * 50)
    print(f"  Pan total:  {calibration['pan_total_seconds']}s")
    print(f"  Tilt total: {calibration['tilt_total_seconds']}s")
    print(f"  Zoom range: {calibration['zoom_min']} - {calibration['zoom_max']}")
    print(f"\n  Calibration saved to: {output}")
    print(f"  Photos saved to: reports/photos/")
    print("=" * 50)


if __name__ == "__main__":
    main()
