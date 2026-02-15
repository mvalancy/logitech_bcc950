#pragma once

#include <cstdint>
#include <string>
#include <linux/v4l2-controls.h>

namespace bcc950 {

// V4L2 control IDs (from linux/v4l2-controls.h)
constexpr uint32_t CTRL_PAN_SPEED      = V4L2_CID_PAN_SPEED;
constexpr uint32_t CTRL_TILT_SPEED     = V4L2_CID_TILT_SPEED;
constexpr uint32_t CTRL_ZOOM_ABSOLUTE  = V4L2_CID_ZOOM_ABSOLUTE;

// Zoom limits
constexpr int ZOOM_MIN     = 100;
constexpr int ZOOM_MAX     = 500;
constexpr int ZOOM_DEFAULT = ZOOM_MIN;

// Speed limits
constexpr int PAN_SPEED_MIN  = -1;
constexpr int PAN_SPEED_MAX  =  1;
constexpr int TILT_SPEED_MIN = -1;
constexpr int TILT_SPEED_MAX =  1;

// Default speeds
constexpr int DEFAULT_PAN_SPEED  = 1;
constexpr int DEFAULT_TILT_SPEED = 1;
constexpr int DEFAULT_ZOOM_STEP  = 10;

// Default movement duration (seconds)
constexpr double DEFAULT_MOVE_DURATION = 0.1;

// Estimated position range (movement-seconds based)
constexpr double EST_PAN_MIN  = -5.0;
constexpr double EST_PAN_MAX  =  5.0;
constexpr double EST_TILT_MIN = -3.0;
constexpr double EST_TILT_MAX =  3.0;

// Config / presets file names
inline const std::string DEFAULT_CONFIG_FILENAME  = ".bcc950_config";
inline const std::string DEFAULT_PRESETS_FILENAME  = ".bcc950_presets.json";

// Default device path
inline const std::string DEFAULT_DEVICE = "/dev/video0";

} // namespace bcc950
