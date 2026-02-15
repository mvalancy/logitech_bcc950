#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <memory>

#include "bcc950/v4l2_device.hpp"
#include "bcc950/controller.hpp"
#include "bcc950/position.hpp"
#include "bcc950/constants.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_bcc950_native, m) {
    m.doc() = "BCC950 native C++ bindings";

    // V4L2Device
    py::class_<bcc950::V4L2Device>(m, "V4L2Device")
        .def(py::init<>())
        .def("open", &bcc950::V4L2Device::open)
        .def("close", &bcc950::V4L2Device::close)
        .def("is_open", &bcc950::V4L2Device::is_open)
        .def("set_control", &bcc950::V4L2Device::set_control)
        .def("get_control", &bcc950::V4L2Device::get_control);

    // PositionTracker
    py::class_<bcc950::PositionTracker>(m, "PositionTracker")
        .def(py::init<>())
        .def_readwrite("pan", &bcc950::PositionTracker::pan)
        .def_readwrite("tilt", &bcc950::PositionTracker::tilt)
        .def_readwrite("zoom", &bcc950::PositionTracker::zoom)
        .def("reset", &bcc950::PositionTracker::reset)
        .def("distance_to", &bcc950::PositionTracker::distance_to);

    // Controller - factory function since it takes unique_ptr
    m.def("create_controller", [](const std::string& device) {
        auto dev = std::make_unique<bcc950::V4L2Device>();
        dev->open(device);
        return bcc950::Controller(std::move(dev));
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
