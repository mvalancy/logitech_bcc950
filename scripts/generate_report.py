#!/usr/bin/env python3
"""Generate an HTML test report for the BCC950 system.

Runs all verification checks (system, hardware, software, AI) and produces
a visual HTML report with checkmarks and X marks.

Usage:
    python scripts/generate_report.py
    python scripts/generate_report.py --device /dev/video0
    python scripts/generate_report.py --output report.html
"""

from __future__ import annotations

import argparse
import base64
import datetime
import html
import json
import os
import platform
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

# Default durations when no calibration.json exists (generous to ensure full sweep)
DEFAULT_PAN_DURATION = 5.0
DEFAULT_TILT_DURATION = 5.0
SETTLE_TIME = 0.5
CENTER_DURATION = 6.0
WARMUP_FRAMES = 10


def load_calibration() -> dict | None:
    """Load calibration.json if it exists."""
    path = os.path.join(PROJECT_ROOT, "calibration.json")
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return None


def run_photo_tour(device: str) -> dict[str, str]:
    """Capture photos at extreme positions and return {label: filepath} map.

    Uses calibration.json durations if available, otherwise generous defaults.
    """
    try:
        import cv2
    except ImportError:
        print("  Skipping photo tour: OpenCV not installed")
        return {}

    try:
        from bcc950 import BCC950Controller
        from bcc950.constants import ZOOM_MAX, ZOOM_MIN
    except ImportError:
        print("  Skipping photo tour: bcc950 package not installed")
        return {}

    cal = load_calibration()
    if cal:
        pan_left_dur = cal.get("pan_left_seconds", DEFAULT_PAN_DURATION)
        pan_right_dur = cal.get("pan_right_seconds", DEFAULT_PAN_DURATION)
        tilt_up_dur = cal.get("tilt_up_seconds", DEFAULT_TILT_DURATION)
        tilt_down_dur = cal.get("tilt_down_seconds", DEFAULT_TILT_DURATION)
        print(f"  Using calibration.json durations (pan L/R: {pan_left_dur}/{pan_right_dur}s, "
              f"tilt U/D: {tilt_up_dur}/{tilt_down_dur}s)")
    else:
        pan_left_dur = pan_right_dur = DEFAULT_PAN_DURATION
        tilt_up_dur = tilt_down_dur = DEFAULT_TILT_DURATION
        print(f"  No calibration.json found, using defaults ({DEFAULT_PAN_DURATION}s pan, "
              f"{DEFAULT_TILT_DURATION}s tilt)")

    cam = BCC950Controller(device=device)
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        print(f"  Skipping photo tour: could not open {device}")
        return {}

    # Warmup
    for _ in range(WARMUP_FRAMES):
        cap.read()
    time.sleep(0.5)

    photos_dir = os.path.join(PROJECT_ROOT, "reports", "photos")
    os.makedirs(photos_dir, exist_ok=True)
    photos: dict[str, str] = {}

    def center():
        cam.pan_right(CENTER_DURATION)
        cam.pan_left(CENTER_DURATION)
        cam.pan_right(CENTER_DURATION / 2)
        cam.tilt_up(CENTER_DURATION)
        cam.tilt_down(CENTER_DURATION)
        cam.tilt_up(CENTER_DURATION / 2)
        time.sleep(SETTLE_TIME)

    def capture_photo(label: str, filename: str):
        time.sleep(SETTLE_TIME)
        for _ in range(3):
            cap.read()
        ret, frame = cap.read()
        if ret and frame is not None:
            path = os.path.join(photos_dir, filename)
            cv2.imwrite(path, frame)
            photos[label] = path
            print(f"    Captured: {label}")

    # Center + zoom min
    print("  Capturing photo tour...")
    cam.zoom_to(ZOOM_MIN)
    time.sleep(SETTLE_TIME)
    center()

    capture_photo("Center", "center.jpg")

    # Zoom min/max
    cam.zoom_to(ZOOM_MIN)
    time.sleep(SETTLE_TIME)
    capture_photo("Zoom Min (100)", "zoom_min.jpg")

    cam.zoom_to(ZOOM_MAX)
    time.sleep(SETTLE_TIME)
    capture_photo("Zoom Max (500)", "zoom_max.jpg")

    cam.zoom_to(ZOOM_MIN)
    time.sleep(SETTLE_TIME)

    # Full left
    center()
    cam.pan_left(pan_left_dur)
    time.sleep(SETTLE_TIME)
    capture_photo("Full Left", "full_left.jpg")

    # Full right
    center()
    cam.pan_right(pan_right_dur)
    time.sleep(SETTLE_TIME)
    capture_photo("Full Right", "full_right.jpg")

    # Full up
    center()
    cam.tilt_up(tilt_up_dur)
    time.sleep(SETTLE_TIME)
    capture_photo("Full Up", "full_up.jpg")

    # Full down
    center()
    cam.tilt_down(tilt_down_dur)
    time.sleep(SETTLE_TIME)
    capture_photo("Full Down", "full_down.jpg")

    # Corners
    corner_moves = [
        ("Upper Left", "upper_left.jpg", cam.pan_left, pan_left_dur, cam.tilt_up, tilt_up_dur),
        ("Upper Right", "upper_right.jpg", cam.pan_right, pan_right_dur, cam.tilt_up, tilt_up_dur),
        ("Lower Left", "lower_left.jpg", cam.pan_left, pan_left_dur, cam.tilt_down, tilt_down_dur),
        ("Lower Right", "lower_right.jpg", cam.pan_right, pan_right_dur, cam.tilt_down, tilt_down_dur),
    ]
    for label, filename, pan_fn, pan_dur, tilt_fn, tilt_dur in corner_moves:
        center()
        pan_fn(pan_dur)
        tilt_fn(tilt_dur)
        time.sleep(SETTLE_TIME)
        capture_photo(label, filename)

    # Reset
    center()
    cam.zoom_to(ZOOM_MIN)

    cap.release()
    print(f"  Photo tour complete: {len(photos)} photos captured")
    return photos


