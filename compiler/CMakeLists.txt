
cmake_minimum_required(VERSION 3.19)
project(yafl)

# Main Python script
set(MAIN_SCRIPT ${CMAKE_SOURCE_DIR}/main.py)
message(STATUS "PyInstaller script path: ${MAIN_SCRIPT}")

# Output executable name directly 'yafl'
set(EXECUTABLE_NAME yafl)

add_custom_target(build_executable ALL
    COMMAND ${CMAKE_COMMAND} -E env
        pyinstaller --add-data "stdlib:stdlib" --onefile --name ${EXECUTABLE_NAME} ${MAIN_SCRIPT}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Building standalone executable using PyInstaller"
)

install(PROGRAMS ${CMAKE_SOURCE_DIR}/dist/${EXECUTABLE_NAME}
        DESTINATION bin)

set_directory_properties(PROPERTIES ADDITIONAL_MAKE_CLEAN_FILES
    "build;dist;__pycache__;${EXECUTABLE_NAME}.spec")

