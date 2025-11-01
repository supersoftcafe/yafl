
#include "common.h"
#include "yafl.h"


EXPORT enum log_level LOG_LEVEL = DEBUG;

static char LOG_LEVEL_NAMES[7][8] = {
    "ULTRA", "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"
};

static void LOG2(enum log_level level, const char* format, va_list argp) {
    if (level >= LOG_LEVEL) {
        fprintf(stderr, "  [%s] - ", LOG_LEVEL_NAMES[level]);
        vfprintf(stderr, format, argp);
        fprintf(stderr, "\n");
    }
}

EXPORT void LOG(enum log_level level, const char* format, ...) {
    if (level >= LOG_LEVEL) {
        va_list argp;
        va_start(argp, format);
        LOG2(level, format, argp);
        va_end(argp);
    }
}

EXPORT void log_error(char const* format, ...) {
    va_list argp;
    va_start(argp, format);
    LOG2(ERROR, format, argp);
    va_end(argp);
}

EXPORT noreturn void log_error_and_exit(char const* format, ...) {
    log_error("errno %d\n", errno);

    va_list argp;
    va_start(argp, format);
    log_error(format, argp);
    va_end(argp);

    abort();
    __builtin_unreachable();
}
