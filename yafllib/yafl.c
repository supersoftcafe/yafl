
#include "common.h"
#include "yafl.h"


EXPORT void log_error(char const* format, ...) {
    va_list argp;
    va_start(argp, format);
    vfprintf(stderr, format, argp);
    va_end(argp);
}

EXPORT noreturn void log_error_and_exit(char const* format, ...) {
    log_error("errno %d\n", errno);

    va_list argp;
    va_start(argp, format);
    vfprintf(stderr, format, argp);
    va_end(argp);

    abort();
    __builtin_unreachable();
}
