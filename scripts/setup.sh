#!/bin/bash
# BCC950 Full Environment Setup
# Idempotent: safe to run multiple times. Each phase skips if already done.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
MODELS_DIR="$PROJECT_ROOT/models"
PIPER_DIR="$MODELS_DIR/piper"
PIPER_VERSION="2023.11.14-2"
PIPER_VOICE="en_US-amy-medium"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "      $1"; }

echo "========================================"
echo "  BCC950 Environment Setup"
echo "========================================"
echo ""

# --- Phase 1: System packages ---
echo "--- Phase 1: System packages ---"

install_apt_package() {
    local pkg="$1"
    local desc="$2"
    if dpkg -s "$pkg" &>/dev/null; then
        skip "$desc ($pkg already installed)"
    else
        info "Installing $pkg..."
        sudo apt-get install -y "$pkg" >/dev/null 2>&1 && pass "$desc" || fail "$desc"
    fi
}

# Update apt cache once if anything needs installing
NEEDS_UPDATE=false
for pkg in v4l-utils portaudio19-dev ffmpeg python3-venv python3-dev; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        NEEDS_UPDATE=true
        break
    fi
done

if $NEEDS_UPDATE; then
    info "Updating apt cache..."
    sudo apt-get update -qq >/dev/null 2>&1
fi

install_apt_package "v4l-utils"      "v4l2-ctl (V4L2 camera control)"
install_apt_package "portaudio19-dev" "PortAudio (audio I/O)"
install_apt_package "ffmpeg"          "FFmpeg (audio/video processing)"
install_apt_package "python3-venv"    "Python venv support"
install_apt_package "python3-dev"     "Python development headers"
install_apt_package "alsa-utils"      "ALSA utilities (arecord/aplay)"
echo ""

# --- Phase 2: Python virtual environment ---
echo "--- Phase 2: Python virtual environment ---"

if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    skip "Virtual environment already exists at .venv/"
else
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" && pass "Created .venv/" || fail "Could not create .venv/"
fi

# Activate venv for remaining phases
source "$VENV_DIR/bin/activate"
info "Using Python: $(which python) ($(python --version))"
echo ""

# --- Phase 3: Python packages ---
echo "--- Phase 3: Python packages ---"

install_pip_package() {
    local pkg="$1"
    local desc="$2"
    if python -c "import ${pkg%%[>=<]*}" 2>/dev/null; then
        skip "$desc (already installed)"
    else
        info "Installing $desc..."
        pip install -q "$pkg" 2>/dev/null && pass "$desc" || fail "$desc"
    fi
}

pip install -q --upgrade pip >/dev/null 2>&1

install_pip_package "numpy"           "NumPy"
install_pip_package "opencv-python"   "OpenCV"
install_pip_package "sounddevice"     "sounddevice (audio capture)"
install_pip_package "openai-whisper"  "OpenAI Whisper (speech-to-text)"
install_pip_package "requests"        "requests (HTTP client)"
echo ""

# --- Phase 4: Install bcc950 package ---
echo "--- Phase 4: bcc950 Python package ---"

if python -c "import bcc950" 2>/dev/null; then
    skip "bcc950 package already installed"
else
    info "Installing bcc950 in editable mode..."
    if pip install -e "$PROJECT_ROOT/src/python" 2>&1 | tail -5; then
        pass "bcc950 package (editable)"
    else
        fail "bcc950 package install"
        info "Try: pip install -e src/python"
    fi
fi
echo ""

# --- Phase 5: Piper TTS ---
echo "--- Phase 5: Piper TTS (Amy voice) ---"

mkdir -p "$PIPER_DIR"

# Detect architecture
ARCH=$(uname -m)
case "$ARCH" in
    aarch64) PIPER_ARCH="aarch64" ;;
    x86_64)  PIPER_ARCH="amd64" ;;
    *)       fail "Unsupported architecture: $ARCH"; PIPER_ARCH="" ;;
esac

if [ -x "$PIPER_DIR/piper" ]; then
    skip "Piper binary already installed"
else
    if [ -n "$PIPER_ARCH" ]; then
        PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz"
        info "Downloading Piper binary ($PIPER_ARCH)..."
        if curl -sL "$PIPER_URL" | tar xz -C "$MODELS_DIR" 2>/dev/null; then
            chmod +x "$PIPER_DIR/piper" 2>/dev/null || true
            pass "Piper binary"
        else
            fail "Piper binary download (try manually: $PIPER_URL)"
        fi
    fi
fi

VOICE_ONNX="$PIPER_DIR/${PIPER_VOICE}.onnx"
VOICE_JSON="$PIPER_DIR/${PIPER_VOICE}.onnx.json"

if [ -f "$VOICE_ONNX" ] && [ -f "$VOICE_JSON" ]; then
    skip "Amy voice model already installed"
else
    HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium"
    info "Downloading Amy voice model..."
    VOICE_OK=true
    curl -sL "${HF_BASE}/${PIPER_VOICE}.onnx" -o "$VOICE_ONNX" 2>/dev/null || VOICE_OK=false
    curl -sL "${HF_BASE}/${PIPER_VOICE}.onnx.json" -o "$VOICE_JSON" 2>/dev/null || VOICE_OK=false
    if $VOICE_OK && [ -s "$VOICE_ONNX" ]; then
        pass "Amy voice model (${PIPER_VOICE})"
    else
        fail "Amy voice model download"
        rm -f "$VOICE_ONNX" "$VOICE_JSON" 2>/dev/null
    fi
