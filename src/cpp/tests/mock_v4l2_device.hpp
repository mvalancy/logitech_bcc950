#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "bcc950/v4l2_device.hpp"

namespace bcc950 {
namespace testing {

/// In-memory mock of IV4L2Device for unit testing.
///
/// Records every set_control call as a (id, value) pair and stores
/// control values in a map so that get_control can return them.
class MockV4L2Device : public IV4L2Device {
public:
    using Call = std::pair<uint32_t, int32_t>;

    MockV4L2Device() = default;
    ~MockV4L2Device() override = default;

    // ---- IV4L2Device interface ----

    void set_control(uint32_t id, int32_t value) override {
        calls_.emplace_back(id, value);
        values_[id] = value;
    }

    int32_t get_control(uint32_t id) override {
        auto it = values_.find(id);
        return (it != values_.end()) ? it->second : 0;
    }

    struct v4l2_queryctrl query_control(uint32_t id) override {
        struct v4l2_queryctrl qctrl{};
        qctrl.id = id;
        // Provide sensible defaults for testing
        qctrl.minimum = 0;
        qctrl.maximum = 100;
        qctrl.step = 1;
        qctrl.default_value = 0;
        qctrl.type = V4L2_CTRL_TYPE_INTEGER;
        return qctrl;
    }

    void open(const std::string& /*device*/) override {
        open_ = true;
    }

    void close() override {
        open_ = false;
    }

    bool is_open() const override {
        return open_;
    }

    // ---- Test helpers ----

    /// Return all recorded set_control calls.
    const std::vector<Call>& get_calls() const { return calls_; }

    /// Clear the recorded call log.
    void clear_calls() { calls_.clear(); }

    /// Return the stored value for a control id (0 if never set).
    int32_t get_stored_value(uint32_t id) const {
        auto it = values_.find(id);
        return (it != values_.end()) ? it->second : 0;
    }

    /// Pre-seed a control value (e.g. to simulate initial zoom).
    void set_stored_value(uint32_t id, int32_t value) {
        values_[id] = value;
    }

    /// Return total number of set_control calls recorded.
    std::size_t call_count() const { return calls_.size(); }

private:
    bool open_ = true;
    std::vector<Call> calls_;
    std::unordered_map<uint32_t, int32_t> values_;
};

} // namespace testing
} // namespace bcc950
