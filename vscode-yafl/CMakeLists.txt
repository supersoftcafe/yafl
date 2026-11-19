cmake_minimum_required(VERSION 3.19)
project(vscode-yafl NONE)

# Standalone project — NOT wired into the top-level YAFL build. It packages the
# VS Code language extension living in this directory.
#
#   cmake -S vscode-yafl -B vscode-yafl/build
#   cmake --build vscode-yafl/build --target install-extension
#
# install-extension installs the language client's npm dependencies (npm ci,
# from package-lock.json), then symlinks this source directory into the VS Code
# extensions directory, so edits are live after "Developer: Reload Window" with
# no rebuild.

# The version is package.json's, the one place it is written.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/package.json" _package)
string(JSON EXT_VERSION GET "${_package}" version)
set(EXT_ID "yafl-${EXT_VERSION}")

find_program(NPM_EXECUTABLE npm)

set(YAFL_VSCODE_EXTENSIONS_DIR "$ENV{HOME}/.vscode/extensions"
    CACHE PATH "Parent directory VS Code loads extensions from")

set(_link "${YAFL_VSCODE_EXTENSIONS_DIR}/${EXT_ID}")

# The language client needs its npm dependencies; without npm the extension
# still installs, with highlighting but no language server.
if(NPM_EXECUTABLE)
    set(_npm_ci COMMAND "${NPM_EXECUTABLE}" ci --no-fund --no-audit
                --prefix "${CMAKE_CURRENT_SOURCE_DIR}")
else()
    set(_npm_ci COMMAND "${CMAKE_COMMAND}" -E echo
                "npm not found: installing without the language client's dependencies")
endif()

add_custom_target(install-extension
    ${_npm_ci}
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
if(NPX_EXECUTABLE AND NPM_EXECUTABLE)
    add_custom_target(package-vsix
        COMMAND "${NPM_EXECUTABLE}" ci --no-fund --no-audit
        COMMAND "${NPX_EXECUTABLE}" --yes @vscode/vsce package
                -o "${CMAKE_CURRENT_BINARY_DIR}/vscode-yafl-${EXT_VERSION}.vsix"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        VERBATIM)
else()
    add_custom_target(package-vsix
        COMMAND "${CMAKE_COMMAND}" -E echo
                "npm and npx not found: install Node.js to build a .vsix"
        VERBATIM)
endif()
