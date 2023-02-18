
#include <stdio.h>
#include <unistd.h>
#include "object.h"
#include "heap.h"
#include "fiber.h"
#include "blitz.h"


extern int32_t synth_main(struct object* self);

static void first_func(void* nothing) {
    int32_t result = synth_main(&global_unit);
    exit(result);
}

int main() {
    // sigset_t mask;
    // sigfillset(&mask);
    // assert(pthread_sigmask(SIG_BLOCK, &mask, NULL) == 0 && "failed to block signals");

    fiber_init(first_func, NULL);
    sleep(1000000); // Signal handling and some other stuff can happen in main thread

    return 0;
}


