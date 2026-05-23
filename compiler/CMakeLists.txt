
cmake_minimum_required(VERSION 3.19)
project(yafl_compiler)

set(MAIN_SCRIPT ${CMAKE_CURRENT_SOURCE_DIR}/main.py)
set(EXECUTABLE_NAME yafl)
set(YAFL_COMPILER_BIN ${CMAKE_CURRENT_SOURCE_DIR}/dist/${EXECUTABLE_NAME}
    CACHE INTERNAL "Path to the built yafl compiler binary")

add_custom_target(build_executable ALL
    COMMAND ${CMAKE_COMMAND} -E env
        pyinstaller --add-data "stdlib:stdlib" --onefile --name ${EXECUTABLE_NAME} ${MAIN_SCRIPT}
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    BYPRODUCTS ${YAFL_COMPILER_BIN}
    COMMENT "Building standalone executable using PyInstaller"
)

install(PROGRAMS ${YAFL_COMPILER_BIN}
        DESTINATION bin)

set_directory_properties(PROPERTIES ADDITIONAL_MAKE_CLEAN_FILES
    "build;dist;__pycache__;${EXECUTABLE_NAME}.spec")

