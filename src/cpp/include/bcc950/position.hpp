#pragma once

#include "constants.hpp"

namespace bcc950 {

/// Tracks estimated camera position based on movement-seconds.
///
/// The BCC950 has no absolute pan/tilt readback, so we accumulate
/// movement duration * speed to estimate position.
struct PositionTracker {
    double pan  = 0.0;
    double tilt = 0.0;
    int    zoom = ZOOM_DEFAULT;

    double pan_min  = EST_PAN_MIN;
    double pan_max  = EST_PAN_MAX;
    double tilt_min = EST_TILT_MIN;
    double tilt_max = EST_TILT_MAX;

    /// Update pan estimate: speed * duration added to position.
    void update_pan(int speed, double duration);

    /// Update tilt estimate: speed * duration added to position.
    void update_tilt(int speed, double duration);

    /// Update zoom to an absolute value (clamped).
    void update_zoom(int value);

    /// Euclidean distance to another position (pan/tilt only).
    double distance_to(const PositionTracker& other) const;

    /// Reset to origin.
    void reset();
};

} // namespace bcc950
