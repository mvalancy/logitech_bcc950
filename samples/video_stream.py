#!/usr/bin/env python3
"""Interactive video stream with PTZ control via keyboard.

Opens the BCC950 camera feed in an OpenCV window. Use arrow keys
to pan/tilt and +/- to zoom. Press 'q' or ESC to quit.

Controls:
    Left/Right arrow  — pan
    Up/Down arrow     — tilt
    +/=               — zoom in
    -                 — zoom out
    r                 — reset to home
    q / ESC           — quit

Usage:
    python samples/video_stream.py
    python samples/video_stream.py --device /dev/video2
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

import cv2
from bcc950 import BCC950Controller


def main() -> None:
    parser = argparse.ArgumentParser(description="BCC950 interactive video")
    parser.add_argument("--device", default=None, help="V4L2 device path")
    args = parser.parse_args()

    ctrl = BCC950Controller(device=args.device)
    if args.device is None:
        found = ctrl.find_camera()
        if not found:
            print("Could not auto-detect BCC950. Use --device /dev/videoN")
            sys.exit(1)
        print(f"Camera: {found}")

    cap = cv2.VideoCapture(ctrl.device)
    if not cap.isOpened():
        print(f"Cannot open video: {ctrl.device}")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print("Controls: arrows=pan/tilt, +/-=zoom, r=reset, q=quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        # Draw zoom level
        zoom = ctrl.get_zoom()
        text = f"Zoom: {zoom}"
        cv2.putText(frame, text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        cv2.imshow("BCC950", frame)
        key = cv2.waitKey(30) & 0xFF

        if key == ord("q") or key == 27:  # q or ESC
            break
        elif key == 81 or key == 2:  # Left arrow
            ctrl.pan_left(duration=0.1)
        elif key == 83 or key == 3:  # Right arrow
            ctrl.pan_right(duration=0.1)
        elif key == 82 or key == 0:  # Up arrow
            ctrl.tilt_up(duration=0.1)
        elif key == 84 or key == 1:  # Down arrow
            ctrl.tilt_down(duration=0.1)
        elif key == ord("+") or key == ord("="):
            ctrl.zoom_in()
        elif key == ord("-"):
            ctrl.zoom_out()
        elif key == ord("r"):
            ctrl.reset_position()

    cap.release()
    cv2.destroyAllWindows()
    print("Done!")


if __name__ == "__main__":
    main()
