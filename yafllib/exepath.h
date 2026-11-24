// yafllib/exepath.h — where this program's executable lives, runtime-internal
// side (System::exePath is the YAFL face, via sys_exe_path in yafl.h).
//
// A program that locates its install from its own path (the compiler finds
// `${prefix}/lib/yafl` beside `${prefix}/bin/<exe>`) cannot use argv[0]: a
// program started by bare name from PATH is given the name and no directory.
// The path is asked of the OS where it will say, and rebuilt from argv[0] and
// PATH, the way a shell found the program, where it will not. Either way the
// result is absolute with every symlink resolved, so a link to the program
// from another `bin/` leads to the real install.
#pragma once

#include "yafl.h"

// The running executable's real path, kept for the life of the process. The
// OS first (/proc/self/exe on Linux, _NSGetExecutablePath on macOS), then
// yafl_exe_path_from_argv0 on the process's own argv[0]. NULL if neither says.
HIDDEN const char* yafl_exe_path(void);

// The real path of the program a shell would start for `argv0`: itself if it
// carries a `/` (relative to the working directory), else the first
// executable regular file of that name in a PATH directory, the empty entry
// meaning the working directory. False if there is none, or it doesn't fit.
HIDDEN bool yafl_exe_path_from_argv0(const char* argv0, char* out, size_t n);
