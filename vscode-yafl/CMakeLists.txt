cmake_minimum_required(VERSION 3.19)
project(vscode-yafl NONE)

# Standalone project — NOT wired into the top-level YAFL build. It packages the
# VS Code language extension living in this directory.
#
#   cmake -S vscode-yafl -B vscode-yafl/build
#   cmake --build vscode-yafl/build --target install-extension
#
# install-extension symlinks this source directory into the VS Code extensions
# directory, so grammar edits are live after "Developer: Reload Window" with no
# rebuild.

set(EXT_ID "yafl-0.1.0")

set(YAFL_VSCODE_EXTENSIONS_DIR "$ENV{HOME}/.vscode/extensions"
    CACHE PATH "Parent directory VS Code loads extensions from")

set(_link "${YAFL_VSCODE_EXTENSIONS_DIR}/${EXT_ID}")

add_custom_target(install-extension
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${YAFL_VSCODE_EXTENSIONS_DIR}"
    COMMAND "${CMAKE_COMMAND}" -E rm -rf "${_link}"
    COMMAND "${CMAKE_COMMAND}" -E create_symlink
            "${CMAKE_CURRENT_SOURCE_DIR}" "${_link}"
    COMMAND "${CMAKE_COMMAND}" -E echo
            "Linked ${_link} -> ${CMAKE_CURRENT_SOURCE_DIR}"
    COMMAND "${CMAKE_COMMAND}" -E echo
            "Run 'Developer: Reload Window' in VS Code to load it."
    VERBATIM)

add_custom_target(uninstall-extension
    COMMAND "${CMAKE_COMMAND}" -E rm -rf "${_link}"
    COMMAND "${CMAKE_COMMAND}" -E echo "Removed ${_link}"
    VERBATIM)

find_program(NPX_EXECUTABLE npx)
if(NPX_EXECUTABLE)
    add_custom_target(package-vsix
        COMMAND "${NPX_EXECUTABLE}" --yes @vscode/vsce package
                --no-dependencies
                -o "${CMAKE_CURRENT_BINARY_DIR}/vscode-yafl-0.1.0.vsix"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        VERBATIM)
else()
    add_custom_target(package-vsix
        COMMAND "${CMAKE_COMMAND}" -E echo
                "npx not found: install Node.js to build a .vsix"
        VERBATIM)
endif()
