#include <gtest/gtest.h>

#include <memory>
#include <utility>

#include "bcc950/constants.hpp"
#include "bcc950/controller.hpp"
#include "mock_v4l2_device.hpp"

namespace bcc950 {
namespace {

/// Fixture that creates a Controller backed by a MockV4L2Device.
class ControllerTest : public ::testing::Test {
protected:
    void SetUp() override {
        auto device = std::make_unique<testing::MockV4L2Device>();
        mock_ = device.get();  // keep raw pointer for inspection
        // Use empty paths so no real files are touched
        controller_ = std::make_unique<Controller>(
            std::move(device),
            /*device_path=*/"",
            /*config_path=*/"/dev/null",
            /*presets_path=*/"/dev/null"
        );
    }

    testing::MockV4L2Device* mock_ = nullptr;
    std::unique_ptr<Controller> controller_;
};

// ----- Pan tests -----

TEST_F(ControllerTest, PanLeftSetsPanSpeedNegativeThenZero) {
    controller_->pan_left();

    const auto& calls = mock_->get_calls();
    // Expect at least two pan_speed calls: negative then zero
    bool found_negative = false;
    bool found_stop = false;
    int stop_index = -1;
    int negative_index = -1;

    for (std::size_t i = 0; i < calls.size(); ++i) {
        if (calls[i].first == CTRL_PAN_SPEED) {
            if (calls[i].second < 0) {
                found_negative = true;
                negative_index = static_cast<int>(i);
            }
            if (calls[i].second == 0 && found_negative) {
                found_stop = true;
                stop_index = static_cast<int>(i);
            }
        }
    }

    EXPECT_TRUE(found_negative) << "Expected a negative pan_speed call for pan_left";
    EXPECT_TRUE(found_stop) << "Expected pan_speed=0 after negative speed";
    if (found_negative && found_stop) {
        EXPECT_GT(stop_index, negative_index)
            << "Stop must come after the negative speed";
    }
}

TEST_F(ControllerTest, PanRightSetsPanSpeedPositiveThenZero) {
    controller_->pan_right();

    const auto& calls = mock_->get_calls();
    bool found_positive = false;
    bool found_stop = false;
    int positive_index = -1;
    int stop_index = -1;

    for (std::size_t i = 0; i < calls.size(); ++i) {
        if (calls[i].first == CTRL_PAN_SPEED) {
            if (calls[i].second > 0) {
                found_positive = true;
                positive_index = static_cast<int>(i);
            }
            if (calls[i].second == 0 && found_positive) {
                found_stop = true;
                stop_index = static_cast<int>(i);
            }
        }
    }

    EXPECT_TRUE(found_positive) << "Expected a positive pan_speed call for pan_right";
    EXPECT_TRUE(found_stop) << "Expected pan_speed=0 after positive speed";
    if (found_positive && found_stop) {
        EXPECT_GT(stop_index, positive_index)
            << "Stop must come after the positive speed";
    }
}

// ----- Tilt tests -----

TEST_F(ControllerTest, TiltUpSetsTiltSpeedPositiveThenZero) {
    controller_->tilt_up();

    const auto& calls = mock_->get_calls();
    bool found_positive = false;
    bool found_stop = false;
    int positive_index = -1;
    int stop_index = -1;

    for (std::size_t i = 0; i < calls.size(); ++i) {
        if (calls[i].first == CTRL_TILT_SPEED) {
            if (calls[i].second > 0) {
                found_positive = true;
                positive_index = static_cast<int>(i);
            }
            if (calls[i].second == 0 && found_positive) {
                found_stop = true;
                stop_index = static_cast<int>(i);
            }
        }
    }

    EXPECT_TRUE(found_positive) << "Expected a positive tilt_speed call for tilt_up";
    EXPECT_TRUE(found_stop) << "Expected tilt_speed=0 after positive speed";
    if (found_positive && found_stop) {
        EXPECT_GT(stop_index, positive_index);
    }
}

TEST_F(ControllerTest, TiltDownSetsTiltSpeedNegativeThenZero) {
    controller_->tilt_down();

    const auto& calls = mock_->get_calls();
    bool found_negative = false;
    bool found_stop = false;
    int negative_index = -1;
    int stop_index = -1;

    for (std::size_t i = 0; i < calls.size(); ++i) {
        if (calls[i].first == CTRL_TILT_SPEED) {
            if (calls[i].second < 0) {
                found_negative = true;
                negative_index = static_cast<int>(i);
            }
            if (calls[i].second == 0 && found_negative) {
                found_stop = true;
                stop_index = static_cast<int>(i);
            }
        }
    }

    EXPECT_TRUE(found_negative) << "Expected a negative tilt_speed call for tilt_down";
    EXPECT_TRUE(found_stop) << "Expected tilt_speed=0 after negative speed";
    if (found_negative && found_stop) {
        EXPECT_GT(stop_index, negative_index);
    }
}

// ----- Zoom tests -----

TEST_F(ControllerTest, ZoomClampsToZoomMax) {
    controller_->zoom_to(9999);  // way above ZOOM_MAX

    int32_t stored = mock_->get_stored_value(CTRL_ZOOM_ABSOLUTE);
    EXPECT_LE(stored, ZOOM_MAX) << "Zoom should be clamped to ZOOM_MAX";
}

TEST_F(ControllerTest, ZoomClampsToZoomMin) {
    controller_->zoom_to(-100);  // below ZOOM_MIN

    int32_t stored = mock_->get_stored_value(CTRL_ZOOM_ABSOLUTE);
    EXPECT_GE(stored, ZOOM_MIN) << "Zoom should be clamped to ZOOM_MIN";
}

TEST_F(ControllerTest, ZoomToValidValue) {
    const int target = 250;
    controller_->zoom_to(target);

    int32_t stored = mock_->get_stored_value(CTRL_ZOOM_ABSOLUTE);
    EXPECT_EQ(stored, target);
}

// ----- Reset position test -----

TEST_F(ControllerTest, ResetPositionIssuesMultipleCalls) {
    controller_->reset_position();

    const auto& calls = mock_->get_calls();
    // A reset should issue at least some pan and tilt control calls
    bool has_pan_call = false;
    bool has_tilt_call = false;
    bool has_zoom_call = false;

    for (const auto& call : calls) {
        if (call.first == CTRL_PAN_SPEED)     has_pan_call = true;
        if (call.first == CTRL_TILT_SPEED)    has_tilt_call = true;
        if (call.first == CTRL_ZOOM_ABSOLUTE) has_zoom_call = true;
    }

    EXPECT_TRUE(has_pan_call)  << "Reset should touch pan control";
    EXPECT_TRUE(has_tilt_call) << "Reset should touch tilt control";
    EXPECT_TRUE(has_zoom_call) << "Reset should touch zoom control";
}

TEST_F(ControllerTest, ResetPositionEndsWithZeroPanAndTilt) {
    controller_->reset_position();

    // After reset, the last pan_speed and tilt_speed should be 0
    int32_t final_pan = mock_->get_stored_value(CTRL_PAN_SPEED);
    int32_t final_tilt = mock_->get_stored_value(CTRL_TILT_SPEED);

    EXPECT_EQ(final_pan, 0)  << "Pan speed should be 0 after reset";
    EXPECT_EQ(final_tilt, 0) << "Tilt speed should be 0 after reset";
}

TEST_F(ControllerTest, ResetPositionSetsZoomToDefault) {
    // First zoom in
    controller_->zoom_to(400);
    mock_->clear_calls();

    controller_->reset_position();

    int32_t final_zoom = mock_->get_stored_value(CTRL_ZOOM_ABSOLUTE);
    EXPECT_EQ(final_zoom, ZOOM_DEFAULT) << "Zoom should reset to ZOOM_DEFAULT (ZOOM_MIN)";
}

} // anonymous namespace
} // namespace bcc950
