//
// Created by Michael Brown on 11/02/2023.
//

#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <errno.h>
#include "blitz.h"


void log_error(char const* format, ...) {
    va_list argp;
    va_start(argp, format);
    vfprintf(stderr, format, argp);
    va_end(argp);
}

noreturn void log_error_and_exit(char const* format, ...) {
    log_error("errno %d\n", errno);

    va_list argp;
    va_start(argp, format);
    vfprintf(stderr, format, argp);
    va_end(argp);

    exit(1);
}
