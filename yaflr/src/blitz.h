//
// Created by Michael Brown on 10/02/2023.
//

#ifndef YAFLC1_BLITZ_H
#define YAFLC1_BLITZ_H

#include <stdnoreturn.h>
#include <stdio.h>


#define likely(x)       __builtin_expect((x),1)
#define unlikely(x)     __builtin_expect((x),0)
#define indexof(type, field)     (offsetof(type, field) / sizeof(((type*)NULL)->field))

void log_error(char const* format, ...) __attribute__ ((format (printf, 1, 2)));
noreturn void log_error_and_exit(char const* format, ...) __attribute__ ((format (printf, 1, 2)));

#define ERROR(...)  log_error_and_exit(__VA_ARGS__)

#ifndef NDEBUG
#define DEBUG(...)  log_error(__VA_ARGS__)
#else
#define DEBUG(...)
#endif

#define ZZ  DEBUG("%s: %d\n", __FILE__, __LINE__);

#endif //YAFLC1_BLITZ_H
