#!/bin/bash

# Logitech BCC950 Camera Control Script
# This script controls the pan, tilt, and zoom functions of the Logitech BCC950 ConferenceCam
# using v4l2-ctl commands in Linux.

# Default device - will be auto-detected if possible
DEVICE="/dev/video0"

# Movement values
PAN_SPEED=1
TILT_SPEED=1
ZOOM_STEP=10

# Function to detect OS and install prerequisites if needed
setup() {
    echo "Setting up Logitech BCC950 camera control..."
    
    # Check if v4l2-ctl is installed
    if ! command -v v4l2-ctl &> /dev/null; then
        echo "v4l2-ctl not found. Installing prerequisites..."
        
        # Detect OS
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$NAME
        elif type lsb_release >/dev/null 2>&1; then
            OS=$(lsb_release -si)
        else
            OS=$(uname -s)
        fi
        
        # Install v4l-utils based on OS
        if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
            sudo apt-get update && sudo apt-get install -y v4l-utils
        elif [[ "$OS" == *"Fedora"* ]]; then
            sudo dnf install -y v4l-utils
        elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]]; then
            sudo yum install -y v4l-utils
        elif [[ "$OS" == *"Arch"* ]]; then
            sudo pacman -Sy v4l-utils
        else
            echo "Unsupported OS: $OS. Please install v4l-utils manually."
            exit 1
        fi
    else
        echo "v4l2-ctl is already installed."
    fi
    
    # Detect camera
    find_camera
    
    # Test camera connection
    test_camera
    
    echo "Setup complete."
    exit 0
}

# Function to find the BCC950 camera
find_camera() {
    echo "Looking for Logitech BCC950 camera..."
    
    # List all video devices
    v4l2-ctl --list-devices
    
    # Try to find BCC950 in the device list
    local devices=$(v4l2-ctl --list-devices 2>/dev/null)
    if echo "$devices" | grep -q "BCC950"; then
        local dev_path=$(echo "$devices" | grep -A 2 "BCC950" | grep "/dev/video" | head -n 1 | tr -d '\t')
        if [ -n "$dev_path" ]; then
            echo "Found Logitech BCC950 at: $dev_path"
            DEVICE="$dev_path"
            return 0
        fi
    fi
    
    # If not found by name, check all video devices for pan/tilt support
    echo "Checking all video devices for PTZ support..."
    local all_video_devices=$(find /dev -name "video*" | sort)
    
    for dev in $all_video_devices; do
        echo "Testing $dev..."
        # Check if device supports pan_speed control
        if v4l2-ctl -d "$dev" --list-ctrls 2>/dev/null | grep -q "pan_speed"; then
            echo "Found compatible PTZ camera at: $dev"
            DEVICE="$dev"
            return 0
        fi
    done
    
    echo "No compatible camera found. Using default device: $DEVICE"
    echo "You may need to specify the device manually with --device option."
    return 1
}

# Function to test camera connection
test_camera() {
    echo "Testing camera controls..."
    
    if [ ! -e "$DEVICE" ]; then
        echo "ERROR: Camera device $DEVICE does not exist."
        return 1
    fi
    
    # Get list of available controls
    echo "Available camera controls:"
    v4l2-ctl -d "$DEVICE" --list-ctrls
    
    # Test pan_speed control if available
    if v4l2-ctl -d "$DEVICE" --list-ctrls | grep -q "pan_speed"; then
        echo "Pan control is available."
    else
        echo "WARNING: Pan control not found for this camera."
    fi
    
    # Test tilt_speed control if available
    if v4l2-ctl -d "$DEVICE" --list-ctrls | grep -q "tilt_speed"; then
        echo "Tilt control is available."
    else
        echo "WARNING: Tilt control not found for this camera."
    fi
    
    # Test zoom_absolute control if available
    if v4l2-ctl -d "$DEVICE" --list-ctrls | grep -q "zoom_absolute"; then
        echo "Zoom control is available."
    else
        echo "WARNING: Zoom control not found for this camera."
    fi
    
    return 0
}

