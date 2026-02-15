#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <stdexcept>
#include <linux/videodev2.h>

namespace bcc950 {

/// Runtime error for V4L2 operations.
class V4L2Error : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

/// Abstract interface for V4L2 device operations.
/// Enables dependency injection and test mocking.
class IV4L2Device {
public:
    virtual ~IV4L2Device() = default;

    /// Set a V4L2 control to the given value.
    virtual void set_control(uint32_t id, int32_t value) = 0;

    /// Get the current value of a V4L2 control.
    virtual int32_t get_control(uint32_t id) = 0;

    /// Query metadata for a V4L2 control.
    virtual struct v4l2_queryctrl query_control(uint32_t id) = 0;

    /// Open the device at the given path.
    virtual void open(const std::string& device) = 0;

    /// Close the device.
    virtual void close() = 0;

    /// Returns true if the device is currently open.
    virtual bool is_open() const = 0;
};

/// Concrete V4L2 device implementation using ioctl system calls.
class V4L2Device : public IV4L2Device {
public:
    V4L2Device() = default;
    explicit V4L2Device(const std::string& device);
    ~V4L2Device() override;

    // Non-copyable
    V4L2Device(const V4L2Device&) = delete;
    V4L2Device& operator=(const V4L2Device&) = delete;

    // Movable
    V4L2Device(V4L2Device&& other) noexcept;
    V4L2Device& operator=(V4L2Device&& other) noexcept;

    void set_control(uint32_t id, int32_t value) override;
    int32_t get_control(uint32_t id) override;
    struct v4l2_queryctrl query_control(uint32_t id) override;

    void open(const std::string& device) override;
    void close() override;
    bool is_open() const override;

    /// Return the file descriptor (mainly for diagnostics).
    int fd() const { return fd_; }

private:
    int fd_ = -1;
    std::string device_path_;
};

} // namespace bcc950
