#!/usr/bin/env python3
"""Movement verifier demo for the Logitech BCC950 camera.

Interactive tool that opens the camera feed, overlays Lucas-Kanade optical flow
arrows, and lets the user issue PTZ commands via keyboard. After each command,
optical flow is analyzed to verify the camera actually moved, displaying a
PASS/FAIL overlay.

Usage:
    python movement_verifier.py
    python movement_verifier.py --device /dev/video2

Controls:
    a / d  - Pan left / right
    w / s  - Tilt up / down
    + / -  - Zoom in / out
    r      - Reset camera
    q      - Quit

Extension points:
    - Add custom verification metrics in verify_movement()
    - Integrate with test frameworks for automated PTZ validation
    - Extend key bindings for preset recall, combined moves, etc.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "python"))

try:
    import cv2
    import numpy as np
except ImportError:
    print("Error: OpenCV and NumPy are required for this demo.")
    print("Install them with:  pip install opencv-python numpy")
    sys.exit(1)

from bcc950 import BCC950Controller

# Lucas-Kanade optical flow parameters
LK_PARAMS = dict(
    winSize=(21, 21), maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
)
# Shi-Tomasi corner detection for feature points
FEATURE_PARAMS = dict(maxCorners=200, qualityLevel=0.01, minDistance=10, blockSize=7)
MIN_DISPLACEMENT = 2.0  # pixels -- threshold for "real" movement
OVERLAY_FRAMES = 45  # how long to show PASS/FAIL
COMMAND_DURATION = 0.15


def find_features(gray: np.ndarray) -> np.ndarray | None:
    """Detect Shi-Tomasi features. Extension point: swap with ORB/SIFT."""
    return cv2.goodFeaturesToTrack(gray, mask=None, **FEATURE_PARAMS)


def compute_flow(prev: np.ndarray, curr: np.ndarray, pts: np.ndarray):
    """Compute Lucas-Kanade optical flow. Returns (old, new) matched points."""
    nxt, status, _ = cv2.calcOpticalFlowPyrLK(prev, curr, pts, None, **LK_PARAMS)
    if nxt is None or status is None:
        return np.array([]), np.array([])
    mask = status.flatten() == 1
    return pts[mask], nxt[mask]


def draw_flow(frame: np.ndarray, old: np.ndarray, new: np.ndarray) -> np.ndarray:
    """Draw optical flow arrows on the frame."""
    out = frame.copy()
    for (x0, y0), (x1, y1) in zip(old.astype(int), new.astype(int)):
        mag = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if mag < 0.5:
            continue
        color = (int(min(255, abs(x1-x0)*20)), int(min(255, abs(y1-y0)*20)),
                 int(min(255, mag*10)))
        cv2.arrowedLine(out, (x0, y0), (x1, y1), color, 1, tipLength=0.3)
        cv2.circle(out, (x0, y0), 2, (0, 255, 0), -1)
    return out


def verify_movement(old: np.ndarray, new: np.ndarray, direction: str):
    """Verify optical flow matches expected direction. Returns (pass, mag, detail).

    Extension point: add histogram-based or homography-based verification.
    """
    if len(old) == 0 or len(new) == 0:
        return False, 0.0, "No features tracked"
    disp = new - old
    dx, dy = float(np.mean(disp[:, 0])), float(np.mean(disp[:, 1]))
    mag = float(np.mean(np.linalg.norm(disp, axis=1)))
    detail = f"dx={dx:+.1f} dy={dy:+.1f} mag={mag:.1f}"
    if mag < MIN_DISPLACEMENT:
        return False, mag, f"Insufficient motion ({detail})"
    # Camera pan left -> scene shifts right (positive dx), etc.
    checks = {"left": dx > 0, "right": dx < 0, "up": dy > 0, "down": dy < 0,
              "zoom_in": mag > MIN_DISPLACEMENT, "zoom_out": mag > MIN_DISPLACEMENT}
    return checks.get(direction, False), mag, detail


def draw_overlay(frame, passed, message, pos_info):
    """Draw PASS/FAIL overlay and status info."""
    out = frame.copy()
    h, w = out.shape[:2]
    cv2.putText(out, pos_info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    if passed is not None:
        text = "PASS" if passed else "FAIL"
        color = (0, 255, 0) if passed else (0, 0, 255)
        sz = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 4)[0]
        tx, ty = (w - sz[0]) // 2, (h + sz[1]) // 2
        cv2.rectangle(out, (tx-20, ty-sz[1]-20), (tx+sz[0]+20, ty+20), (0, 0, 0), -1)
        cv2.putText(out, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 2.0, color, 4)
        cv2.putText(out, message, (10, h-40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    cv2.putText(out, "WASD:pan/tilt  +/-:zoom  r:reset  q:quit",
                (10, h-15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
    return out


# Map keys to (camera_method, direction_label)
KEY_COMMANDS = {
    ord("a"): ("pan_left",  "left"),
    ord("d"): ("pan_right", "right"),
    ord("w"): ("tilt_up",   "up"),
    ord("s"): ("tilt_down", "down"),
    ord("+"): ("zoom_in",   "zoom_in"),
    ord("="): ("zoom_in",   "zoom_in"),
    ord("-"): ("zoom_out",  "zoom_out"),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive PTZ movement verifier with optical flow visualization."
    )
    parser.add_argument(
        "--device", default="/dev/video0", help="V4L2 device path (default: /dev/video0)"
    )
    parser.add_argument(
        "--move-duration", type=float, default=COMMAND_DURATION,
        help=f"Duration per PTZ command in seconds (default: {COMMAND_DURATION})",
    )
    args = parser.parse_args()

    cam = BCC950Controller(device=args.device)
    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        print(f"Error: Could not open video device {args.device}")
        sys.exit(1)

    print(f"Movement verifier started on {args.device}")
    print("WASD to pan/tilt, +/- to zoom, r to reset, q to quit.")

    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to read initial frame.")
        sys.exit(1)

    prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    result_passed: bool | None = None
    result_msg = ""
    countdown = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            display = frame.copy()

            # Show live optical flow
            pts = find_features(prev_gray)
            if pts is not None and len(pts) > 0:
                old, new = compute_flow(prev_gray, curr_gray, pts)
                if len(old) > 0:
                    display = draw_flow(display, old, new)

            if countdown > 0:
                countdown -= 1
            else:
                result_passed, result_msg = None, ""

            pos = cam.position
            pos_info = f"Pan:{pos.pan:+.2f} Tilt:{pos.tilt:+.2f} Zoom:{pos.zoom}"
            display = draw_overlay(display, result_passed, result_msg, pos_info)
            cv2.imshow("BCC950 Movement Verifier", display)

            prev_gray = curr_gray.copy()
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("r"):
                cam.reset_position()
                print("Camera reset.")
                continue

            if key in KEY_COMMANDS:
                method_name, direction = KEY_COMMANDS[key]
                pre_gray = curr_gray.copy()
                pre_pts = find_features(pre_gray)

                # Execute the camera command
                method = getattr(cam, method_name)
                if direction.startswith("zoom"):
                    method()
                else:
                    method(args.move_duration)

                # Verify with post-move frame
                if pre_pts is not None and len(pre_pts) > 0:
                    ret2, post_frame = cap.read()
                    if ret2:
                        post_gray = cv2.cvtColor(post_frame, cv2.COLOR_BGR2GRAY)
                        g_old, g_new = compute_flow(pre_gray, post_gray, pre_pts)
                        passed, mag, detail = verify_movement(g_old, g_new, direction)
                        result_passed = passed
                        result_msg = f"{direction.upper()}: {detail}"
                        countdown = OVERLAY_FRAMES
                        tag = "PASS" if passed else "FAIL"
                        print(f"[{tag}] {direction}: {detail}")
    finally:
        cam.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
