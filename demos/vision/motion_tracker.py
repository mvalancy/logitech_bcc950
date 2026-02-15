#!/usr/bin/env python3
"""Motion tracker demo for the Logitech BCC950 camera.

Detects the largest moving object in the camera feed using MOG2 background
subtraction, computes its centroid, and automatically pans/tilts the camera
to keep the object centered in the frame.

Usage:
    python motion_tracker.py
    python motion_tracker.py --device /dev/video2
    python motion_tracker.py --dead-zone 0.15 --move-duration 0.08

Controls:
    q - Quit
    r - Reset camera to center

Extension points:
    - Replace detect_motion() with a deep learning detector (YOLO, SSD, etc.)
    - Adjust DEAD_ZONE_FRACTION for sensitivity tuning
    - Override compute_movement() for custom tracking strategies (PID, etc.)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Add project source to path so we can import bcc950
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "python"))

try:
    import cv2
    import numpy as np
except ImportError:
    print("Error: OpenCV and NumPy are required for this demo.")
    print("Install them with:  pip install opencv-python numpy")
    sys.exit(1)

from bcc950 import BCC950Controller


# --- Configuration defaults ---
DEFAULT_DEAD_ZONE = 0.10  # fraction of frame width/height
DEFAULT_MOVE_DURATION = 0.05  # seconds per correction step
MIN_CONTOUR_AREA = 1500  # minimum pixel area to consider as motion
BG_HISTORY = 500
BG_THRESHOLD = 16
BG_DETECT_SHADOWS = True
MORPH_KERNEL_SIZE = 5


def create_background_subtractor() -> cv2.BackgroundSubtractorMOG2:
    """Create and configure the MOG2 background subtractor.

    Extension point: replace with cv2.createBackgroundSubtractorKNN()
    or a deep-learning-based segmenter for different environments.
    """
    return cv2.createBackgroundSubtractorMOG2(
        history=BG_HISTORY,
        varThreshold=BG_THRESHOLD,
        detectShadows=BG_DETECT_SHADOWS,
    )


def detect_motion(
    frame: np.ndarray,
    bg_subtractor: cv2.BackgroundSubtractorMOG2,
    min_area: int = MIN_CONTOUR_AREA,
) -> tuple[np.ndarray | None, np.ndarray]:
    """Detect the largest moving region in the frame.

    Returns:
        (centroid, mask) where centroid is (cx, cy) or None if no motion,
        and mask is the foreground mask for visualization.

    Extension point: swap this function with a YOLO or MobileNet-SSD
    detector that returns bounding-box centroids instead.
    """
    fg_mask = bg_subtractor.apply(frame)

    # Clean up the mask with morphological operations
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE)
    )
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

    # Threshold to remove shadows (shadows are gray, motion is white)
    _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None, fg_mask

    # Find the largest contour by area
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)

    if area < min_area:
        return None, fg_mask

    # Compute centroid via moments
    moments = cv2.moments(largest)
    if moments["m00"] == 0:
        return None, fg_mask

    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])

    return np.array([cx, cy]), fg_mask


def compute_movement(
    centroid: np.ndarray,
    frame_w: int,
    frame_h: int,
    dead_zone: float,
) -> tuple[int, int]:
    """Determine pan/tilt direction from centroid offset.

    Returns (pan_dir, tilt_dir) where each is -1, 0, or 1.

    Extension point: replace with a PID controller for smoother tracking,
    or add proportional speed control based on distance from center.
    """
    cx, cy = centroid
    center_x = frame_w / 2.0
    center_y = frame_h / 2.0

    dz_w = dead_zone * frame_w
    dz_h = dead_zone * frame_h

    pan_dir = 0
    tilt_dir = 0

    if cx < center_x - dz_w:
        pan_dir = -1  # Object is left of center, pan left
    elif cx > center_x + dz_w:
        pan_dir = 1  # Object is right of center, pan right

    if cy < center_y - dz_h:
        tilt_dir = 1  # Object is above center, tilt up
    elif cy > center_y + dz_h:
        tilt_dir = -1  # Object is below center, tilt down

    return pan_dir, tilt_dir


def draw_overlay(
    frame: np.ndarray,
    centroid: np.ndarray | None,
    pan_dir: int,
    tilt_dir: int,
    dead_zone: float,
) -> np.ndarray:
    """Draw tracking visualization on the frame."""
    h, w = frame.shape[:2]
    display = frame.copy()

    # Draw dead zone rectangle
    dz_x = int(dead_zone * w)
    dz_y = int(dead_zone * h)
    cx, cy = w // 2, h // 2
    cv2.rectangle(
        display,
        (cx - dz_x, cy - dz_y),
        (cx + dz_x, cy + dz_y),
        (0, 255, 0),
        1,
    )

    # Draw crosshair at center
    cv2.line(display, (cx - 20, cy), (cx + 20, cy), (0, 255, 0), 1)
    cv2.line(display, (cx, cy - 20), (cx, cy + 20), (0, 255, 0), 1)

    if centroid is not None:
        # Draw centroid marker
        cv2.circle(display, tuple(centroid), 10, (0, 0, 255), 2)
        cv2.circle(display, tuple(centroid), 3, (0, 0, 255), -1)

        # Draw line from center to centroid
        cv2.line(display, (cx, cy), tuple(centroid), (0, 0, 255), 1)

    # Show movement direction
    direction_text = []
    if pan_dir == -1:
        direction_text.append("PAN LEFT")
    elif pan_dir == 1:
        direction_text.append("PAN RIGHT")
    if tilt_dir == 1:
        direction_text.append("TILT UP")
    elif tilt_dir == -1:
        direction_text.append("TILT DOWN")

    status = " | ".join(direction_text) if direction_text else "CENTERED"
    color = (0, 0, 255) if direction_text else (0, 255, 0)
    cv2.putText(display, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.putText(
        display,
        "Press 'q' to quit, 'r' to reset",
        (10, h - 15),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (200, 200, 200),
        1,
    )

    return display


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Motion tracking demo for the Logitech BCC950 camera."
    )
    parser.add_argument(
        "--device", default="/dev/video0", help="V4L2 device path (default: /dev/video0)"
    )
    parser.add_argument(
        "--dead-zone",
        type=float,
        default=DEFAULT_DEAD_ZONE,
        help=f"Dead zone as fraction of frame size (default: {DEFAULT_DEAD_ZONE})",
    )
    parser.add_argument(
        "--move-duration",
        type=float,
        default=DEFAULT_MOVE_DURATION,
        help=f"Duration per correction step in seconds (default: {DEFAULT_MOVE_DURATION})",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=MIN_CONTOUR_AREA,
        help=f"Minimum contour area to track (default: {MIN_CONTOUR_AREA})",
    )
    args = parser.parse_args()

    cam = BCC950Controller(device=args.device)
    cap = cv2.VideoCapture(args.device)

    if not cap.isOpened():
        print(f"Error: Could not open video device {args.device}")
        sys.exit(1)

    bg_sub = create_background_subtractor()

    print(f"Motion tracker started on {args.device}")
    print("Press 'q' to quit, 'r' to reset camera.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Failed to read frame.")
                break

            h, w = frame.shape[:2]
            centroid, fg_mask = detect_motion(frame, bg_sub, args.min_area)

            pan_dir, tilt_dir = 0, 0
            if centroid is not None:
                pan_dir, tilt_dir = compute_movement(centroid, w, h, args.dead_zone)

                if pan_dir != 0 or tilt_dir != 0:
                    cam.move(pan_dir, tilt_dir, args.move_duration)

            display = draw_overlay(frame, centroid, pan_dir, tilt_dir, args.dead_zone)
            cv2.imshow("BCC950 Motion Tracker", display)
            cv2.imshow("Foreground Mask", fg_mask)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("r"):
                cam.reset_position()
                bg_sub = create_background_subtractor()
                print("Camera reset.")
    finally:
        cam.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
