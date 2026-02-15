# Unit tests for libbcc950
#
# GoogleTest is fetched by the parent CMakeLists.txt via FetchContent.
# If this file is used standalone, the FetchContent block below ensures
# GoogleTest is still available.

include(FetchContent)

FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()

add_executable(bcc950_tests
    test_position.cpp
    test_motion.cpp
    test_controller.cpp
    test_presets.cpp
    test_config.cpp
)

target_include_directories(bcc950_tests
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}           # for mock_v4l2_device.hpp
)

target_link_libraries(bcc950_tests
    PRIVATE
        libbcc950
        GTest::gtest_main
        GTest::gmock
)

include(GoogleTest)
gtest_discover_tests(bcc950_tests)
