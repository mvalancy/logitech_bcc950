#pragma once

#include <map>
#include <string>

#include "constants.hpp"

namespace bcc950 {

/// Manages BCC950 configuration load/save from ~/.bcc950_config.
///
/// Key=value file format, compatible with the Python version.
class Config {
public:
    /// Construct with optional custom config file path.
    explicit Config(const std::string& config_path = "");

    /// Load config from file. Missing file is silently ignored.
    void load();

    /// Save current config to file.
    void save() const;

    /// Get a config value by key, or a default if missing.
    std::string get(const std::string& key, const std::string& default_val = "") const;

    /// Set a config value.
    void set(const std::string& key, const std::string& value);

    // --- Typed accessors ---

    std::string device() const;
    void set_device(const std::string& value);

    int pan_speed() const;
    void set_pan_speed(int value);

    int tilt_speed() const;
    void set_tilt_speed(int value);

    int zoom_step() const;
    void set_zoom_step(int value);

    /// Return the config file path.
    const std::string& path() const { return path_; }

private:
    std::string path_;
    std::map<std::string, std::string> data_;

    void set_defaults();
};

} // namespace bcc950
