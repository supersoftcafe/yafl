cmake_minimum_required(VERSION 3.19)
project(yafl_meta LANGUAGES C)

# Top-level driver.  Build everything with:
#   cmake -B build -DCMAKE_INSTALL_PREFIX=/usr/local
#   cmake --build build -j
#   cmake --install build
#
# This builds:
#   - yafllib       → libyafl.so / libyafl.a / yafl.h
#   - compiler      → yafl  (PyInstaller, bundles stdlib)
#   - examples      → yafl_json_pretty, ...  (one binary per example)
# and installs them under ${CMAKE_INSTALL_PREFIX}.

add_subdirectory(yafllib)
add_subdirectory(compiler)
add_subdirectory(examples)