# Pan camera left
pan_left() {
    echo "Panning left..."
    v4l2-ctl -d "$DEVICE" -c pan_speed=-$PAN_SPEED
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
}

# Pan camera right
pan_right() {
    echo "Panning right..."
    v4l2-ctl -d "$DEVICE" -c pan_speed=$PAN_SPEED
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
}

# Tilt camera up
tilt_up() {
    echo "Tilting up..."
    v4l2-ctl -d "$DEVICE" -c tilt_speed=$TILT_SPEED
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
}

# Tilt camera down
tilt_down() {
    echo "Tilting down..."
    v4l2-ctl -d "$DEVICE" -c tilt_speed=-$TILT_SPEED
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
}

# Zoom camera in
zoom_in() {
    echo "Zooming in..."
    local current_zoom=$(v4l2-ctl -d "$DEVICE" --get-ctrl=zoom_absolute | awk -F '=' '{print $2}')
    local new_zoom=$((current_zoom + ZOOM_STEP))
    # Ensure we don't exceed maximum zoom (usually 500 for BCC950)
    if [[ $new_zoom -gt 500 ]]; then
        new_zoom=500
    fi
    v4l2-ctl -d "$DEVICE" -c zoom_absolute=$new_zoom
}

# Zoom camera out
zoom_out() {
    echo "Zooming out..."
    local current_zoom=$(v4l2-ctl -d "$DEVICE" --get-ctrl=zoom_absolute | awk -F '=' '{print $2}')
    local new_zoom=$((current_zoom - ZOOM_STEP))
    # Ensure we don't go below minimum zoom (usually 100 for BCC950)
    if [[ $new_zoom -lt 100 ]]; then
        new_zoom=100
    fi
    v4l2-ctl -d "$DEVICE" -c zoom_absolute=$new_zoom
}

# Reset camera position
reset_position() {
    echo "Resetting camera position..."
    # For relative controls, we need to center by briefly moving in both directions
    v4l2-ctl -d "$DEVICE" -c pan_speed=1
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c pan_speed=-1
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    
    v4l2-ctl -d "$DEVICE" -c tilt_speed=1
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c tilt_speed=-1
    sleep 0.1
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    
    # Reset zoom to default/minimum
    v4l2-ctl -d "$DEVICE" -c zoom_absolute=100
}

# Display usage information
usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  --setup               Install prerequisites and detect camera"
    echo "  -d, --device DEVICE   Specify camera device (default: $DEVICE)"
    echo "  -l, --list            List available camera devices"
    echo "  --pan-left            Pan camera left"
    echo "  --pan-right           Pan camera right"
    echo "  --tilt-up             Tilt camera up"
    echo "  --tilt-down           Tilt camera down"
    echo "  --zoom-in             Zoom camera in"
    echo "  --zoom-out            Zoom camera out"
    echo "  --reset               Reset camera to default position"
    echo "  --demo                Run a demonstration sequence of camera movements"
    echo "  --info                Show camera information and controls"
    echo "  -h, --help            Show this help message"
    exit 1
}

# List available camera devices
list_devices() {
    echo "Available camera devices:"
    v4l2-ctl --list-devices
    exit 0
}

# Show camera information
show_info() {
    echo "Camera information for $DEVICE:"
    v4l2-ctl -d "$DEVICE" --all
    exit 0
}

# Load config file if it exists
if [ -f ~/.bcc950_config ]; then
    source ~/.bcc950_config
fi

