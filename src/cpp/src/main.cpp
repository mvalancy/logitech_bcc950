#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <iomanip>

#include "bcc950/controller.hpp"
#include "bcc950/v4l2_device.hpp"

namespace {

struct Args {
    std::string device;
    double duration = 0.1;

    bool pan_left    = false;
    bool pan_right   = false;
    bool tilt_up     = false;
    bool tilt_down   = false;
    bool zoom_in_    = false;
    bool zoom_out_   = false;

    int  zoom_value  = -1;  // -1 means not set

    bool has_move    = false;
    int  move_pan    = 0;
    int  move_tilt   = 0;
    double move_dur  = 0.1;

    std::string save_preset;
    std::string recall_preset;
    std::string delete_preset;
    bool list_presets = false;

    bool show_position = false;
    bool reset         = false;
    bool setup         = false;
    bool info          = false;
    bool help          = false;
};

void print_usage(const char* prog) {
    std::cout
        << "Usage: " << prog << " [OPTIONS]\n"
        << "\n"
        << "Control Logitech BCC950 Camera\n"
        << "\n"
        << "Options:\n"
        << "  -d, --device DEVICE      Specify camera device\n"
        << "      --duration SECS      Movement duration in seconds (default: 0.1)\n"
        << "\n"
        << "Movement:\n"
        << "      --pan-left           Pan camera left\n"
        << "      --pan-right          Pan camera right\n"
        << "      --tilt-up            Tilt camera up\n"
        << "      --tilt-down          Tilt camera down\n"
        << "      --zoom-in            Zoom camera in\n"
        << "      --zoom-out           Zoom camera out\n"
        << "      --zoom-value VALUE   Set zoom to absolute value (100-500)\n"
        << "      --move PAN TILT DUR  Combined move: PAN(-1/0/1) TILT(-1/0/1) DURATION\n"
        << "\n"
        << "Presets:\n"
        << "      --save-preset NAME   Save current position as preset\n"
        << "      --recall-preset NAME Recall a named preset\n"
        << "      --delete-preset NAME Delete a named preset\n"
        << "      --list-presets       List all presets\n"
        << "\n"
        << "Info / Setup:\n"
        << "      --position           Show estimated position\n"
        << "      --reset              Reset camera to default position\n"
        << "      --setup              Detect camera and test connection\n"
        << "      --info               Show camera information\n"
        << "  -h, --help               Show this help message\n";
}

bool parse_args(int argc, char* argv[], Args& args) {
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];

        if (arg == "-h" || arg == "--help") {
            args.help = true;
            return true;
        } else if (arg == "-d" || arg == "--device") {
            if (++i >= argc) {
                std::cerr << "Error: --device requires an argument\n";
                return false;
            }
            args.device = argv[i];
        } else if (arg == "--duration") {
            if (++i >= argc) {
                std::cerr << "Error: --duration requires an argument\n";
                return false;
            }
            args.duration = std::stod(argv[i]);
        } else if (arg == "--pan-left") {
            args.pan_left = true;
        } else if (arg == "--pan-right") {
            args.pan_right = true;
        } else if (arg == "--tilt-up") {
            args.tilt_up = true;
        } else if (arg == "--tilt-down") {
            args.tilt_down = true;
        } else if (arg == "--zoom-in") {
            args.zoom_in_ = true;
        } else if (arg == "--zoom-out") {
            args.zoom_out_ = true;
        } else if (arg == "--zoom-value") {
            if (++i >= argc) {
                std::cerr << "Error: --zoom-value requires an argument\n";
                return false;
            }
            args.zoom_value = std::stoi(argv[i]);
        } else if (arg == "--move") {
            if (i + 3 >= argc) {
                std::cerr << "Error: --move requires 3 arguments: PAN TILT DURATION\n";
                return false;
            }
            args.has_move  = true;
            args.move_pan  = std::stoi(argv[++i]);
            args.move_tilt = std::stoi(argv[++i]);
            args.move_dur  = std::stod(argv[++i]);
        } else if (arg == "--save-preset") {
            if (++i >= argc) {
                std::cerr << "Error: --save-preset requires an argument\n";
                return false;
            }
            args.save_preset = argv[i];
        } else if (arg == "--recall-preset") {
            if (++i >= argc) {
                std::cerr << "Error: --recall-preset requires an argument\n";
                return false;
            }
            args.recall_preset = argv[i];
        } else if (arg == "--delete-preset") {
            if (++i >= argc) {
                std::cerr << "Error: --delete-preset requires an argument\n";
                return false;
            }
            args.delete_preset = argv[i];
        } else if (arg == "--list-presets") {
            args.list_presets = true;
        } else if (arg == "--position") {
            args.show_position = true;
        } else if (arg == "--reset") {
            args.reset = true;
        } else if (arg == "--setup") {
            args.setup = true;
        } else if (arg == "--info") {
            args.info = true;
        } else {
            std::cerr << "Unknown option: " << arg << "\n";
            return false;
        }
    }
    return true;
}

} // anonymous namespace

