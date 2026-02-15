"""Constants for Logitech BCC950 camera control."""

# Zoom limits
ZOOM_MIN = 100
ZOOM_MAX = 500
ZOOM_DEFAULT = ZOOM_MIN

# Speed limits
PAN_SPEED_MIN = -1
PAN_SPEED_MAX = 1
TILT_SPEED_MIN = -1
TILT_SPEED_MAX = 1

# Default speeds
DEFAULT_PAN_SPEED = 1
DEFAULT_TILT_SPEED = 1
DEFAULT_ZOOM_STEP = 10

# Default movement duration (seconds)
DEFAULT_MOVE_DURATION = 0.1

# V4L2 control names
CTRL_PAN_SPEED = "pan_speed"
CTRL_TILT_SPEED = "tilt_speed"
CTRL_ZOOM_ABSOLUTE = "zoom_absolute"

# Config file
DEFAULT_CONFIG_FILENAME = ".bcc950_config"
DEFAULT_PRESETS_FILENAME = ".bcc950_presets.json"

# Default device
DEFAULT_DEVICE = "/dev/video0"
