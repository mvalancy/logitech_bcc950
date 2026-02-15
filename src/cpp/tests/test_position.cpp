#include <gtest/gtest.h>

#include <cmath>

#include "bcc950/constants.hpp"
#include "bcc950/position.hpp"

namespace bcc950 {
namespace {

class PositionTest : public ::testing::Test {
protected:
    PositionTracker pos;
};

// ---- Default state ----

TEST_F(PositionTest, DefaultValuesAreOrigin) {
    EXPECT_DOUBLE_EQ(pos.pan, 0.0);
    EXPECT_DOUBLE_EQ(pos.tilt, 0.0);
    EXPECT_EQ(pos.zoom, ZOOM_DEFAULT);
}

// ---- UpdatePanAccumulates ----

TEST_F(PositionTest, UpdatePanAccumulates) {
    pos.update_pan(1, 0.5);   // +0.5
    EXPECT_DOUBLE_EQ(pos.pan, 0.5);

    pos.update_pan(1, 0.3);   // +0.3 => 0.8
    EXPECT_DOUBLE_EQ(pos.pan, 0.8);

    pos.update_pan(-1, 0.2);  // -0.2 => 0.6
    EXPECT_DOUBLE_EQ(pos.pan, 0.6);
}

TEST_F(PositionTest, UpdatePanNegativeDirection) {
    pos.update_pan(-1, 1.0);
    EXPECT_DOUBLE_EQ(pos.pan, -1.0);
}

// ---- UpdateTiltAccumulates ----

TEST_F(PositionTest, UpdateTiltAccumulates) {
    pos.update_tilt(1, 0.4);
    EXPECT_DOUBLE_EQ(pos.tilt, 0.4);

    pos.update_tilt(1, 0.6);
    EXPECT_DOUBLE_EQ(pos.tilt, 1.0);

    pos.update_tilt(-1, 0.3);
    EXPECT_DOUBLE_EQ(pos.tilt, 0.7);
}

// ---- ClampsAtRange ----

TEST_F(PositionTest, ClampsAtPanMaxRange) {
    pos.update_pan(1, 100.0);
    EXPECT_DOUBLE_EQ(pos.pan, EST_PAN_MAX);
}

TEST_F(PositionTest, ClampsAtPanMinRange) {
    pos.update_pan(-1, 100.0);
    EXPECT_DOUBLE_EQ(pos.pan, EST_PAN_MIN);
}

TEST_F(PositionTest, ClampsAtTiltMaxRange) {
    pos.update_tilt(1, 100.0);
    EXPECT_DOUBLE_EQ(pos.tilt, EST_TILT_MAX);
}

TEST_F(PositionTest, ClampsAtTiltMinRange) {
    pos.update_tilt(-1, 100.0);
    EXPECT_DOUBLE_EQ(pos.tilt, EST_TILT_MIN);
}

TEST_F(PositionTest, ZoomClampsAboveMax) {
    pos.update_zoom(9999);
    EXPECT_EQ(pos.zoom, ZOOM_MAX);
}

TEST_F(PositionTest, ZoomClampsBelowMin) {
    pos.update_zoom(0);
    EXPECT_EQ(pos.zoom, ZOOM_MIN);
}

TEST_F(PositionTest, ZoomAcceptsValidValue) {
    pos.update_zoom(300);
    EXPECT_EQ(pos.zoom, 300);
}

TEST_F(PositionTest, PanClampsThenAccumulates) {
    // Clamp at max, then move back
    pos.update_pan(1, 100.0);
    EXPECT_DOUBLE_EQ(pos.pan, EST_PAN_MAX);

    pos.update_pan(-1, 2.0);
    EXPECT_DOUBLE_EQ(pos.pan, EST_PAN_MAX - 2.0);
}

// ---- DistanceTo ----

TEST_F(PositionTest, DistanceToSamePositionIsZero) {
    PositionTracker other;
    EXPECT_DOUBLE_EQ(pos.distance_to(other), 0.0);
}

TEST_F(PositionTest, DistanceToCalculatesEuclidean) {
    pos.pan = 3.0;
    pos.tilt = 0.0;

    PositionTracker other;
    other.pan = 0.0;
    other.tilt = 4.0;

    // distance = sqrt(3^2 + 4^2) = 5.0
    EXPECT_DOUBLE_EQ(pos.distance_to(other), 5.0);
}

TEST_F(PositionTest, DistanceToIsSymmetric) {
    pos.pan = 1.0;
    pos.tilt = 2.0;

    PositionTracker other;
    other.pan = -1.0;
    other.tilt = -1.0;

    EXPECT_DOUBLE_EQ(pos.distance_to(other), other.distance_to(pos));
}

TEST_F(PositionTest, DistanceToOnlyUsesPanTilt) {
    pos.pan = 1.0;
    pos.tilt = 0.0;
    pos.zoom = 500;

    PositionTracker other;
    other.pan = 0.0;
    other.tilt = 0.0;
    other.zoom = 100;

    // Zoom difference should not affect distance
    EXPECT_DOUBLE_EQ(pos.distance_to(other), 1.0);
}

// ---- Reset ----

TEST_F(PositionTest, ResetSetsPanToZero) {
    pos.pan = 3.5;
    pos.reset();
    EXPECT_DOUBLE_EQ(pos.pan, 0.0);
}

TEST_F(PositionTest, ResetSetsTiltToZero) {
    pos.tilt = -2.1;
    pos.reset();
    EXPECT_DOUBLE_EQ(pos.tilt, 0.0);
}

TEST_F(PositionTest, ResetSetsZoomToDefault) {
    pos.zoom = 400;
    pos.reset();
    EXPECT_EQ(pos.zoom, ZOOM_DEFAULT);
}

TEST_F(PositionTest, ResetFromArbitraryState) {
    pos.pan = -4.0;
    pos.tilt = 2.5;
    pos.zoom = 350;
    pos.reset();

    EXPECT_DOUBLE_EQ(pos.pan, 0.0);
    EXPECT_DOUBLE_EQ(pos.tilt, 0.0);
    EXPECT_EQ(pos.zoom, ZOOM_DEFAULT);
}

} // anonymous namespace
} // namespace bcc950
