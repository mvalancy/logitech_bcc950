#include "bcc950/presets.hpp"

#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace bcc950 {

namespace {

/// Get the home directory path.
std::string get_home_dir() {
    const char* home = std::getenv("HOME");
    if (home) {
        return std::string(home);
    }
    return ".";
}

/// Trim leading and trailing whitespace.
std::string trim(const std::string& s) {
    auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    auto end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

/// Remove surrounding quotes from a string value.
std::string unquote(const std::string& s) {
    if (s.size() >= 2 && s.front() == '"' && s.back() == '"') {
        return s.substr(1, s.size() - 2);
    }
    return s;
}

} // anonymous namespace

PresetManager::PresetManager(const std::string& presets_path)
    : path_(presets_path.empty()
            ? get_home_dir() + "/" + DEFAULT_PRESETS_FILENAME
            : presets_path) {
    load();
}

void PresetManager::load() {
    std::ifstream file(path_);
    if (!file.is_open()) {
        return;
    }

    std::ostringstream ss;
    ss << file.rdbuf();
    from_json(ss.str());
}

void PresetManager::save() const {
    std::ofstream file(path_);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot write presets file: " + path_);
    }
    file << to_json();
}

void PresetManager::save_preset(const std::string& name,
                                 const PositionTracker& position) {
    presets_[name] = position;
    save();
}

std::optional<PositionTracker> PresetManager::recall_preset(
    const std::string& name) const {
    auto it = presets_.find(name);
    if (it == presets_.end()) {
        return std::nullopt;
    }
    return it->second;
}

bool PresetManager::delete_preset(const std::string& name) {
    auto it = presets_.find(name);
    if (it == presets_.end()) {
        return false;
    }
    presets_.erase(it);
    save();
    return true;
}

std::vector<std::string> PresetManager::list_presets() const {
    std::vector<std::string> names;
    names.reserve(presets_.size());
    for (const auto& [name, _] : presets_) {
        names.push_back(name);
    }
    return names;
}

const std::map<std::string, PositionTracker>& PresetManager::get_all() const {
    return presets_;
}

std::string PresetManager::to_json() const {
    std::ostringstream out;
    out << "{\n";
    bool first = true;
    for (const auto& [name, pos] : presets_) {
        if (!first) {
            out << ",\n";
        }
        first = false;
        out << "  \"" << name << "\": {\n";
        out << "    \"pan\": " << pos.pan << ",\n";
        out << "    \"tilt\": " << pos.tilt << ",\n";
        out << "    \"zoom\": " << pos.zoom << "\n";
        out << "  }";
    }
    out << "\n}\n";
    return out.str();
}

void PresetManager::from_json(const std::string& json_str) {
    // Minimal hand-written JSON parser for our known format:
    // {
    //   "name": {
    //     "pan": 1.5,
    //     "tilt": -0.3,
    //     "zoom": 200
    //   },
    //   ...
    // }
    //
    // This parser handles the exact structure we emit. It is not a
    // general-purpose JSON parser.

    presets_.clear();

    enum class State {
        ROOT,          // expecting '{' to start the root object
        PRESET_KEY,    // expecting a quoted key or '}'
        COLON_1,       // expecting ':' after preset key
        INNER_OPEN,    // expecting '{' to open inner object
        FIELD_KEY,     // expecting a field key or '}'
        COLON_2,       // expecting ':' after field key
        FIELD_VALUE,   // expecting a numeric value
        FIELD_SEP,     // expecting ',' or '}' after value
        PRESET_SEP,    // expecting ',' or '}' after inner object
    };

    State state = State::ROOT;
    std::string current_preset;
    std::string current_field;
    double pan_val = 0.0;
    double tilt_val = 0.0;
    int zoom_val = ZOOM_DEFAULT;

    size_t i = 0;
    auto skip_ws = [&]() {
        while (i < json_str.size() &&
               (json_str[i] == ' ' || json_str[i] == '\t' ||
                json_str[i] == '\n' || json_str[i] == '\r')) {
            ++i;
        }
    };

    auto read_quoted_string = [&]() -> std::string {
        if (i >= json_str.size() || json_str[i] != '"') {
            throw std::runtime_error("Expected '\"' in JSON");
        }
        ++i; // skip opening quote
        std::string result;
        while (i < json_str.size() && json_str[i] != '"') {
            if (json_str[i] == '\\' && i + 1 < json_str.size()) {
                ++i;
            }
            result += json_str[i];
            ++i;
        }
        if (i < json_str.size()) {
            ++i; // skip closing quote
        }
        return result;
    };

    auto read_number = [&]() -> double {
        size_t start = i;
        while (i < json_str.size() &&
               (json_str[i] == '-' || json_str[i] == '+' ||
                json_str[i] == '.' || json_str[i] == 'e' ||
                json_str[i] == 'E' ||
                (json_str[i] >= '0' && json_str[i] <= '9'))) {
            ++i;
        }
        return std::stod(json_str.substr(start, i - start));
    };

    while (i < json_str.size()) {
        skip_ws();
        if (i >= json_str.size()) break;

        switch (state) {
        case State::ROOT:
            if (json_str[i] == '{') {
                ++i;
                state = State::PRESET_KEY;
            } else {
                throw std::runtime_error("Expected '{' at root");
            }
            break;

        case State::PRESET_KEY:
            if (json_str[i] == '}') {
                ++i;
                return; // done
            }
            current_preset = read_quoted_string();
            state = State::COLON_1;
            break;

        case State::COLON_1:
            if (json_str[i] == ':') {
                ++i;
                state = State::INNER_OPEN;
            }
            break;

        case State::INNER_OPEN:
            if (json_str[i] == '{') {
                ++i;
                pan_val = 0.0;
                tilt_val = 0.0;
                zoom_val = ZOOM_DEFAULT;
                state = State::FIELD_KEY;
            }
            break;

        case State::FIELD_KEY:
            if (json_str[i] == '}') {
                ++i;
                // Store the preset
                PositionTracker pt;
                pt.pan  = pan_val;
                pt.tilt = tilt_val;
                pt.zoom = zoom_val;
                presets_[current_preset] = pt;
                state = State::PRESET_SEP;
            } else {
                current_field = read_quoted_string();
                state = State::COLON_2;
            }
            break;

        case State::COLON_2:
            if (json_str[i] == ':') {
                ++i;
                state = State::FIELD_VALUE;
            }
            break;

        case State::FIELD_VALUE: {
            double val = read_number();
            if (current_field == "pan") {
                pan_val = val;
            } else if (current_field == "tilt") {
                tilt_val = val;
            } else if (current_field == "zoom") {
                zoom_val = static_cast<int>(val);
            }
            state = State::FIELD_SEP;
            break;
        }

        case State::FIELD_SEP:
            if (json_str[i] == ',') {
                ++i;
                state = State::FIELD_KEY;
            } else if (json_str[i] == '}') {
                // will be handled in FIELD_KEY
                state = State::FIELD_KEY;
            }
            break;

        case State::PRESET_SEP:
            if (json_str[i] == ',') {
                ++i;
                state = State::PRESET_KEY;
            } else if (json_str[i] == '}') {
                ++i;
                return; // done
            }
            break;
        }
    }
}

} // namespace bcc950
