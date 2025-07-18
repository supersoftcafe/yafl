cmake_minimum_required(VERSION 3.15)
project(MyPythonApp)

# Set your main Python script here
set(MAIN_SCRIPT main.py)

# Set output name
set(EXECUTABLE_NAME my_python_app)

# Add a custom target to run PyInstaller
add_custom_target(build_executable ALL
    COMMAND ${CMAKE_COMMAND} -E env
        pyinstaller --onefile --name ${EXECUTABLE_NAME} ${MAIN_SCRIPT}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Building standalone executable using PyInstaller"
)

# Optional: clean up PyInstaller build directories on 'make clean'
set_directory_properties(PROPERTIES ADDITIONAL_MAKE_CLEAN_FILES "build;dist;__pycache__;${EXECUTABLE_NAME}.spec")