class Check:
    def __init__(self, category: str, name: str, passed: bool, detail: str = "", duration_ms: float = 0):
        self.category = category
        self.name = name
        self.passed = passed
        self.detail = detail
        self.duration_ms = duration_ms


def run_checks(device: str | None = None) -> list[Check]:
    results: list[Check] = []

    def check(category: str, name: str, passed: bool, detail: str = "", duration_ms: float = 0) -> bool:
        results.append(Check(category, name, passed, detail, duration_ms))
        icon = "\033[32m+\033[0m" if passed else "\033[31mx\033[0m"
        print(f"  [{icon}] {name}" + (f"  ({detail})" if detail else ""))
        return passed

    def timed(fn):
        t0 = time.monotonic()
        try:
            result = fn()
            elapsed = (time.monotonic() - t0) * 1000
            return result, elapsed
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return e, elapsed

    # ==========================================
    # SYSTEM ENVIRONMENT
    # ==========================================
    print("\n  System Environment")
    print("  " + "-" * 40)

    check("System", "Operating system", True,
          f"{platform.system()} {platform.release()} ({platform.machine()})")

    # Python version
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    check("System", "Python >= 3.10", py_ok, py_ver)

    # v4l2-ctl
    v4l2_path = shutil.which("v4l2-ctl")
    check("System", "v4l2-ctl installed", v4l2_path is not None,
          v4l2_path or "not found - install v4l-utils")

    # ffmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    check("System", "ffmpeg installed", ffmpeg_path is not None,
          ffmpeg_path or "not found")

    # arecord
    arecord_path = shutil.which("arecord")
    check("System", "arecord (ALSA) installed", arecord_path is not None,
          arecord_path or "not found")

    # Ollama
    ollama_path = shutil.which("ollama")
    check("System", "Ollama installed", ollama_path is not None,
          ollama_path or "not found")

    # Virtual environment
    in_venv = sys.prefix != sys.base_prefix
    check("System", "Python virtual environment active", in_venv,
          sys.prefix if in_venv else "not in venv")

    # GPU
    gpu_info = "unknown"
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
    except Exception:
        pass
    check("System", "NVIDIA GPU available", gpu_info != "unknown", gpu_info)

    # ==========================================
    # PYTHON PACKAGES
    # ==========================================
    print("\n  Python Packages")
    print("  " + "-" * 40)

    def check_import(module: str, display_name: str | None = None):
        name = display_name or module
        try:
            mod = __import__(module)
            ver = getattr(mod, "__version__", getattr(mod, "VERSION", "installed"))
            check("Packages", name, True, str(ver))
        except ImportError:
            check("Packages", name, False, "not installed")

    check_import("bcc950")
    check_import("cv2", "opencv-python")
    check_import("numpy")
    check_import("sounddevice")
    check_import("whisper", "openai-whisper")
    check_import("requests")

    # ==========================================
    # CAMERA HARDWARE
    # ==========================================
    print("\n  Camera Hardware")
    print("  " + "-" * 40)

    cam = None
    cam_device = device

    try:
        from bcc950 import BCC950Controller
        cam = BCC950Controller(device=cam_device)
        if cam_device is None:
            found = cam.find_camera()
            if found:
                cam_device = found
                check("Camera", "BCC950 auto-detected", True, found)
            else:
                check("Camera", "BCC950 auto-detected", False, "not found")
        else:
            check("Camera", "Camera device specified", True, cam_device)
    except Exception as e:
        check("Camera", "BCC950 controller", False, str(e))

    if cam:
        # PTZ support
        try:
            ptz = cam.has_ptz_support()
            check("Camera", "PTZ controls available", ptz)
        except Exception as e:
            check("Camera", "PTZ controls available", False, str(e))

        # Pan test
        result, ms = timed(lambda: cam.pan_left(0.3))
        if not isinstance(result, Exception):
            time.sleep(0.1)
            timed(lambda: cam.pan_right(0.3))
            check("Camera", "Pan left/right", True, f"{ms:.0f}ms")
        else:
            check("Camera", "Pan left/right", False, str(result))

        # Tilt test
        result, ms = timed(lambda: cam.tilt_up(0.3))
        if not isinstance(result, Exception):
            time.sleep(0.1)
            timed(lambda: cam.tilt_down(0.3))
            check("Camera", "Tilt up/down", True, f"{ms:.0f}ms")
        else:
            check("Camera", "Tilt up/down", False, str(result))

        # Zoom test
        result, ms = timed(lambda: cam.zoom_to(200))
        if not isinstance(result, Exception):
            time.sleep(0.2)
            cam.zoom_to(100)
            check("Camera", "Zoom control", True, f"{ms:.0f}ms")
        else:
            check("Camera", "Zoom control", False, str(result))

        # Read zoom
        try:
            zoom_val = cam.get_zoom()
            check("Camera", "Read zoom from hardware", True, f"zoom={zoom_val}")
        except Exception as e:
            check("Camera", "Read zoom from hardware", False, str(e))

        # OpenCV frame capture
        try:
            import cv2
            cap = cv2.VideoCapture(cam.device)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    cv2.imwrite("/tmp/bcc950_report_frame.jpg", frame)
                    check("Camera", "Frame capture (OpenCV)", True, f"{w}x{h}")
                else:
                    check("Camera", "Frame capture (OpenCV)", False, "empty frame")
            else:
                check("Camera", "Frame capture (OpenCV)", False, "could not open device")
        except ImportError:
            check("Camera", "Frame capture (OpenCV)", False, "opencv not installed")
        except Exception as e:
            check("Camera", "Frame capture (OpenCV)", False, str(e))

    # ==========================================
    # AUDIO
    # ==========================================
    print("\n  Audio")
    print("  " + "-" * 40)

    # Check for BCC950 mic in ALSA
    bcc_audio_card = None
    try:
        result = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "bcc950" in line.lower() or "conferencecam" in line.lower():
                    bcc_audio_card = line.split("card")[1].strip().split(":")[0].strip()
                    break
        check("Audio", "BCC950 microphone (ALSA)", bcc_audio_card is not None,
              f"card {bcc_audio_card}" if bcc_audio_card else "not found")
    except Exception as e:
        check("Audio", "BCC950 microphone (ALSA)", False, str(e))

    # Check sounddevice can list devices
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d["max_input_channels"] > 0]
        check("Audio", "Audio input devices (sounddevice)", len(input_devs) > 0,
              f"{len(input_devs)} input device(s)")
    except Exception as e:
        check("Audio", "Audio input devices", False, str(e))

    # ==========================================
    # PIPER TTS
    # ==========================================
    print("\n  Piper TTS")
    print("  " + "-" * 40)

    piper_bin = os.path.join(PROJECT_ROOT, "models", "piper", "piper")
    piper_model = os.path.join(PROJECT_ROOT, "models", "piper", "en_US-amy-medium.onnx")

    check("TTS", "Piper binary", os.path.isfile(piper_bin) and os.access(piper_bin, os.X_OK),
          piper_bin if os.path.isfile(piper_bin) else "not found")
    check("TTS", "Amy voice model (.onnx)", os.path.isfile(piper_model),
          piper_model if os.path.isfile(piper_model) else "not found")

    if os.path.isfile(piper_bin) and os.path.isfile(piper_model):
        try:
            proc = subprocess.run(
                [piper_bin, "--model", piper_model, "--output_file", "/tmp/bcc950_tts_test.wav"],
                input=b"Test", capture_output=True, timeout=10
            )
            tts_ok = proc.returncode == 0 and os.path.isfile("/tmp/bcc950_tts_test.wav")
            check("TTS", "Piper synthesis test", tts_ok,
                  "generated /tmp/bcc950_tts_test.wav" if tts_ok else proc.stderr.decode()[:100])
        except Exception as e:
            check("TTS", "Piper synthesis test", False, str(e))
    else:
        check("TTS", "Piper synthesis test", False, "binary or model missing")

    # ==========================================
    # OLLAMA / AI MODELS
    # ==========================================
    print("\n  AI Models (Ollama)")
    print("  " + "-" * 40)

    if ollama_path:
        # Check if ollama is running
        try:
            result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
            ollama_running = result.returncode == 0
            check("AI", "Ollama service running", ollama_running)

            if ollama_running:
                models = result.stdout.strip()
                has_qwen = "qwen3-vl:32b" in models
                has_gemma = "gemma3:4b" in models
                check("AI", "qwen3-vl:32b (primary vision LLM)", has_qwen,
                      "available" if has_qwen else "not pulled - run: ollama pull qwen3-vl:32b")
                check("AI", "gemma3:4b (fallback vision LLM)", has_gemma,
                      "available" if has_gemma else "not pulled")

                # Quick inference test with smallest available model
                test_model = "gemma3:4b" if has_gemma else None
                if test_model:
                    try:
                        t0 = time.monotonic()
                        result = subprocess.run(
                            ["ollama", "run", test_model, "Say hello in 3 words"],
                            capture_output=True, text=True, timeout=30
                        )
                        elapsed = (time.monotonic() - t0) * 1000
                        infer_ok = result.returncode == 0 and len(result.stdout.strip()) > 0
                        check("AI", f"Ollama inference test ({test_model})", infer_ok,
                              f"{elapsed:.0f}ms" if infer_ok else result.stderr[:100])
                    except subprocess.TimeoutExpired:
                        check("AI", f"Ollama inference test ({test_model})", False, "timeout >30s")
                    except Exception as e:
                        check("AI", f"Ollama inference test ({test_model})", False, str(e))
        except Exception as e:
            check("AI", "Ollama service", False, str(e))
    else:
        check("AI", "Ollama service", False, "ollama not installed")

    # ==========================================
    # WHISPER STT
    # ==========================================
    print("\n  Whisper STT")
    print("  " + "-" * 40)

    try:
        import whisper
        check("Whisper", "Whisper package", True, whisper.__version__ if hasattr(whisper, "__version__") else "installed")
        # Check if large-v3 model is cached
        model_dir = os.path.expanduser("~/.cache/whisper")
        large_v3_exists = os.path.isfile(os.path.join(model_dir, "large-v3.pt"))
        check("Whisper", "large-v3 model cached", large_v3_exists,
              "ready" if large_v3_exists else "will download on first use (~3GB)")
    except ImportError:
        check("Whisper", "Whisper package", False, "not installed")

    # ==========================================
    # PROJECT FILES
    # ==========================================
    print("\n  Project Structure")
    print("  " + "-" * 40)

    key_files = [
        ("Project", "src/python/bcc950/__init__.py", "bcc950 package"),
        ("Project", "src/python/pyproject.toml", "package config"),
        ("Project", "scripts/setup.sh", "setup script"),
        ("Project", "scripts/verify_hardware.py", "hardware verification"),
        ("Project", "scripts/generate_report.py", "report generator"),
        ("Project", "demos/embodied/conversation.py", "embodied AI demo"),
        ("Project", "demos/voice/voice_control.py", "voice control demo"),
        ("Project", "demos/voice/narrator.py", "narrator demo"),
        ("Project", "docs/setup_guide.md", "setup guide"),
        ("Project", "docs/usage_scenarios.md", "usage scenarios"),
    ]
    for cat, rel_path, desc in key_files:
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        check(cat, desc, os.path.isfile(full_path), rel_path)

    return results