# Function to run a demo sequence showing camera capabilities
run_demo() {
    echo "Running camera demonstration sequence..."
    
    # Make sure camera works
    if [ ! -e "$DEVICE" ]; then
        echo "ERROR: Camera device $DEVICE does not exist."
        return 1
    fi
    
    echo "Starting demo in 3 seconds..."
    sleep 3
    
    # Reset zoom to minimum to start
    v4l2-ctl -d "$DEVICE" -c zoom_absolute=100
    sleep 1
    
    echo "Beginning circular sweep pattern with zoom..."
    
    # Start with pan left while zooming in
    echo "Panning left while zooming in..."
    v4l2-ctl -d "$DEVICE" -c pan_speed=-$PAN_SPEED
    for zoom in $(seq 100 20 300); do
        v4l2-ctl -d "$DEVICE" -c zoom_absolute=$zoom
        sleep 0.3
    done
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    sleep 1
    
    # Tilt up while maintaining zoom
    echo "Tilting up..."
    v4l2-ctl -d "$DEVICE" -c tilt_speed=$TILT_SPEED
    sleep 3
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    sleep 1
    
    # Pan right while zooming out
    echo "Panning right while zooming out..."
    v4l2-ctl -d "$DEVICE" -c pan_speed=$PAN_SPEED
    for zoom in $(seq 300 -20 100); do
        v4l2-ctl -d "$DEVICE" -c zoom_absolute=$zoom
        sleep 0.3
    done
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    sleep 1
    
    # Tilt down to complete the circle
    echo "Tilting down..."
    v4l2-ctl -d "$DEVICE" -c tilt_speed=-$TILT_SPEED
    sleep 3
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    sleep 1
    
    # Do a full zoom-in/zoom-out cycle
    echo "Demonstrating full zoom range..."
    # Zoom all the way in
    for zoom in $(seq 100 20 500); do
        v4l2-ctl -d "$DEVICE" -c zoom_absolute=$zoom
        sleep 0.1
    done
    sleep 2
    # Zoom all the way out
    for zoom in $(seq 500 -20 100); do
        v4l2-ctl -d "$DEVICE" -c zoom_absolute=$zoom
        sleep 0.1
    done
    
    # Perform a diagonal pattern
    echo "Performing diagonal movement..."
    # Diagonal up-right
    v4l2-ctl -d "$DEVICE" -c pan_speed=$PAN_SPEED
    v4l2-ctl -d "$DEVICE" -c tilt_speed=$TILT_SPEED
    sleep 2
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    sleep 1
    
    # Diagonal down-left
    v4l2-ctl -d "$DEVICE" -c pan_speed=-$PAN_SPEED
    v4l2-ctl -d "$DEVICE" -c tilt_speed=-$TILT_SPEED
    sleep 2
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    sleep 1
    
    # Diagonal up-left
    v4l2-ctl -d "$DEVICE" -c pan_speed=-$PAN_SPEED
    v4l2-ctl -d "$DEVICE" -c tilt_speed=$TILT_SPEED
    sleep 2
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    sleep 1
    
    # Diagonal down-right
    v4l2-ctl -d "$DEVICE" -c pan_speed=$PAN_SPEED
    v4l2-ctl -d "$DEVICE" -c tilt_speed=-$TILT_SPEED
    sleep 2
    v4l2-ctl -d "$DEVICE" -c pan_speed=0
    v4l2-ctl -d "$DEVICE" -c tilt_speed=0
    
    echo "Demo sequence completed."
    
    # Reset camera position
    reset_position
    
    return 0
}

# Parse command line arguments
if [[ $# -eq 0 ]]; then
    usage
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --setup)
            setup
            ;;
        -d|--device)
            DEVICE="$2"
            shift 2
            ;;
        -l|--list)
            list_devices
            ;;
        --pan-left)
            pan_left
            shift
            ;;
        --pan-right)
            pan_right
            shift
            ;;
        --tilt-up)
            tilt_up
            shift
            ;;
        --tilt-down)
            tilt_down
            shift
            ;;
        --zoom-in)
            zoom_in
            shift
            ;;
        --zoom-out)
            zoom_out
            shift
            ;;
        --reset)
            reset_position
            shift
            ;;
        --demo)
            run_demo
            shift
            ;;
        --info)
            show_info
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

exit 0
