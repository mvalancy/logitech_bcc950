#include "bcc950/position.hpp"

#include <algorithm>
#include <cmath>

namespace bcc950 {

void PositionTracker::update_pan(int speed, double duration) {
    pan += speed * duration;
    pan = std::clamp(pan, pan_min, pan_max);
}

void PositionTracker::update_tilt(int speed, double duration) {
    tilt += speed * duration;
    tilt = std::clamp(tilt, tilt_min, tilt_max);
}

void PositionTracker::update_zoom(int value) {
    zoom = std::clamp(value, ZOOM_MIN, ZOOM_MAX);
}

double PositionTracker::distance_to(const PositionTracker& other) const {
    double dp = pan - other.pan;
    double dt = tilt - other.tilt;
    return std::sqrt(dp * dp + dt * dt);
}

void PositionTracker::reset() {
    pan  = 0.0;
    tilt = 0.0;
    zoom = ZOOM_DEFAULT;
}

} // namespace bcc950
