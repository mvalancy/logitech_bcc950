#include "bcc950/controller.hpp"

#include <stdexcept>

namespace bcc950 {

Controller::Controller(
    std::unique_ptr<IV4L2Device> device,
    const std::string& device_path,
    const std::string& config_path,
    const std::string& presets_path)
    : v4l2_device_(std::move(device))
    , config_(config_path)
    , position_()
    , motion_(v4l2_device_.get(), &position_)
    , presets_(presets_path)
{
    config_.load();
    device_path_ = device_path.empty() ? config_.device() : device_path;

    // Open the V4L2 device if not already open
    if (!v4l2_device_->is_open()) {
        v4l2_device_->open(device_path_);
    }
}

const std::string& Controller::device_path() const {
    return device_path_;
}

void Controller::set_device_path(const std::string& path) {
    device_path_ = path;
    if (v4l2_device_->is_open()) {
        v4l2_device_->close();
    }
    v4l2_device_->open(path);
}

const PositionTracker& Controller::position() const {
    return position_;
}

Config& Controller::config() {
    return config_;
}

const Config& Controller::config() const {
    return config_;
}

// --- Backward-compatible API ---

void Controller::pan_left(double duration) {
    motion_.pan(-config_.pan_speed(), duration);
}

void Controller::pan_right(double duration) {
    motion_.pan(config_.pan_speed(), duration);
}

void Controller::tilt_up(double duration) {
    motion_.tilt(config_.tilt_speed(), duration);
}

void Controller::tilt_down(double duration) {
    motion_.tilt(-config_.tilt_speed(), duration);
}

void Controller::zoom_in() {
    motion_.zoom_relative(config_.zoom_step());
}

void Controller::zoom_out() {
    motion_.zoom_relative(-config_.zoom_step());
}

void Controller::reset_position() {
    motion_.pan(1, 0.1);
    motion_.pan(-1, 0.1);
    motion_.tilt(1, 0.1);
    motion_.tilt(-1, 0.1);
    motion_.zoom_absolute(ZOOM_MIN);
    position_.reset();
}

// --- New API ---

void Controller::move(int pan_dir, int tilt_dir, double duration) {
    motion_.combined_move(pan_dir, tilt_dir, duration);
}

void Controller::zoom_to(int value) {
    motion_.zoom_absolute(value);
}

void Controller::move_with_zoom(int pan_dir, int tilt_dir,
                                 int zoom_target, double duration) {
    motion_.combined_move_with_zoom(pan_dir, tilt_dir, zoom_target, duration);
}

void Controller::save_preset(const std::string& name) {
    presets_.save_preset(name, position_);
}

bool Controller::recall_preset(const std::string& name) {
    auto pos = presets_.recall_preset(name);
    if (!pos) {
        return false;
    }
    motion_.zoom_absolute(pos->zoom);
    return true;
}

bool Controller::delete_preset(const std::string& name) {
    return presets_.delete_preset(name);
}

std::vector<std::string> Controller::list_presets() const {
    return presets_.list_presets();
}

// --- Info ---

int Controller::get_zoom() {
    return v4l2_device_->get_control(CTRL_ZOOM_ABSOLUTE);
}

bool Controller::has_ptz_support() {
    try {
        v4l2_device_->query_control(CTRL_PAN_SPEED);
        v4l2_device_->query_control(CTRL_TILT_SPEED);
        v4l2_device_->query_control(CTRL_ZOOM_ABSOLUTE);
        return true;
    } catch (const V4L2Error&) {
        return false;
    }
}

void Controller::stop() {
    motion_.stop();
}

} // namespace bcc950
