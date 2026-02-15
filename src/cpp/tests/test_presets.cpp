#include <gtest/gtest.h>

#include <algorithm>
#include <cstdio>
#include <string>
#include <unistd.h>

#include "bcc950/constants.hpp"
#include "bcc950/presets.hpp"

namespace bcc950 {
namespace {

/// Fixture that provides a unique temporary file for each test.
class PresetsTest : public ::testing::Test {
protected:
    std::string tmp_path;

    void SetUp() override {
        tmp_path = "/tmp/bcc950_test_presets_"
                   + std::to_string(getpid()) + "_"
                   + std::to_string(reinterpret_cast<uintptr_t>(this))
                   + ".json";
    }

    void TearDown() override {
        std::remove(tmp_path.c_str());
    }
};

// ---- SaveAndRecall ----

TEST_F(PresetsTest, SaveAndRecallSinglePreset) {
    PresetManager pm(tmp_path);

    PositionTracker pos;
    pos.pan  = 2.5;
    pos.tilt = -1.0;
    pos.zoom = 350;

    pm.save_preset("home", pos);

    auto result = pm.recall_preset("home");
    ASSERT_TRUE(result.has_value());
    EXPECT_DOUBLE_EQ(result->pan, 2.5);
    EXPECT_DOUBLE_EQ(result->tilt, -1.0);
    EXPECT_EQ(result->zoom, 350);
}

TEST_F(PresetsTest, RecallNonexistentReturnsNullopt) {
    PresetManager pm(tmp_path);
    auto result = pm.recall_preset("does_not_exist");
    EXPECT_FALSE(result.has_value());
}

TEST_F(PresetsTest, SaveOverwritesExistingPreset) {
    PresetManager pm(tmp_path);

    PositionTracker pos1;
    pos1.pan = 1.0;
    pos1.tilt = 1.0;
    pos1.zoom = 200;
    pm.save_preset("spot", pos1);

    PositionTracker pos2;
    pos2.pan = -2.0;
    pos2.tilt = -2.0;
    pos2.zoom = 400;
    pm.save_preset("spot", pos2);

    auto result = pm.recall_preset("spot");
    ASSERT_TRUE(result.has_value());
    EXPECT_DOUBLE_EQ(result->pan, -2.0);
    EXPECT_DOUBLE_EQ(result->tilt, -2.0);
    EXPECT_EQ(result->zoom, 400);

    // Still only one preset
    EXPECT_EQ(pm.list_presets().size(), 1u);
}

// ---- DeletePreset ----

TEST_F(PresetsTest, DeletePresetRemovesIt) {
    PresetManager pm(tmp_path);

    PositionTracker pos;
    pos.pan = 1.0;
    pm.save_preset("temp", pos);

    EXPECT_TRUE(pm.delete_preset("temp"));
    EXPECT_FALSE(pm.recall_preset("temp").has_value());
    EXPECT_TRUE(pm.list_presets().empty());
}

TEST_F(PresetsTest, DeleteNonexistentReturnsFalse) {
    PresetManager pm(tmp_path);
    EXPECT_FALSE(pm.delete_preset("nonexistent"));
}

TEST_F(PresetsTest, DeleteDoesNotAffectOtherPresets) {
    PresetManager pm(tmp_path);

    PositionTracker pos;
    pos.pan = 1.0;
    pm.save_preset("keep", pos);

    pos.pan = 2.0;
    pm.save_preset("remove", pos);

    EXPECT_TRUE(pm.delete_preset("remove"));
    EXPECT_EQ(pm.list_presets().size(), 1u);

    auto kept = pm.recall_preset("keep");
    ASSERT_TRUE(kept.has_value());
    EXPECT_DOUBLE_EQ(kept->pan, 1.0);
}

// ---- ListPresets ----

TEST_F(PresetsTest, ListPresetsEmptyByDefault) {
    PresetManager pm(tmp_path);
    EXPECT_TRUE(pm.list_presets().empty());
}

TEST_F(PresetsTest, ListPresetsReturnsAllNames) {
    PresetManager pm(tmp_path);

    PositionTracker pos;
    pm.save_preset("alpha", pos);
    pm.save_preset("beta", pos);
    pm.save_preset("gamma", pos);

    auto names = pm.list_presets();
    EXPECT_EQ(names.size(), 3u);

    // Verify all names are present (order may vary)
    std::sort(names.begin(), names.end());
    EXPECT_EQ(names[0], "alpha");
    EXPECT_EQ(names[1], "beta");
    EXPECT_EQ(names[2], "gamma");
}

TEST_F(PresetsTest, ListPresetsAfterDelete) {
    PresetManager pm(tmp_path);

    PositionTracker pos;
    pm.save_preset("one", pos);
    pm.save_preset("two", pos);
    pm.save_preset("three", pos);

    pm.delete_preset("two");

    auto names = pm.list_presets();
    EXPECT_EQ(names.size(), 2u);

    std::sort(names.begin(), names.end());
    EXPECT_EQ(names[0], "one");
    EXPECT_EQ(names[1], "three");
}

// ---- PersistenceAcrossInstances ----

TEST_F(PresetsTest, PersistenceAcrossInstances) {
    // Save presets with one instance
    {
        PresetManager pm1(tmp_path);

        PositionTracker p1;
        p1.pan  = 3.0;
        p1.tilt = -1.5;
        p1.zoom = 250;
        pm1.save_preset("desk", p1);

        PositionTracker p2;
        p2.pan  = -2.0;
        p2.tilt = 1.0;
        p2.zoom = 400;
        pm1.save_preset("window", p2);
    }
    // pm1 is destroyed here; data should have been persisted to disk

    // Load presets with a new instance
    {
        PresetManager pm2(tmp_path);

        auto names = pm2.list_presets();
        EXPECT_EQ(names.size(), 2u);

        auto desk = pm2.recall_preset("desk");
        ASSERT_TRUE(desk.has_value());
        EXPECT_DOUBLE_EQ(desk->pan, 3.0);
        EXPECT_DOUBLE_EQ(desk->tilt, -1.5);
        EXPECT_EQ(desk->zoom, 250);

        auto window = pm2.recall_preset("window");
        ASSERT_TRUE(window.has_value());
        EXPECT_DOUBLE_EQ(window->pan, -2.0);
        EXPECT_DOUBLE_EQ(window->tilt, 1.0);
        EXPECT_EQ(window->zoom, 400);
    }
}

TEST_F(PresetsTest, PersistenceDeleteSurvivesReload) {
    // Save a preset, then delete it, then reload
    {
        PresetManager pm1(tmp_path);
        PositionTracker pos;
        pos.pan = 1.0;
        pm1.save_preset("ephemeral", pos);
        pm1.save_preset("permanent", pos);
        pm1.delete_preset("ephemeral");
    }
    {
        PresetManager pm2(tmp_path);
        EXPECT_FALSE(pm2.recall_preset("ephemeral").has_value());
        EXPECT_TRUE(pm2.recall_preset("permanent").has_value());
        EXPECT_EQ(pm2.list_presets().size(), 1u);
    }
}

TEST_F(PresetsTest, PersistenceMultipleRoundTrips) {
    PositionTracker pos;

    // Round 1: save
    {
        PresetManager pm(tmp_path);
        pos.pan = 1.0;
        pos.tilt = 0.5;
        pos.zoom = 200;
        pm.save_preset("spot_a", pos);
    }

    // Round 2: add another, verify first still there
    {
        PresetManager pm(tmp_path);
        ASSERT_TRUE(pm.recall_preset("spot_a").has_value());

        pos.pan = -1.0;
        pos.tilt = -0.5;
        pos.zoom = 300;
        pm.save_preset("spot_b", pos);
    }

    // Round 3: verify both
    {
        PresetManager pm(tmp_path);
        EXPECT_EQ(pm.list_presets().size(), 2u);

        auto a = pm.recall_preset("spot_a");
        ASSERT_TRUE(a.has_value());
        EXPECT_DOUBLE_EQ(a->pan, 1.0);

        auto b = pm.recall_preset("spot_b");
        ASSERT_TRUE(b.has_value());
        EXPECT_DOUBLE_EQ(b->pan, -1.0);
    }
}

} // anonymous namespace
} // namespace bcc950