GITHUB_URL = "https://github.com/mvalancy/logitech_bcc950"


def _build_calibration_html() -> str:
    """Build HTML for calibration data section if calibration.json exists."""
    cal = load_calibration()
    if not cal:
        return (
            '<div class="category">'
            '<div class="category-header fail">'
            '<span class="cat-icon">&#x274C;</span>'
            '<span class="cat-name">Calibration</span>'
            '<span class="cat-count">not calibrated</span>'
            '</div>'
            '<table><tr><td class="check-detail" style="padding:1rem;">'
            '<span class="detail">Run <code>python scripts/auto_tune.py</code> to calibrate range of motion</span>'
            '</td></tr></table>'
            '</div>'
        )

    measured = cal.get("measured_at", "unknown")
    device = cal.get("device", "unknown")
    rows = [
        ("Pan Left", f'{cal.get("pan_left_seconds", "?")}s from center'),
        ("Pan Right", f'{cal.get("pan_right_seconds", "?")}s from center'),
        ("Tilt Up", f'{cal.get("tilt_up_seconds", "?")}s from center'),
        ("Tilt Down", f'{cal.get("tilt_down_seconds", "?")}s from center'),
        ("Zoom Range", f'{cal.get("zoom_min", "?")} - {cal.get("zoom_max", "?")}'),
        ("Device", device),
        ("Measured At", measured),
    ]
    row_html = ""
    for name, val in rows:
        row_html += (
            f'<tr><td class="icon">&#x1F4CF;</td>'
            f'<td class="check-name">{html.escape(name)}</td>'
            f'<td class="check-detail"><span class="detail">{html.escape(str(val))}</span></td></tr>'
        )

    return (
        '<div class="category">'
        '<div class="category-header pass">'
        '<span class="cat-icon">&#x2705;</span>'
        '<span class="cat-name">Calibration (Range of Motion)</span>'
        '<span class="cat-count">calibrated</span>'
        '</div>'
        f'<table>{row_html}</table>'
        '</div>'
    )


