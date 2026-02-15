#include "bcc950/v4l2_device.hpp"

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <linux/videodev2.h>

namespace bcc950 {

V4L2Device::V4L2Device(const std::string& device) {
    open(device);
}

V4L2Device::~V4L2Device() {
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
}

V4L2Device::V4L2Device(V4L2Device&& other) noexcept
    : fd_(other.fd_), device_path_(std::move(other.device_path_)) {
    other.fd_ = -1;
}

V4L2Device& V4L2Device::operator=(V4L2Device&& other) noexcept {
    if (this != &other) {
        if (fd_ >= 0) {
            ::close(fd_);
        }
        fd_ = other.fd_;
        device_path_ = std::move(other.device_path_);
        other.fd_ = -1;
    }
    return *this;
}

void V4L2Device::open(const std::string& device) {
    if (fd_ >= 0) {
        close();
    }

    fd_ = ::open(device.c_str(), O_RDWR | O_NONBLOCK);
    if (fd_ < 0) {
        throw V4L2Error("Failed to open device " + device + ": " +
                         std::strerror(errno));
    }
    device_path_ = device;
}

void V4L2Device::close() {
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
        device_path_.clear();
    }
}

bool V4L2Device::is_open() const {
    return fd_ >= 0;
}

void V4L2Device::set_control(uint32_t id, int32_t value) {
    if (fd_ < 0) {
        throw V4L2Error("Device not open");
    }

    struct v4l2_control ctrl{};
    ctrl.id = id;
    ctrl.value = value;

    if (::ioctl(fd_, VIDIOC_S_CTRL, &ctrl) < 0) {
        throw V4L2Error("VIDIOC_S_CTRL failed for control 0x" +
                         std::to_string(id) + ": " + std::strerror(errno));
    }
}

int32_t V4L2Device::get_control(uint32_t id) {
    if (fd_ < 0) {
        throw V4L2Error("Device not open");
    }

    struct v4l2_control ctrl{};
    ctrl.id = id;

    if (::ioctl(fd_, VIDIOC_G_CTRL, &ctrl) < 0) {
        throw V4L2Error("VIDIOC_G_CTRL failed for control 0x" +
                         std::to_string(id) + ": " + std::strerror(errno));
    }

    return ctrl.value;
}

struct v4l2_queryctrl V4L2Device::query_control(uint32_t id) {
    if (fd_ < 0) {
        throw V4L2Error("Device not open");
    }

    struct v4l2_queryctrl qctrl{};
    qctrl.id = id;

    if (::ioctl(fd_, VIDIOC_QUERYCTRL, &qctrl) < 0) {
        throw V4L2Error("VIDIOC_QUERYCTRL failed for control 0x" +
                         std::to_string(id) + ": " + std::strerror(errno));
    }

    return qctrl;
}

} // namespace bcc950
