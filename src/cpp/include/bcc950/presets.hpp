#pragma once

#include <map>
#include <string>
#include <vector>
#include <optional>

#include "position.hpp"

namespace bcc950 {

/// JSON-based named preset storage for camera positions.
///
/// Uses hand-written JSON serialization (no external dependencies).
class PresetManager {
public:
    /// Construct with optional custom file path.
    explicit PresetManager(const std::string& presets_path = "");

    /// Load presets from JSON file.
    void load();

    /// Persist presets to JSON file.
    void save() const;

    /// Save a named preset from current position.
    void save_preset(const std::string& name, const PositionTracker& position);

    /// Recall a named preset. Returns nullopt if not found.
    std::optional<PositionTracker> recall_preset(const std::string& name) const;

    /// Delete a named preset. Returns true if it existed.
    bool delete_preset(const std::string& name);

    /// Return list of preset names.
    std::vector<std::string> list_presets() const;

    /// Return all presets as a map.
    const std::map<std::string, PositionTracker>& get_all() const;

private:
    std::string path_;
    std::map<std::string, PositionTracker> presets_;

    /// Serialize presets to a JSON string.
    std::string to_json() const;

    /// Parse a JSON string and populate presets.
    void from_json(const std::string& json_str);
};

} // namespace bcc950
