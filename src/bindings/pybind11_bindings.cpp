#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <memory>
#include <sstream>
#include <string>
#include <unordered_map>

#include <dirent.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <linux/videodev2.h>

#include "bcc950/v4l2_device.hpp"
#include "bcc950/controller.hpp"
#include "bcc950/position.hpp"
#include "bcc950/constants.hpp"

namespace py = pybind11;

// Map Python control names (matching v4l2-ctl naming) to V4L2 CID values.
static const std::unordered_map<std::string, uint32_t> CONTROL_MAP = {
    {"pan_speed",      V4L2_CID_PAN_SPEED},
    {"tilt_speed",     V4L2_CID_TILT_SPEED},
    {"zoom_absolute",  V4L2_CID_ZOOM_ABSOLUTE},
    {"pan_absolute",   V4L2_CID_PAN_ABSOLUTE},
    {"tilt_absolute",  V4L2_CID_TILT_ABSOLUTE},
    {"zoom_relative",  V4L2_CID_ZOOM_RELATIVE},
    {"pan_relative",   V4L2_CID_PAN_RELATIVE},
    {"tilt_relative",  V4L2_CID_TILT_RELATIVE},
    {"brightness",     V4L2_CID_BRIGHTNESS},
    {"contrast",       V4L2_CID_CONTRAST},
    {"saturation",     V4L2_CID_SATURATION},
    {"sharpness",      V4L2_CID_SHARPNESS},
    {"focus_auto",     V4L2_CID_FOCUS_AUTO},
    {"focus_absolute", V4L2_CID_FOCUS_ABSOLUTE},
};

static uint32_t resolve_control(const std::string& name) {
    auto it = CONTROL_MAP.find(name);
    if (it != CONTROL_MAP.end()) {
        return it->second;
    }
    throw py::value_error("Unknown control name: '" + name +
                          "'. Use a V4L2 control name like 'pan_speed', "
                          "'tilt_speed', 'zoom_absolute'.");
}

// Enumerate V4L2 controls on an open device fd.
static std::string enumerate_controls(bcc950::V4L2Device& dev) {
    if (!dev.is_open()) {
        throw bcc950::V4L2Error("Device not open");
    }
    int fd = dev.fd();
    std::ostringstream out;
    struct v4l2_queryctrl qctrl{};
    qctrl.id = V4L2_CTRL_FLAG_NEXT_CTRL;
    while (::ioctl(fd, VIDIOC_QUERYCTRL, &qctrl) == 0) {
        if (!(qctrl.flags & V4L2_CTRL_FLAG_DISABLED)) {
            out << reinterpret_cast<const char*>(qctrl.name)
                << " 0x" << std::hex << qctrl.id << std::dec
                << " (";
            switch (qctrl.type) {
                case V4L2_CTRL_TYPE_INTEGER: out << "int"; break;
                case V4L2_CTRL_TYPE_BOOLEAN: out << "bool"; break;
                case V4L2_CTRL_TYPE_MENU:    out << "menu"; break;
                default:                     out << "type=" << qctrl.type; break;
            }
            out << "): min=" << qctrl.minimum
                << " max=" << qctrl.maximum
                << " step=" << qctrl.step
                << " default=" << qctrl.default_value;
            // Read current value
            struct v4l2_control ctrl{};
            ctrl.id = qctrl.id;
            if (::ioctl(fd, VIDIOC_G_CTRL, &ctrl) == 0) {
                out << " value=" << ctrl.value;
            }
            out << "\n";
        }
        qctrl.id |= V4L2_CTRL_FLAG_NEXT_CTRL;
    }
    return out.str();
}

// Scan /dev/video* for V4L2 devices, return formatted string.
static std::string scan_devices() {
    std::ostringstream out;
    DIR* dir = ::opendir("/dev");
    if (!dir) return "Cannot open /dev\n";

    struct dirent* entry;
    while ((entry = ::readdir(dir)) != nullptr) {
        std::string name(entry->d_name);
        if (name.rfind("video", 0) != 0) continue;
        std::string path = "/dev/" + name;
        int fd = ::open(path.c_str(), O_RDWR | O_NONBLOCK);
        if (fd < 0) continue;
        struct v4l2_capability cap{};
        if (::ioctl(fd, VIDIOC_QUERYCAP, &cap) == 0) {
            out << path << " : "
                << reinterpret_cast<const char*>(cap.card)
                << " (" << reinterpret_cast<const char*>(cap.driver) << ")\n";
        }
        ::close(fd);
    }
    ::closedir(dir);
    return out.str();
}