def _build_photo_gallery_html(photos: dict[str, str] | None) -> str:
    """Build HTML for the photo gallery section with base64-embedded images."""
    if not photos:
        return ""

    # Desired display order
    order = [
        "Center", "Zoom Min (100)", "Zoom Max (500)",
        "Full Left", "Full Right", "Full Up", "Full Down",
        "Upper Left", "Upper Right", "Lower Left", "Lower Right",
    ]
    ordered = [(label, photos[label]) for label in order if label in photos]
    # Include any extras not in the predefined order
    seen = {label for label, _ in ordered}
    for label, path in photos.items():
        if label not in seen:
            ordered.append((label, path))

    cards = []
    for label, filepath in ordered:
        if not os.path.isfile(filepath):
            continue
        with open(filepath, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("ascii")
        cards.append(
            f'<div class="photo-card">'
            f'<img src="data:image/jpeg;base64,{img_data}" alt="{html.escape(label)}">'
            f'<div class="photo-label">{html.escape(label)}</div>'
            f'</div>'
        )

    if not cards:
        return ""

    return (
        '<div class="photo-section">'
        '<h2>Camera Position Photos</h2>'
        '<div class="photo-grid">'
        + "".join(cards)
        + '</div></div>'
    )


def generate_html(results: list[Check], output_path: str, photos: dict[str, str] | None = None) -> None:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    passed = sum(1 for c in results if c.passed)
    failed = sum(1 for c in results if not c.passed)
    total = len(results)
    pct = (passed / total * 100) if total else 0

    # Group by category
    categories: dict[str, list[Check]] = {}
    for c in results:
        categories.setdefault(c.category, []).append(c)

    # Build category HTML
    cat_html_parts = []
    for cat_name, checks in categories.items():
        cat_passed = sum(1 for c in checks if c.passed)
        cat_total = len(checks)
        cat_all_pass = cat_passed == cat_total

        rows = []
        for c in checks:
            icon = "&#x2705;" if c.passed else "&#x274C;"
            status_class = "pass" if c.passed else "fail"
            detail_html = f'<span class="detail">{html.escape(c.detail)}</span>' if c.detail else ""
            rows.append(f"""
                <tr class="{status_class}">
                    <td class="icon">{icon}</td>
                    <td class="check-name">{html.escape(c.name)}</td>
                    <td class="check-detail">{detail_html}</td>
                </tr>""")

        cat_icon = "&#x2705;" if cat_all_pass else "&#x274C;"
        cat_status = "pass" if cat_all_pass else "fail"
        cat_html_parts.append(f"""
        <div class="category">
            <div class="category-header {cat_status}">
                <span class="cat-icon">{cat_icon}</span>
                <span class="cat-name">{html.escape(cat_name)}</span>
                <span class="cat-count">{cat_passed}/{cat_total}</span>
            </div>
            <table>
                {"".join(rows)}
            </table>
        </div>""")

    # Overall status
    if failed == 0:
        overall_class = "overall-pass"
        overall_text = "ALL CHECKS PASSED"
        overall_icon = "&#x2705;"
    else:
        overall_class = "overall-fail"
        overall_text = f"{failed} CHECK{'S' if failed != 1 else ''} FAILED"
        overall_icon = "&#x274C;"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BCC950 System Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #0f0f0f;
        color: #e0e0e0;
        padding: 2rem;
        max-width: 900px;
        margin: 0 auto;
    }}
    h1 {{
        font-size: 1.8rem;
        margin-bottom: 0.3rem;
        color: #fff;
    }}
    .subtitle {{
        color: #888;
        margin-bottom: 2rem;
        font-size: 0.9rem;
    }}
    .overall {{
        padding: 1.5rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        text-align: center;
        font-size: 1.3rem;
        font-weight: 700;
    }}
    .overall-pass {{
        background: linear-gradient(135deg, #0a2e0a, #1a4a1a);
        border: 2px solid #2d7a2d;
        color: #5cdb5c;
    }}
    .overall-fail {{
        background: linear-gradient(135deg, #2e0a0a, #4a1a1a);
        border: 2px solid #7a2d2d;
        color: #db5c5c;
    }}
    .stats {{
        display: flex;
        gap: 1rem;
        margin-bottom: 2rem;
    }}
    .stat-box {{
        flex: 1;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        background: #1a1a1a;
        border: 1px solid #333;
    }}
    .stat-box .number {{
        font-size: 2rem;
        font-weight: 700;
    }}
    .stat-box .label {{
        font-size: 0.8rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .stat-box.pass .number {{ color: #5cdb5c; }}
    .stat-box.fail .number {{ color: #db5c5c; }}
    .stat-box.total .number {{ color: #5cabdb; }}
    .stat-box.pct .number {{ color: {("#5cdb5c" if pct >= 80 else "#dbdb5c" if pct >= 50 else "#db5c5c")}; }}
    .progress-bar {{
        width: 100%;
        height: 8px;
        background: #333;
        border-radius: 4px;
        margin-bottom: 2rem;
        overflow: hidden;
    }}
    .progress-fill {{
        height: 100%;
        border-radius: 4px;
        background: linear-gradient(90deg, #5cdb5c, #3dba3d);
        width: {pct:.1f}%;
        transition: width 0.3s;
    }}
    .category {{
        margin-bottom: 1.5rem;
        background: #1a1a1a;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #2a2a2a;
    }}
    .category-header {{
        padding: 0.8rem 1.2rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
        font-weight: 600;
        font-size: 1.05rem;
        border-bottom: 1px solid #2a2a2a;
    }}
    .category-header.pass {{ background: #0d1f0d; }}
    .category-header.fail {{ background: #1f0d0d; }}
    .cat-count {{
        margin-left: auto;
        font-size: 0.85rem;
        color: #888;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
    }}
    tr {{
        border-bottom: 1px solid #222;
    }}
    tr:last-child {{
        border-bottom: none;
    }}
    tr:hover {{
        background: #222;
    }}
    td {{
        padding: 0.6rem 1rem;
        vertical-align: middle;
    }}
    td.icon {{
        width: 2.5rem;
        text-align: center;
        font-size: 1.1rem;
    }}
    td.check-name {{
        font-weight: 500;
        white-space: nowrap;
    }}
    td.check-detail {{
        text-align: right;
    }}
    .detail {{
        color: #888;
        font-size: 0.85rem;
        font-family: 'SF Mono', 'Fira Code', monospace;
    }}
    tr.fail td.check-name {{
        color: #db8c8c;
    }}
    .footer {{
        text-align: center;
        color: #555;
        font-size: 0.8rem;
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid #222;
    }}
    .photo-section {{
        margin-top: 2rem;
    }}
    .photo-section h2 {{
        font-size: 1.4rem;
        margin-bottom: 1rem;
        color: #fff;
    }}
    .photo-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 1rem;
    }}
    .photo-card {{
        background: #1a1a1a;
        border: 1px solid #2a2a2a;
        border-radius: 10px;
        overflow: hidden;
    }}
    .photo-card img {{
        width: 100%;
        display: block;
    }}
    .photo-card .photo-label {{
        padding: 0.6rem 1rem;
        font-size: 0.9rem;
        color: #ccc;
        text-align: center;
        border-top: 1px solid #2a2a2a;
    }}
</style>
</head>
<body>
    <h1>BCC950 System Report</h1>
    <div class="subtitle">Generated {html.escape(now)} &bull; {html.escape(platform.node())} &bull; <a href="{GITHUB_URL}" style="color:#5cabdb;">{GITHUB_URL}</a></div>

    <div class="overall {overall_class}">
        {overall_icon} {overall_text}
    </div>

    <div class="stats">
        <div class="stat-box pass">
            <div class="number">{passed}</div>
            <div class="label">Passed</div>
        </div>
        <div class="stat-box fail">
            <div class="number">{failed}</div>
            <div class="label">Failed</div>
        </div>
        <div class="stat-box total">
            <div class="number">{total}</div>
            <div class="label">Total</div>
        </div>
        <div class="stat-box pct">
            <div class="number">{pct:.0f}%</div>
            <div class="label">Score</div>
        </div>
    </div>

    <div class="progress-bar">
        <div class="progress-fill"></div>
    </div>

    {"".join(cat_html_parts)}

    {_build_calibration_html()}

    {_build_photo_gallery_html(photos)}

    <div class="footer">
        <a href="{GITHUB_URL}" style="color:#5cabdb;">Logitech BCC950 Camera Control</a> &bull; End-to-End Verification Report
    </div>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html_content)


def main():
    parser = argparse.ArgumentParser(description="Generate BCC950 HTML test report")
    parser.add_argument("--device", default=None, help="V4L2 device path (auto-detect if omitted)")
    parser.add_argument("--output", default=None, help="Output HTML file path")
    parser.add_argument("--no-photos", action="store_true", help="Skip photo tour")
    args = parser.parse_args()

    output = args.output or os.path.join(PROJECT_ROOT, "report.html")
    output = os.path.abspath(output)

    print("=" * 50)
    print("  BCC950 System Report Generator")
    print("=" * 50)

    results = run_checks(device=args.device)

    # Photo tour
    photos: dict[str, str] = {}
    if not args.no_photos:
        # Determine camera device from check results
        cam_device = args.device
        if cam_device is None:
            for c in results:
                if c.name == "BCC950 auto-detected" and c.passed:
                    cam_device = c.detail
                    break
        if cam_device:
            print("\n  Photo Tour")
            print("  " + "-" * 40)
            photos = run_photo_tour(cam_device)
        else:
            print("\n  Skipping photo tour: no camera device available")

    # Load existing photos from disk if none were captured this run
    if not photos:
        photos_dir = os.path.join(PROJECT_ROOT, "reports", "photos")
        known_photos = [
            ("Center", "center.jpg"),
            ("Zoom Min (100)", "zoom_min.jpg"),
            ("Zoom Max (500)", "zoom_max.jpg"),
            ("Full Left", "full_left.jpg"),
            ("Full Right", "full_right.jpg"),
            ("Full Up", "full_up.jpg"),
            ("Full Down", "full_down.jpg"),
            ("Upper Left", "upper_left.jpg"),
            ("Upper Right", "upper_right.jpg"),
            ("Lower Left", "lower_left.jpg"),
            ("Lower Right", "lower_right.jpg"),
        ]
        for label, filename in known_photos:
            path = os.path.join(photos_dir, filename)
            if os.path.isfile(path):
                photos[label] = path
        if photos:
            print(f"\n  Loaded {len(photos)} existing photos from reports/photos/")

    generate_html(results, output, photos)

    passed = sum(1 for c in results if c.passed)
    failed = sum(1 for c in results if not c.passed)
    total = len(results)

    print()
    print("=" * 50)
    if failed == 0:
        print(f"  \033[32mAll {total} checks passed!\033[0m")
    else:
        print(f"  {passed}/{total} passed, \033[31m{failed} failed\033[0m")
    print(f"  Report saved to: {output}")
    print("=" * 50)

    # Try to open in browser
    try:
        import webbrowser
        webbrowser.open(f"file://{output}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
