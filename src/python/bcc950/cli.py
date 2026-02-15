"""CLI entrypoint for BCC950 camera control."""

from __future__ import annotations

import argparse
import sys

from .controller import BCC950Controller


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control Logitech BCC950 Camera",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-d", "--device", help="Specify camera device")

    # Basic movement
    parser.add_argument("--pan-left", action="store_true", help="Pan camera left")
    parser.add_argument("--pan-right", action="store_true", help="Pan camera right")
    parser.add_argument("--tilt-up", action="store_true", help="Tilt camera up")
    parser.add_argument("--tilt-down", action="store_true", help="Tilt camera down")
    parser.add_argument("--zoom-in", action="store_true", help="Zoom camera in")
    parser.add_argument("--zoom-out", action="store_true", help="Zoom camera out")

    # Extended movement
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Movement duration in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--zoom-value",
        type=int,
        metavar="VALUE",
        help="Set zoom to absolute value (100-500)",
    )
    parser.add_argument(
        "--move",
        nargs=3,
        metavar=("PAN", "TILT", "DURATION"),
        help="Combined move: PAN(-1/0/1) TILT(-1/0/1) DURATION",
    )

    # Presets
    parser.add_argument("--save-preset", metavar="NAME", help="Save current position as preset")
    parser.add_argument("--recall-preset", metavar="NAME", help="Recall a named preset")
    parser.add_argument("--delete-preset", metavar="NAME", help="Delete a named preset")
    parser.add_argument("--list-presets", action="store_true", help="List all presets")

    # Info / setup
    parser.add_argument("--position", action="store_true", help="Show estimated position")
    parser.add_argument("--reset", action="store_true", help="Reset camera to default position")
    parser.add_argument("--setup", action="store_true", help="Detect camera and test connection")
    parser.add_argument("-l", "--list", action="store_true", help="List available camera devices")
    parser.add_argument("--info", action="store_true", help="Show camera information")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    ctrl = BCC950Controller(device=args.device)
    duration = args.duration or 0.1

    if args.setup:
        device = ctrl.find_camera()
        if device:
            print(f"Found camera at: {device}")
        ptz = ctrl.has_ptz_support()
        print(f"PTZ support: {ptz}")

    elif args.list:
        print(ctrl.list_devices())

    elif args.pan_left:
        ctrl.pan_left(duration)
    elif args.pan_right:
        ctrl.pan_right(duration)
    elif args.tilt_up:
        ctrl.tilt_up(duration)
    elif args.tilt_down:
        ctrl.tilt_down(duration)
    elif args.zoom_in:
        ctrl.zoom_in()
    elif args.zoom_out:
        ctrl.zoom_out()

    elif args.zoom_value is not None:
        ctrl.zoom_to(args.zoom_value)
        print(f"Zoom set to {args.zoom_value}")

    elif args.move:
        pan_dir, tilt_dir, dur = int(args.move[0]), int(args.move[1]), float(args.move[2])
        ctrl.move(pan_dir, tilt_dir, dur)
        print(f"Moved pan={pan_dir} tilt={tilt_dir} for {dur}s")

    elif args.save_preset:
        ctrl.save_preset(args.save_preset)
        print(f"Saved preset: {args.save_preset}")
    elif args.recall_preset:
        if ctrl.recall_preset(args.recall_preset):
            print(f"Recalled preset: {args.recall_preset}")
        else:
            print(f"Preset not found: {args.recall_preset}")
            return 1
    elif args.delete_preset:
        if ctrl.delete_preset(args.delete_preset):
            print(f"Deleted preset: {args.delete_preset}")
        else:
            print(f"Preset not found: {args.delete_preset}")
            return 1
    elif args.list_presets:
        presets = ctrl.list_presets()
        if presets:
            for name in presets:
                print(f"  {name}")
        else:
            print("No presets saved.")

    elif args.position:
        pos = ctrl.position
        print(f"Pan: {pos.pan:.2f}  Tilt: {pos.tilt:.2f}  Zoom: {pos.zoom}")

    elif args.reset:
        ctrl.reset_position()
        print("Camera reset to default position.")

    elif args.info:
        print(f"Device: {ctrl.device}")
        print(f"PTZ support: {ctrl.has_ptz_support()}")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
