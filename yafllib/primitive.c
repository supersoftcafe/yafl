
#include "common.h"
#include "yafl.h"
#include <stdio.h>


EXPORT void __abort_on_overflow() {
    fputs("Aborting due to integer overflow", stderr);
    abort();
    __builtin_unreachable();
}
