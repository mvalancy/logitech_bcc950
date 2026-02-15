#include <gtest/gtest.h>

#include <memory>

#include "bcc950/constants.hpp"
#include "bcc950/motion.hpp"
#include "bcc950/position.hpp"
#include "mock_v4l2_device.hpp"

namespace bcc950 {
namespace {

/// Fixture providing a MotionController wired to a MockV4L2Device.
class MotionTest : public ::testing::Test {
protected:
    void SetUp() override {
        mock_ = std::make_unique<testing::MockV4L2Device>();
        position_ = PositionTracker{};
        motion_ = std::make_unique<MotionController>(mock_.get(), &position_);
    }

    std::unique_ptr<testing::MockV4L2Device> mock_;
    PositionTracker position_;
    std::unique_ptr<MotionController> motion_;
};

// ---- Pan tests ----

TEST_F(MotionTest, PanSetsSpeedAndStops) {
    motion_->pan(-1, 0.01);  // pan left, short duration

    const auto& calls = mock_->get_calls();
    ASSERT_GE(calls.size(), 2u);

    // First call: set pan speed to -1
    EXPECT_EQ(calls[0].first, CTRL_PAN_SPEED);
    EXPECT_EQ(calls[0].second, -1);

    // Second call: stop pan (set to 0)
    EXPECT_EQ(calls[1].first, CTRL_PAN_SPEED);
    EXPECT_EQ(calls[1].second, 0);
}

TEST_F(MotionTest, PanRightSetsPositiveSpeed) {
    motion_->pan(1, 0.01);

    const auto& calls = mock_->get_calls();
    ASSERT_GE(calls.size(), 2u);

    EXPECT_EQ(calls[0].first, CTRL_PAN_SPEED);
    EXPECT_EQ(calls[0].second, 1);

    EXPECT_EQ(calls[1].first, CTRL_PAN_SPEED);
    EXPECT_EQ(calls[1].second, 0);
}

TEST_F(MotionTest, PanUpdatesPositionTracker) {
    position_.pan = 0.0;
    motion_->pan(1, 0.5);

    // Position should have accumulated speed * duration
    EXPECT_DOUBLE_EQ(position_.pan, 0.5);
}

// ---- Tilt tests ----

TEST_F(MotionTest, TiltSetsSpeedAndStops) {
    motion_->tilt(1, 0.01);  // tilt up

    const auto& calls = mock_->get_calls();
    ASSERT_GE(calls.size(), 2u);

    EXPECT_EQ(calls[0].first, CTRL_TILT_SPEED);
    EXPECT_EQ(calls[0].second, 1);

    EXPECT_EQ(calls[1].first, CTRL_TILT_SPEED);
    EXPECT_EQ(calls[1].second, 0);
}

TEST_F(MotionTest, TiltDownSetsNegativeSpeed) {
    motion_->tilt(-1, 0.01);

    const auto& calls = mock_->get_calls();
    ASSERT_GE(calls.size(), 2u);

    EXPECT_EQ(calls[0].first, CTRL_TILT_SPEED);
    EXPECT_EQ(calls[0].second, -1);

    EXPECT_EQ(calls[1].first, CTRL_TILT_SPEED);
    EXPECT_EQ(calls[1].second, 0);
}

TEST_F(MotionTest, TiltUpdatesPositionTracker) {
    position_.tilt = 0.0;
    motion_->tilt(-1, 0.3);

    EXPECT_DOUBLE_EQ(position_.tilt, -0.3);
}

// ---- Combined move tests ----

TEST_F(MotionTest, CombinedMoveSetsBothAxes) {
    motion_->combined_move(1, -1, 0.01);  // pan right + tilt down

    const auto& calls = mock_->get_calls();
    // Should have at least 4 calls: set pan, set tilt, stop pan, stop tilt
    ASSERT_GE(calls.size(), 4u);

    // First two: set both speeds
    EXPECT_EQ(calls[0].first, CTRL_PAN_SPEED);
    EXPECT_EQ(calls[0].second, 1);
    EXPECT_EQ(calls[1].first, CTRL_TILT_SPEED);
    EXPECT_EQ(calls[1].second, -1);

    // Last two: stop both
    EXPECT_EQ(calls[2].first, CTRL_PAN_SPEED);
    EXPECT_EQ(calls[2].second, 0);
    EXPECT_EQ(calls[3].first, CTRL_TILT_SPEED);
    EXPECT_EQ(calls[3].second, 0);
}

TEST_F(MotionTest, CombinedMoveUpdatesBothPositionAxes) {
    position_.pan = 0.0;
    position_.tilt = 0.0;
    motion_->combined_move(1, 1, 0.2);

    EXPECT_DOUBLE_EQ(position_.pan, 0.2);
    EXPECT_DOUBLE_EQ(position_.tilt, 0.2);
}

// ---- Zoom absolute tests ----

TEST_F(MotionTest, ZoomAbsoluteSetsValue) {
    motion_->zoom_absolute(300);

    const auto& calls = mock_->get_calls();
    ASSERT_EQ(calls.size(), 1u);
    EXPECT_EQ(calls[0].first, CTRL_ZOOM_ABSOLUTE);
    EXPECT_EQ(calls[0].second, 300);
}

TEST_F(MotionTest, ZoomAbsoluteClampsAboveMax) {
    motion_->zoom_absolute(9999);

    const auto& calls = mock_->get_calls();
    ASSERT_EQ(calls.size(), 1u);
    EXPECT_EQ(calls[0].second, ZOOM_MAX);
    EXPECT_EQ(position_.zoom, ZOOM_MAX);
}

TEST_F(MotionTest, ZoomAbsoluteClampsBelowMin) {
    motion_->zoom_absolute(-50);

    const auto& calls = mock_->get_calls();
    ASSERT_EQ(calls.size(), 1u);
    EXPECT_EQ(calls[0].second, ZOOM_MIN);
    EXPECT_EQ(position_.zoom, ZOOM_MIN);
}

TEST_F(MotionTest, ZoomAbsoluteUpdatesPosition) {
    motion_->zoom_absolute(350);
    EXPECT_EQ(position_.zoom, 350);
}

// ---- Zoom relative tests ----

TEST_F(MotionTest, ZoomRelativeAddsToCurrentZoom) {
    // Position starts at ZOOM_DEFAULT (100)
    motion_->zoom_relative(50);

    EXPECT_EQ(position_.zoom, ZOOM_DEFAULT + 50);
}

TEST_F(MotionTest, ZoomRelativeClampsAboveMax) {
    position_.zoom = 480;
    motion_->zoom_relative(100);  // would be 580, clamped to 500

    EXPECT_EQ(position_.zoom, ZOOM_MAX);
}

TEST_F(MotionTest, ZoomRelativeClampsBelowMin) {
    position_.zoom = 120;
    motion_->zoom_relative(-200);  // would be -80, clamped to 100

    EXPECT_EQ(position_.zoom, ZOOM_MIN);
}

// ---- Stop test ----

TEST_F(MotionTest, StopSetsBothSpeedsToZero) {
    motion_->stop();

    const auto& calls = mock_->get_calls();
    ASSERT_EQ(calls.size(), 2u);
    EXPECT_EQ(calls[0].first, CTRL_PAN_SPEED);
    EXPECT_EQ(calls[0].second, 0);
    EXPECT_EQ(calls[1].first, CTRL_TILT_SPEED);
    EXPECT_EQ(calls[1].second, 0);
}

} // anonymous namespace
} // namespace bcc950