PYBIND11_MODULE(_bcc950_native, m) {
    m.doc() = "BCC950 native C++ bindings";

    // V4L2Device
    py::class_<bcc950::V4L2Device>(m, "V4L2Device")
        .def(py::init<>())
        .def(py::init<const std::string&>(), py::arg("device"))
        .def("open", &bcc950::V4L2Device::open)
        .def("close", &bcc950::V4L2Device::close)
        .def("is_open", &bcc950::V4L2Device::is_open)
        // Numeric overloads (direct V4L2 CID)
        .def("set_control",
             static_cast<void (bcc950::V4L2Device::*)(uint32_t, int32_t)>(
                 &bcc950::V4L2Device::set_control),
             py::arg("control_id"), py::arg("value"))
        // String overloads (look up in CONTROL_MAP)
        .def("set_control",
             [](bcc950::V4L2Device& self, const std::string& name, int32_t value) {
                 self.set_control(resolve_control(name), value);
             },
             py::arg("control"), py::arg("value"))
        .def("get_control",
             static_cast<int32_t (bcc950::V4L2Device::*)(uint32_t)>(
                 &bcc950::V4L2Device::get_control),
             py::arg("control_id"))
        .def("get_control",
             [](bcc950::V4L2Device& self, const std::string& name) -> int32_t {
                 return self.get_control(resolve_control(name));
             },
             py::arg("control"))
        .def("list_controls", &enumerate_controls);

    // Module-level device scanner
    m.def("list_devices", &scan_devices,
          "Scan /dev/video* and return a formatted device list.");

    // PositionTracker
    py::class_<bcc950::PositionTracker>(m, "PositionTracker")
        .def(py::init<>())
        .def_readwrite("pan", &bcc950::PositionTracker::pan)
        .def_readwrite("tilt", &bcc950::PositionTracker::tilt)
        .def_readwrite("zoom", &bcc950::PositionTracker::zoom)
        .def("reset", &bcc950::PositionTracker::reset)
        .def("distance_to", &bcc950::PositionTracker::distance_to);

    // Controller - factory function returning unique_ptr since Controller
    // holds a unique_ptr member (non-copyable, non-movable in pybind11)
    m.def("create_controller", [](const std::string& device) {
        auto dev = std::make_unique<bcc950::V4L2Device>();
        dev->open(device);
        return std::make_unique<bcc950::Controller>(std::move(dev));
    }, py::arg("device") = bcc950::DEFAULT_DEVICE);

    py::class_<bcc950::Controller>(m, "Controller")
        .def("pan_left", &bcc950::Controller::pan_left,
             py::arg("duration") = bcc950::DEFAULT_MOVE_DURATION)
        .def("pan_right", &bcc950::Controller::pan_right,
             py::arg("duration") = bcc950::DEFAULT_MOVE_DURATION)
        .def("tilt_up", &bcc950::Controller::tilt_up,
             py::arg("duration") = bcc950::DEFAULT_MOVE_DURATION)
        .def("tilt_down", &bcc950::Controller::tilt_down,
             py::arg("duration") = bcc950::DEFAULT_MOVE_DURATION)
        .def("zoom_in", &bcc950::Controller::zoom_in)
        .def("zoom_out", &bcc950::Controller::zoom_out)
        .def("zoom_to", &bcc950::Controller::zoom_to)
        .def("reset_position", &bcc950::Controller::reset_position)
        .def("stop", &bcc950::Controller::stop);

    // Constants
    m.attr("ZOOM_MIN") = bcc950::ZOOM_MIN;
    m.attr("ZOOM_MAX") = bcc950::ZOOM_MAX;
    m.attr("DEFAULT_DEVICE") = bcc950::DEFAULT_DEVICE;
}
