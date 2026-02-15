#include "bcc950/config.hpp"

#include <cstdlib>
#include <fstream>
#include <sstream>

namespace bcc950 {

namespace {

std::string get_home_dir() {
    const char* home = std::getenv("HOME");
    if (home) {
        return std::string(home);
    }
    return ".";
}

std::string trim(const std::string& s) {
    auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    auto end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

} // anonymous namespace

Config::Config(const std::string& config_path)
    : path_(config_path.empty()
            ? get_home_dir() + "/" + DEFAULT_CONFIG_FILENAME
            : config_path) {
    set_defaults();
}

void Config::set_defaults() {
    data_["DEVICE"]    = DEFAULT_DEVICE;
    data_["PAN_SPEED"] = std::to_string(DEFAULT_PAN_SPEED);
    data_["TILT_SPEED"] = std::to_string(DEFAULT_TILT_SPEED);
    data_["ZOOM_STEP"] = std::to_string(DEFAULT_ZOOM_STEP);
}

void Config::load() {
    std::ifstream file(path_);
    if (!file.is_open()) {
        return; // Missing file is silently ignored
    }

    std::string line;
    while (std::getline(file, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') {
            continue;
        }
        auto eq_pos = line.find('=');
        if (eq_pos == std::string::npos) {
            continue;
        }
        std::string key   = trim(line.substr(0, eq_pos));
        std::string value = trim(line.substr(eq_pos + 1));

        // Only update keys we know about
        if (data_.count(key)) {
            data_[key] = value;
        }
    }
}

void Config::save() const {
    std::ofstream file(path_);
    if (!file.is_open()) {
        return;
    }
    for (const auto& [key, value] : data_) {
        file << key << "=" << value << "\n";
    }
}

std::string Config::get(const std::string& key,
                         const std::string& default_val) const {
    auto it = data_.find(key);
    if (it != data_.end()) {
        return it->second;
    }
    return default_val;
}

void Config::set(const std::string& key, const std::string& value) {
    data_[key] = value;
}

std::string Config::device() const {
    return get("DEVICE", DEFAULT_DEVICE);
}

void Config::set_device(const std::string& value) {
    data_["DEVICE"] = value;
}

int Config::pan_speed() const {
    try {
        return std::stoi(get("PAN_SPEED", std::to_string(DEFAULT_PAN_SPEED)));
    } catch (...) {
        return DEFAULT_PAN_SPEED;
    }
}

void Config::set_pan_speed(int value) {
    data_["PAN_SPEED"] = std::to_string(value);
}

int Config::tilt_speed() const {
    try {
        return std::stoi(get("TILT_SPEED", std::to_string(DEFAULT_TILT_SPEED)));
    } catch (...) {
        return DEFAULT_TILT_SPEED;
    }
}

void Config::set_tilt_speed(int value) {
    data_["TILT_SPEED"] = std::to_string(value);
}

int Config::zoom_step() const {
    try {
        return std::stoi(get("ZOOM_STEP", std::to_string(DEFAULT_ZOOM_STEP)));
    } catch (...) {
        return DEFAULT_ZOOM_STEP;
    }
}

void Config::set_zoom_step(int value) {
    data_["ZOOM_STEP"] = std::to_string(value);
}

} // namespace bcc950
