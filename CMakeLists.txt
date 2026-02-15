cmake_minimum_required(VERSION 3.16)
project(bcc950 VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Option to build pybind11 Python bindings
option(BUILD_PYTHON_BINDINGS "Build Python bindings via pybind11" OFF)

# Build the C++ driver library and CLI
add_subdirectory(src/cpp)

# Optional: pybind11 bindings
if(BUILD_PYTHON_BINDINGS)
    find_package(pybind11 REQUIRED)

    pybind11_add_module(_bcc950_native src/bindings/pybind11_bindings.cpp)
    target_link_libraries(_bcc950_native PRIVATE bcc950_lib)
    target_include_directories(_bcc950_native PRIVATE src/cpp/include)

    # Install the module where Python can find it
    install(TARGETS _bcc950_native
        LIBRARY DESTINATION ${CMAKE_INSTALL_PREFIX}/lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages
    )
endif()
