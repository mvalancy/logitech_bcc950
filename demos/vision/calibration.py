#!/usr/bin/env python3
"""ArUco marker-based calibration for the Logitech BCC950 camera.

Detects ArUco markers at known positions and maps movement-seconds to
estimated degrees by tracking marker displacement across pan/tilt commands.
Saves calibration data to a JSON file for use by other applications.

Usage:
    python calibration.py
    python calibration.py --device /dev/video2
    python calibration.py --output my_calibration.json
    python calibration.py --aruco-dict DICT_6X6_250

Procedure:
    1. Place one or more ArUco markers in the camera's field of view.
    2. The script will detect markers, then perform a series of small
       pan/tilt movements, measuring pixel displacement of the markers.
    3. From pixel displacement and known camera FOV, it estimates the
       degrees-per-movement-second for pan and tilt.
    4. Results are saved to a JSON calibration file.

Extension points:
    - Support multi-marker grids for higher accuracy
    - Replace single-step calibration with iterative refinement
    - Add zoom calibration by measuring FOV change at different zoom levels
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "python"))

try:
    import cv2
    import numpy as np
except ImportError:
    print("Error: OpenCV and NumPy are required for this demo.")
    print("Install them with:  pip install opencv-python opencv-contrib-python numpy")
    sys.exit(1)

# Check for ArUco support
try:
    _aruco = cv2.aruco
except AttributeError:
    print("Error: OpenCV ArUco module not found.")
    print("Install it with:  pip install opencv-contrib-python")
    sys.exit(1)

from bcc950 import BCC950Controller

# --- Defaults ---
DEFAULT_OUTPUT = "bcc950_calibration.json"
DEFAULT_ARUCO_DICT = "DICT_4X4_50"
CALIBRATION_MOVE_DURATION = 0.2  # seconds per calibration step
CALIBRATION_STEPS = 5  # number of steps in each direction
SETTLE_TIME = 0.3  # seconds to wait for camera to stabilize
ESTIMATED_HFOV_DEG = 78.0  # BCC950 approximate horizontal FOV at min zoom
ESTIMATED_VFOV_DEG = 48.0  # BCC950 approximate vertical FOV at min zoom


ARUCO_DICT_MAP = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
}


def get_aruco_dict(name: str) -> cv2.aruco.Dictionary:
    """Look up an ArUco dictionary by name."""
    if name not in ARUCO_DICT_MAP:
        available = ", ".join(sorted(ARUCO_DICT_MAP.keys()))
        print(f"Error: Unknown ArUco dictionary '{name}'.")
        print(f"Available: {available}")
        sys.exit(1)
    return cv2.aruco.getPredefinedDictionary(ARUCO_DICT_MAP[name])


def detect_markers(
    frame: np.ndarray,
    aruco_dict: cv2.aruco.Dictionary,
) -> dict[int, np.ndarray]:
    """Detect ArUco markers and return their center positions.

    Returns:
        Dict mapping marker ID to (cx, cy) center coordinates.

    Extension point: support CharUco boards or multi-marker grids
    for sub-pixel accuracy.
    """
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    corners, ids, _ = detector.detectMarkers(frame)

    markers: dict[int, np.ndarray] = {}
    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            # Compute center from the four corners
            center = corners[i][0].mean(axis=0)
            markers[int(marker_id)] = center

    return markers


def capture_stable_frame(cap: cv2.VideoCapture) -> np.ndarray:
    """Capture a frame after allowing the camera to settle."""
    time.sleep(SETTLE_TIME)
    # Flush stale frames from the buffer
    for _ in range(5):
        cap.read()
    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to capture frame.")
        sys.exit(1)
    return frame


def run_calibration_axis(
    cam: BCC950Controller,
    cap: cv2.VideoCapture,
    aruco_dict: cv2.aruco.Dictionary,
    axis: str,
    move_duration: float,
    steps: int,
) -> dict:
    """Run calibration along one axis (pan or tilt).

    Performs small movements, measures marker displacement, and computes
    degrees-per-movement-second.

    Returns dict with calibration measurements.
    """
    print(f"\n--- Calibrating {axis} axis ---")

    displacements_px: list[float] = []
    pixel_axis = 0 if axis == "pan" else 1  # x for pan, y for tilt

    for step in range(steps):
        # Detect markers before movement
        frame_before = capture_stable_frame(cap)
        markers_before = detect_markers(frame_before, aruco_dict)

        if not markers_before:
            print(f"  Step {step + 1}: No markers detected, skipping.")
            continue

        # Perform movement
        if axis == "pan":
            cam.pan_right(move_duration)
        else:
            cam.tilt_up(move_duration)

        # Detect markers after movement
        frame_after = capture_stable_frame(cap)
        markers_after = detect_markers(frame_after, aruco_dict)

        # Compute displacement for markers visible in both frames
        common_ids = set(markers_before.keys()) & set(markers_after.keys())
        if not common_ids:
            print(f"  Step {step + 1}: No common markers, skipping.")
            continue

        step_displacements = []
        for mid in common_ids:
            displacement = markers_after[mid][pixel_axis] - markers_before[mid][pixel_axis]
            step_displacements.append(abs(displacement))

        avg_displacement = float(np.mean(step_displacements))
        displacements_px.append(avg_displacement)
        print(
            f"  Step {step + 1}/{steps}: "
            f"avg displacement = {avg_displacement:.1f} px "
            f"({len(common_ids)} markers)"
        )

    if not displacements_px:
        print(f"  WARNING: No valid measurements for {axis} axis.")
        return {"axis": axis, "valid": False}

    # Get frame dimensions for FOV calculation
    h, w = frame_before.shape[:2]
    fov_deg = ESTIMATED_HFOV_DEG if axis == "pan" else ESTIMATED_VFOV_DEG
    frame_dim = w if axis == "pan" else h

    # Convert pixel displacement to degrees
    avg_px_per_step = float(np.mean(displacements_px))
    deg_per_pixel = fov_deg / frame_dim
    deg_per_step = avg_px_per_step * deg_per_pixel
    deg_per_second = deg_per_step / move_duration

    result = {
        "axis": axis,
        "valid": True,
        "steps": steps,
        "move_duration_s": move_duration,
        "avg_displacement_px": avg_px_per_step,
        "estimated_fov_deg": fov_deg,
        "frame_dimension_px": frame_dim,
        "deg_per_pixel": deg_per_pixel,
        "deg_per_step": deg_per_step,
        "deg_per_second": deg_per_second,
        "raw_displacements_px": displacements_px,
    }

    print(f"  Result: {deg_per_second:.2f} deg/s ({deg_per_step:.2f} deg per step)")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ArUco marker-based calibration for the Logitech BCC950."
    )
    parser.add_argument(
        "--device", default="/dev/video0", help="V4L2 device path (default: /dev/video0)"
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT, help=f"Output JSON file (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--aruco-dict",
        default=DEFAULT_ARUCO_DICT,
        help=f"ArUco dictionary name (default: {DEFAULT_ARUCO_DICT})",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=CALIBRATION_STEPS,
        help=f"Calibration steps per axis (default: {CALIBRATION_STEPS})",
    )
    parser.add_argument(
        "--move-duration",
        type=float,
        default=CALIBRATION_MOVE_DURATION,
        help=f"Movement duration per step in seconds (default: {CALIBRATION_MOVE_DURATION})",
    )
    args = parser.parse_args()

    aruco_dict = get_aruco_dict(args.aruco_dict)

    cam = BCC950Controller(device=args.device)
    cap = cv2.VideoCapture(args.device)

    if not cap.isOpened():
        print(f"Error: Could not open video device {args.device}")
        sys.exit(1)

    print(f"BCC950 Calibration using ArUco markers ({args.aruco_dict})")
    print(f"Device: {args.device}")
    print(f"Place ArUco markers in the camera's field of view.")
    print()

    # Check for markers before starting
    frame = capture_stable_frame(cap)
    markers = detect_markers(frame, aruco_dict)

    if not markers:
        print("No ArUco markers detected. Please place markers and try again.")
        print(f"Expected dictionary: {args.aruco_dict}")
        print("You can generate markers at: https://chev.me/arucogen/")
        cap.release()
        sys.exit(1)

    print(f"Detected {len(markers)} marker(s): IDs {list(markers.keys())}")

    # Reset camera to center before calibration
    print("\nResetting camera to center position...")
    cam.reset_position()
    time.sleep(1.0)

    # Run calibration on each axis
    pan_result = run_calibration_axis(
        cam, cap, aruco_dict, "pan", args.move_duration, args.steps
    )

    # Reset before tilt calibration
    cam.reset_position()
    time.sleep(1.0)

    tilt_result = run_calibration_axis(
        cam, cap, aruco_dict, "tilt", args.move_duration, args.steps
    )

    # Reset after calibration
    cam.reset_position()

    # Save results
    calibration = {
        "device": args.device,
        "aruco_dict": args.aruco_dict,
        "pan": pan_result,
        "tilt": tilt_result,
    }

    output_path = args.output
    with open(output_path, "w") as f:
        json.dump(calibration, f, indent=2)

    print(f"\nCalibration saved to: {output_path}")

    if pan_result.get("valid"):
        print(f"  Pan: {pan_result['deg_per_second']:.2f} deg/s")
    else:
        print("  Pan: calibration failed (no valid measurements)")

    if tilt_result.get("valid"):
        print(f"  Tilt: {tilt_result['deg_per_second']:.2f} deg/s")
    else:
        print("  Tilt: calibration failed (no valid measurements)")

    cap.release()


if __name__ == "__main__":
    main()
