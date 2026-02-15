#!/usr/bin/env python3
"""Native C++ backend PTZ demo with benchmark comparison.

Requires building the pybind11 bindings first:
    cmake -B build -DBUILD_PYTHON_BINDINGS=ON
    cmake --build build -j$(nproc)

Then set PYTHONPATH so Python can find the module:
    export PYTHONPATH=build:$PYTHONPATH
    python samples/native_ptz.py

Usage:
    python samples/native_ptz.py
    python samples/native_ptz.py --device /dev/video2
"""

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))


def benchmark_backend(ctrl, label: str, iterations: int = 100) -> float:
    """Time N get_control calls, return avg ms per call."""
    # Warm up
    ctrl.get_zoom()
    start = time.perf_counter()
    for _ in range(iterations):
        ctrl.get_zoom()
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / iterations) * 1000
    print(f"  {label}: {iterations} get_control calls in {elapsed:.3f}s "
          f"({avg_ms:.2f} ms/call)")
    return avg_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="BCC950 native backend demo")
    parser.add_argument("--device", default=None, help="V4L2 device path")
    parser.add_argument("-n", type=int, default=100, help="Benchmark iterations")
    args = parser.parse_args()

    from bcc950 import BCC950Controller
    from bcc950.native_backend import NativeV4L2Backend, is_available

    if not is_available():
        print("Native backend not available.")
        print("Build with: cmake -B build -DBUILD_PYTHON_BINDINGS=ON && cmake --build build -j$(nproc)")
        print("Then: export PYTHONPATH=build:$PYTHONPATH")
        sys.exit(1)

    # --- Subprocess backend (baseline) ---
    print("=== Subprocess Backend (v4l2-ctl) ===")
    ctrl_sub = BCC950Controller(device=args.device)
    if args.device is None:
        found = ctrl_sub.find_camera()
        if not found:
            print("Could not auto-detect BCC950.")
            sys.exit(1)
        print(f"Camera: {found}")

    sub_ms = benchmark_backend(ctrl_sub, "subprocess", args.n)

    # --- Native backend ---
    print()
    print("=== Native Backend (C++ pybind11) ===")
    backend = NativeV4L2Backend()
    ctrl_native = BCC950Controller(device=args.device, backend=backend)
    if args.device is None:
        ctrl_native.find_camera()

    native_ms = benchmark_backend(ctrl_native, "native", args.n)

    # --- Comparison ---
    print()
    if native_ms > 0:
        speedup = sub_ms / native_ms
        print(f"Speedup: {speedup:.1f}x faster with native backend")
    print(f"  subprocess: {sub_ms:.2f} ms/call")
    print(f"  native:     {native_ms:.2f} ms/call")

    # Quick movement test
    print()
    print("=== Movement Test (native) ===")
    ctrl_native.reset_position()
    time.sleep(0.5)

    print("Pan left...")
    ctrl_native.pan_left(duration=0.2)
    time.sleep(0.3)

    print("Pan right...")
    ctrl_native.pan_right(duration=0.4)
    time.sleep(0.3)

    print("Reset...")
    ctrl_native.reset_position()
    print("Done!")


if __name__ == "__main__":
    main()