fi
echo ""

# --- Phase 6: Ollama vision model ---
echo "--- Phase 6: Ollama vision model ---"

if command -v ollama &>/dev/null; then
    # Check if qwen3-vl:32b is already pulled
    if ollama list 2>/dev/null | grep -q "qwen3-vl:32b"; then
        skip "qwen3-vl:32b already pulled"
    else
        info "Pulling qwen3-vl:32b (21GB, this may take a while)..."
        if ollama pull qwen3-vl:32b 2>&1; then
            pass "qwen3-vl:32b vision model"
        else
            fail "qwen3-vl:32b pull (run manually: ollama pull qwen3-vl:32b)"
        fi
    fi

    # Ensure gemma3:4b fallback is available
    if ollama list 2>/dev/null | grep -q "gemma3:4b"; then
        skip "gemma3:4b fallback already available"
    else
        info "Pulling gemma3:4b fallback..."
        ollama pull gemma3:4b 2>&1 && pass "gemma3:4b fallback" || skip "gemma3:4b (optional)"
    fi
else
    fail "Ollama not installed (see https://ollama.com)"
fi
echo ""

# --- Phase 7: User/group permissions ---
echo "--- Phase 7: Permissions ---"

if groups | grep -q video; then
    skip "User already in 'video' group"
else
    info "Adding $USER to 'video' group..."
    sudo usermod -aG video "$USER" && pass "Added to video group (re-login to take effect)" || fail "Could not add to video group"
fi
echo ""

# --- Phase 8: Hardware verification ---
echo "--- Phase 8: Hardware verification ---"

# Detect BCC950
if command -v v4l2-ctl &>/dev/null; then
    DEVICES=$(v4l2-ctl --list-devices 2>/dev/null || true)
    if echo "$DEVICES" | grep -q "BCC950"; then
        BCC_DEV=$(echo "$DEVICES" | grep -A 2 "BCC950" | grep "/dev/video" | head -1 | tr -d '\t ')
        pass "BCC950 detected at $BCC_DEV"

        # Quick PTZ test
        info "Testing PTZ controls..."
        if v4l2-ctl -d "$BCC_DEV" --list-ctrls 2>/dev/null | grep -q "pan_speed"; then
            # Pan left briefly, stop
            v4l2-ctl -d "$BCC_DEV" -c pan_speed=-1 2>/dev/null
            sleep 0.3
            v4l2-ctl -d "$BCC_DEV" -c pan_speed=0 2>/dev/null
            sleep 0.2
            # Pan right briefly, stop
            v4l2-ctl -d "$BCC_DEV" -c pan_speed=1 2>/dev/null
            sleep 0.3
            v4l2-ctl -d "$BCC_DEV" -c pan_speed=0 2>/dev/null
            sleep 0.2
            # Zoom test
            v4l2-ctl -d "$BCC_DEV" -c zoom_absolute=200 2>/dev/null
            sleep 0.3
            v4l2-ctl -d "$BCC_DEV" -c zoom_absolute=100 2>/dev/null
            pass "PTZ controls responding"
        else
            fail "PTZ controls not found on $BCC_DEV"
        fi

        # Test audio
        info "Testing BCC950 microphone (1s recording)..."
        if arecord -l 2>/dev/null | grep -qi "bcc950\|conferencecam"; then
            AUDIO_CARD=$(arecord -l 2>/dev/null | grep -i "bcc950\|conferencecam" | head -1 | sed 's/card \([0-9]*\):.*/\1/')
            if timeout 2 arecord -D "hw:${AUDIO_CARD},0" -d 1 -f S16_LE -r 16000 /tmp/bcc950_mic_test.wav >/dev/null 2>&1; then
                pass "Microphone recording (card $AUDIO_CARD)"
                rm -f /tmp/bcc950_mic_test.wav
            else
                fail "Microphone recording (card $AUDIO_CARD)"
            fi
        else
            skip "BCC950 microphone not found in ALSA devices"
        fi

        # Test Piper TTS
        if [ -x "$PIPER_DIR/piper" ] && [ -f "$VOICE_ONNX" ]; then
            info "Testing Piper TTS..."
            if echo "Hello, I am Amy." | "$PIPER_DIR/piper" --model "$VOICE_ONNX" --output_file /tmp/bcc950_tts_test.wav >/dev/null 2>&1; then
                pass "Piper TTS synthesis"
                # Play if aplay is available
                if command -v aplay &>/dev/null; then
                    aplay /tmp/bcc950_tts_test.wav >/dev/null 2>&1 || true
                fi
                rm -f /tmp/bcc950_tts_test.wav
            else
                fail "Piper TTS synthesis"
            fi
        else
            skip "Piper not installed, skipping TTS test"
        fi
    else
        fail "BCC950 not detected in v4l2 device list"
        info "Available devices:"
        echo "$DEVICES" | head -20
    fi
else
    fail "v4l2-ctl not available"
fi
echo ""

# --- Summary ---
echo "========================================"
echo "  Setup Complete"
echo "========================================"
echo ""
echo "Next steps:"
echo "  source .venv/bin/activate"
echo "  python scripts/verify_hardware.py"
echo "  python scripts/generate_report.py"
echo "  python demos/embodied/conversation.py"
echo ""