int main(int argc, char* argv[]) {
    Args args;
    if (!parse_args(argc, argv, args)) {
        print_usage(argv[0]);
        return 1;
    }

    if (args.help) {
        print_usage(argv[0]);
        return 0;
    }

    // Determine if any action was requested
    bool has_action =
        args.pan_left || args.pan_right ||
        args.tilt_up || args.tilt_down ||
        args.zoom_in_ || args.zoom_out_ ||
        args.zoom_value >= 0 || args.has_move ||
        !args.save_preset.empty() ||
        !args.recall_preset.empty() ||
        !args.delete_preset.empty() ||
        args.list_presets ||
        args.show_position || args.reset ||
        args.setup || args.info;

    if (!has_action) {
        print_usage(argv[0]);
        return 0;
    }

    try {
        auto v4l2_dev = std::make_unique<bcc950::V4L2Device>();
        bcc950::Controller ctrl(std::move(v4l2_dev), args.device);

        if (args.setup) {
            bool ptz = ctrl.has_ptz_support();
            std::cout << "Device: " << ctrl.device_path() << "\n";
            std::cout << "PTZ support: " << (ptz ? "true" : "false") << "\n";
        } else if (args.pan_left) {
            ctrl.pan_left(args.duration);
        } else if (args.pan_right) {
            ctrl.pan_right(args.duration);
        } else if (args.tilt_up) {
            ctrl.tilt_up(args.duration);
        } else if (args.tilt_down) {
            ctrl.tilt_down(args.duration);
        } else if (args.zoom_in_) {
            ctrl.zoom_in();
        } else if (args.zoom_out_) {
            ctrl.zoom_out();
        } else if (args.zoom_value >= 0) {
            ctrl.zoom_to(args.zoom_value);
            std::cout << "Zoom set to " << args.zoom_value << "\n";
        } else if (args.has_move) {
            ctrl.move(args.move_pan, args.move_tilt, args.move_dur);
            std::cout << "Moved pan=" << args.move_pan
                      << " tilt=" << args.move_tilt
                      << " for " << args.move_dur << "s\n";
        } else if (!args.save_preset.empty()) {
            ctrl.save_preset(args.save_preset);
            std::cout << "Saved preset: " << args.save_preset << "\n";
        } else if (!args.recall_preset.empty()) {
            if (ctrl.recall_preset(args.recall_preset)) {
                std::cout << "Recalled preset: " << args.recall_preset << "\n";
            } else {
                std::cerr << "Preset not found: " << args.recall_preset << "\n";
                return 1;
            }
        } else if (!args.delete_preset.empty()) {
            if (ctrl.delete_preset(args.delete_preset)) {
                std::cout << "Deleted preset: " << args.delete_preset << "\n";
            } else {
                std::cerr << "Preset not found: " << args.delete_preset << "\n";
                return 1;
            }
        } else if (args.list_presets) {
            auto presets = ctrl.list_presets();
            if (presets.empty()) {
                std::cout << "No presets saved.\n";
            } else {
                for (const auto& name : presets) {
                    std::cout << "  " << name << "\n";
                }
            }
        } else if (args.show_position) {
            const auto& pos = ctrl.position();
            std::cout << std::fixed << std::setprecision(2);
            std::cout << "Pan: " << pos.pan
                      << "  Tilt: " << pos.tilt
                      << "  Zoom: " << pos.zoom << "\n";
        } else if (args.reset) {
            ctrl.reset_position();
            std::cout << "Camera reset to default position.\n";
        } else if (args.info) {
            std::cout << "Device: " << ctrl.device_path() << "\n";
            std::cout << "PTZ support: "
                      << (ctrl.has_ptz_support() ? "true" : "false") << "\n";
        }
    } catch (const bcc950::V4L2Error& e) {
        std::cerr << "V4L2 error: " << e.what() << "\n";
        return 1;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }

    return 0;
}
