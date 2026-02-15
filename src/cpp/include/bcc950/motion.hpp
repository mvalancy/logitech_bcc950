#pragma once

#include <mutex>
#include <memory>

#include "constants.hpp"
#include "position.hpp"
#include "v4l2_device.hpp"

namespace bcc950 {

/// Thread-safe motion control for the BCC950.
///
/// All movement methods acquire a mutex so that start-sleep-stop
/// sequences are atomic.
class MotionController {
public:
    /// Construct with a V4L2 device (non-owning pointer).
    MotionController(IV4L2Device* device, PositionTracker* position = nullptr);

    /// Pan camera. direction: -1 (left) or 1 (right).
    void pan(int direction, double duration = DEFAULT_MOVE_DURATION);

    /// Tilt camera. direction: 1 (up) or -1 (down).
    void tilt(int direction, double duration = DEFAULT_MOVE_DURATION);

    /// Simultaneous pan + tilt.
    void combined_move(int pan_dir, int tilt_dir,
                       double duration = DEFAULT_MOVE_DURATION);

    /// Simultaneous pan + tilt + zoom to target.
    void combined_move_with_zoom(int pan_dir, int tilt_dir,
                                 int zoom_target,
                                 double duration = DEFAULT_MOVE_DURATION);

    /// Set zoom to an absolute value (clamped to ZOOM_MIN..ZOOM_MAX).
    void zoom_absolute(int value);

    /// Adjust zoom by a relative delta from current position.
    void zoom_relative(int delta);

    /// Stop all movement.
    void stop();

    /// Access the position tracker.
    PositionTracker& position();
    const PositionTracker& position() const;

private:
    IV4L2Device* device_;
    PositionTracker  owned_position_;
    PositionTracker* position_;
    std::mutex       mutex_;

    static int clamp_speed(int value);
    static int clamp_zoom(int value);
};

} // namespace bcc950
