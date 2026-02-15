cmake_minimum_required(VERSION 3.14)
project(bcc950 VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# --- Library ---

add_library(libbcc950 STATIC
    src/v4l2_device.cpp
    src/position.cpp
    src/motion.cpp
    src/presets.cpp
    src/config.cpp
    src/controller.cpp
)

# Avoid the "liblibbcc950.a" name on Unix; enable PIC for pybind11 linking
set_target_properties(libbcc950 PROPERTIES
    OUTPUT_NAME bcc950
    POSITION_INDEPENDENT_CODE ON
)

target_include_directories(libbcc950
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

find_package(Threads REQUIRED)
target_link_libraries(libbcc950 PUBLIC Threads::Threads)

# --- CLI Executable ---

add_executable(bcc950 src/main.cpp)
target_link_libraries(bcc950 PRIVATE libbcc950)

# --- Tests ---

option(BCC950_BUILD_TESTS "Build BCC950 unit tests" ON)

if(BCC950_BUILD_TESTS)
    include(FetchContent)
    FetchContent_Declare(
        googletest
        GIT_REPOSITORY https://github.com/google/googletest.git
        GIT_TAG        v1.14.0
    )
    # Prevent overriding parent project compiler/linker settings
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)

    enable_testing()
    add_subdirectory(tests)
endif()
