#include "yafl.h"
#line 3 "yafl.c"

EXPORT decl_func
void log_error(char const* format, ...) {
    va_list argp;
    va_start(argp, format);
    vfprintf(stderr, format, argp);
    va_end(argp);
}

EXPORT decl_func
noreturn void log_error_and_exit(char const* format, ...) {
    log_error("errno %d\n", errno);

    va_list argp;
    va_start(argp, format);
    vfprintf(stderr, format, argp);
    va_end(argp);

    abort();
    __builtin_unreachable();
}

int main(int argc, char** argv) {
    thread_start();
}
