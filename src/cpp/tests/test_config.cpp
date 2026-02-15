#include <gtest/gtest.h>
#include <fstream>
#include <cstdio>

#include "bcc950/config.hpp"

using namespace bcc950;

class ConfigTest : public ::testing::Test {
protected:
    std::string tmp_path;

    void SetUp() override {
        tmp_path = "/tmp/bcc950_test_config_" + std::to_string(getpid());
    }

    void TearDown() override {
        std::remove(tmp_path.c_str());
    }
};

TEST_F(ConfigTest, Defaults) {
    Config cfg(tmp_path);
    EXPECT_EQ(cfg.device(), DEFAULT_DEVICE);
    EXPECT_EQ(cfg.pan_speed(), DEFAULT_PAN_SPEED);
    EXPECT_EQ(cfg.tilt_speed(), DEFAULT_TILT_SPEED);
    EXPECT_EQ(cfg.zoom_step(), DEFAULT_ZOOM_STEP);
}

TEST_F(ConfigTest, SaveAndLoad) {
    {
        Config cfg(tmp_path);
        cfg.set_device("/dev/video2");
        cfg.set_pan_speed(1);
        cfg.set_zoom_step(25);
        cfg.save();
    }
    {
        Config cfg(tmp_path);
        cfg.load();
        EXPECT_EQ(cfg.device(), "/dev/video2");
        EXPECT_EQ(cfg.zoom_step(), 25);
    }
}

TEST_F(ConfigTest, LoadMissingFile) {
    Config cfg("/tmp/nonexistent_bcc950_file_xyz");
    cfg.load(); // should not throw
    EXPECT_EQ(cfg.device(), DEFAULT_DEVICE);
}

TEST_F(ConfigTest, LoadIgnoresComments) {
    {
        std::ofstream f(tmp_path);
        f << "# This is a comment\n";
        f << "DEVICE=/dev/video5\n";
        f << "  # another comment\n";
        f << "PAN_SPEED=1\n";
    }
    Config cfg(tmp_path);
    cfg.load();
    EXPECT_EQ(cfg.device(), "/dev/video5");
}

TEST_F(ConfigTest, SetAndGet) {
    Config cfg(tmp_path);
    cfg.set("CUSTOM_KEY", "custom_value");
    EXPECT_EQ(cfg.get("CUSTOM_KEY"), "custom_value");
    EXPECT_EQ(cfg.get("MISSING", "fallback"), "fallback");
}
