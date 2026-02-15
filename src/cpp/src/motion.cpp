#include "bcc950/motion.hpp"

#include <algorithm>
#include <thread>
#include <chrono>

namespace bcc950 {

MotionController::MotionController(IV4L2Device* device, PositionTracker* position)
    : device_(device)
    , owned_position_()
    , position_(position ? position : &owned_position_) {
}

int MotionController::clamp_speed(int value) {
    return std::clamp(value, PAN_SPEED_MIN, PAN_SPEED_MAX);
}

int MotionController::clamp_zoom(int value) {
    return std::clamp(value, ZOOM_MIN, ZOOM_MAX);
}

void MotionController::pan(int direction, double duration) {
    int speed = clamp_speed(direction);
    std::lock_guard<std::mutex> lock(mutex_);
    device_->set_control(CTRL_PAN_SPEED, speed);
    std::this_thread::sleep_for(
        std::chrono::duration<double>(duration));
    device_->set_control(CTRL_PAN_SPEED, 0);
    position_->update_pan(speed, duration);
}

void MotionController::tilt(int direction, double duration) {
    int speed = clamp_speed(direction);
    std::lock_guard<std::mutex> lock(mutex_);
    device_->set_control(CTRL_TILT_SPEED, speed);
    std::this_thread::sleep_for(
        std::chrono::duration<double>(duration));
    device_->set_control(CTRL_TILT_SPEED, 0);
    position_->update_tilt(speed, duration);
}

void MotionController::combined_move(int pan_dir, int tilt_dir, double duration) {
    int pan_speed  = clamp_speed(pan_dir);
    int tilt_speed = clamp_speed(tilt_dir);
    std::lock_guard<std::mutex> lock(mutex_);
    device_->set_control(CTRL_PAN_SPEED, pan_speed);
    device_->set_control(CTRL_TILT_SPEED, tilt_speed);
    std::this_thread::sleep_for(
        std::chrono::duration<double>(duration));
    device_->set_control(CTRL_PAN_SPEED, 0);
    device_->set_control(CTRL_TILT_SPEED, 0);
    position_->update_pan(pan_speed, duration);
    position_->update_tilt(tilt_speed, duration);
}

void MotionController::combined_move_with_zoom(int pan_dir, int tilt_dir,
                                                int zoom_target, double duration) {
    int pan_speed  = clamp_speed(pan_dir);
    int tilt_speed = clamp_speed(tilt_dir);
    zoom_target    = clamp_zoom(zoom_target);
    std::lock_guard<std::mutex> lock(mutex_);
    device_->set_control(CTRL_PAN_SPEED, pan_speed);
    device_->set_control(CTRL_TILT_SPEED, tilt_speed);
    device_->set_control(CTRL_ZOOM_ABSOLUTE, zoom_target);
    std::this_thread::sleep_for(
        std::chrono::duration<double>(duration));
    device_->set_control(CTRL_PAN_SPEED, 0);
    device_->set_control(CTRL_TILT_SPEED, 0);
    position_->update_pan(pan_speed, duration);
    position_->update_tilt(tilt_speed, duration);
    position_->update_zoom(zoom_target);
}

void MotionController::zoom_absolute(int value) {
    value = clamp_zoom(value);
    std::lock_guard<std::mutex> lock(mutex_);
    device_->set_control(CTRL_ZOOM_ABSOLUTE, value);
    position_->update_zoom(value);
}

void MotionController::zoom_relative(int delta) {
    std::lock_guard<std::mutex> lock(mutex_);
    int new_value = clamp_zoom(position_->zoom + delta);
    device_->set_control(CTRL_ZOOM_ABSOLUTE, new_value);
    position_->update_zoom(new_value);
}

void MotionController::stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    device_->set_control(CTRL_PAN_SPEED, 0);
    device_->set_control(CTRL_TILT_SPEED, 0);
}

PositionTracker& MotionController::position() {
    return *position_;
}

const PositionTracker& MotionController::position() const {
    return *position_;
}

} // namespace bcc950
