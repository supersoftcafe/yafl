// yafllib/exepath.c — where this program's executable lives (see exepath.h).
#include "yafl.h"
#include "exepath.h"

#include <limits.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

#if defined(__APPLE__)
#include <mach-o/dyld.h>
#endif

// `candidate` is a file a shell would start: a regular file someone may run.
static bool _is_runnable(const char* candidate) {
    struct stat st;
    return stat(candidate, &st) == 0 && S_ISREG(st.st_mode) && access(candidate, X_OK) == 0;
}

// realpath into `out`, false if the path is gone or the answer does not fit.
// realpath writes up to PATH_MAX bytes, so it goes through a buffer of that
// size and the caller's `n` is checked afterwards.
static bool _resolve(const char* path, char* out, size_t n) {
    char real[PATH_MAX];
    if (realpath(path, real) == NULL) return false;
    size_t len = strlen(real);
    if (len >= n) return false;
    memcpy(out, real, len + 1);
    return true;
}

bool yafl_exe_path_from_argv0(const char* argv0, char* out, size_t n) {
    if (argv0 == NULL || *argv0 == 0) return false;

    // A name with a directory in it is the path itself, as for a shell.
    if (strchr(argv0, '/') != NULL)
        return _is_runnable(argv0) && _resolve(argv0, out, n);

    // A bare name: the first PATH directory holding it. An empty entry is the
    // working directory.
    const char* path = getenv("PATH");
    if (path == NULL) return false;
    size_t name_len = strlen(argv0);
    for (const char* dir = path; ; ) {
        const char* end = strchr(dir, ':');
        size_t dir_len = end ? (size_t)(end - dir) : strlen(dir);
        char candidate[PATH_MAX];
        if (dir_len + 1 + name_len < sizeof candidate) {
            if (dir_len == 0) {
                memcpy(candidate, argv0, name_len + 1);
            } else {
                memcpy(candidate, dir, dir_len);
                candidate[dir_len] = '/';
                memcpy(candidate + dir_len + 1, argv0, name_len + 1);
            }
            if (_is_runnable(candidate)) return _resolve(candidate, out, n);
        }
        if (end == NULL) return false;
        dir = end + 1;
    }
}

// What the OS says, if it says anything: false where it has no such call, or
// the call fails (/proc not mounted, a deleted executable).
static bool _from_os(char* out, size_t n) {
#if defined(__linux__)
    return _resolve("/proc/self/exe", out, n);
#elif defined(__APPLE__)
    char raw[PATH_MAX];
    uint32_t size = sizeof raw;
    return _NSGetExecutablePath(raw, &size) == 0 && _resolve(raw, out, n);
#else
    (void)out; (void)n;
    return false;
#endif
}

// The answer cannot change while the process runs, and asking costs a
// readlink and a realpath, so it is kept once found. Two threads that ask at
// the same moment both work it out and write the same bytes, which does no
// harm; the flag is atomic only so a thread that sees it set also sees the path.
static char        _exe_path[PATH_MAX];
static atomic_bool _exe_found;

const char* yafl_exe_path(void) {
    if (atomic_load_explicit(&_exe_found, memory_order_acquire)) return _exe_path;
    if (!_from_os(_exe_path, sizeof _exe_path)
        && !(_yafl_argc > 0 && yafl_exe_path_from_argv0(_yafl_argv[0], _exe_path, sizeof _exe_path)))
        return NULL;
    atomic_store_explicit(&_exe_found, true, memory_order_release);
    return _exe_path;
}

// System::exePath — `String|None`, None when neither the OS nor argv[0] and
// PATH can say. Same representation as sys_getenv (object.c): None is word 0.
EXPORT str_t sys_exe_path(object_t* self) {
    (void)self;
    const char* path = yafl_exe_path();
    return path == NULL ? str_word(NULL) : str_from_cstr(path);
}
