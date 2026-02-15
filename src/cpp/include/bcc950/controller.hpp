#pragma once

#include <memory>
#include <string>
#include <vector>

#include "config.hpp"
#include "constants.hpp"
#include "motion.hpp"
#include "position.hpp"
#include "presets.hpp"
#include "v4l2_device.hpp"

namespace bcc950 {

/// High-level controller for the Logitech BCC950 camera.
///
/// Backward-compatible API (pan_left(), tilt_up(), etc.) plus new
/// methods (move(), zoom_to(), save_preset(), recall_preset()).
class Controller {
public:
    /// Construct with an injected V4L2 device, optional device path,
    /// config path, and presets path.
    explicit Controller(
        std::unique_ptr<IV4L2Device> device,
        const std::string& device_path = "",
        const std::string& config_path = "",
        const std::string& presets_path = ""
    );

    ~Controller() = default;

    // Non-copyable
    Controller(const Controller&) = delete;
    Controller& operator=(const Controller&) = delete;

    // Movable
    Controller(Controller&&) = default;
    Controller& operator=(Controller&&) = default;

    // --- Properties ---

    const std::string& device_path() const;
    void set_device_path(const std::string& path);

    const PositionTracker& position() const;
    Config& config();
    const Config& config() const;

    // --- Backward-compatible API ---

    void pan_left(double duration = DEFAULT_MOVE_DURATION);
    void pan_right(double duration = DEFAULT_MOVE_DURATION);
    void tilt_up(double duration = DEFAULT_MOVE_DURATION);
    void tilt_down(double duration = DEFAULT_MOVE_DURATION);
    void zoom_in();
    void zoom_out();
    void reset_position();

    // --- New API ---

    /// Combined pan+tilt move with configurable duration.
    void move(int pan_dir = 0, int tilt_dir = 0,
              double duration = DEFAULT_MOVE_DURATION);

    /// Set zoom to an absolute value.
    void zoom_to(int value);

    /// Combined pan + tilt + zoom.
    void move_with_zoom(int pan_dir = 0, int tilt_dir = 0,
                        int zoom_target = ZOOM_MIN,
                        double duration = DEFAULT_MOVE_DURATION);

    /// Save current position as a named preset.
    void save_preset(const std::string& name);

    /// Recall a named preset. Returns false if not found.
    bool recall_preset(const std::string& name);

    /// Delete a named preset. Returns false if not found.
    bool delete_preset(const std::string& name);

    /// List all preset names.
    std::vector<std::string> list_presets() const;

    // --- Info ---

    /// Get current zoom value from hardware.
    int get_zoom();

    /// Check if the device supports PTZ controls.
    bool has_ptz_support();

    /// Stop all movement.
    void stop();

private:
    std::unique_ptr<IV4L2Device> v4l2_device_;
    std::string device_path_;
    Config config_;
    PositionTracker position_;
    MotionController motion_;
    PresetManager presets_;
};

} // namespace bcc950
