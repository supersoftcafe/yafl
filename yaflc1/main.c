
#include <stdio.h>
#include <unistd.h>
#include "object.h"
#include "heap.h"
#include "fiber.h"
#include "blitz.h"


static void first_func(int(*func)()) {
    int32_t result = func();
    exit(result);
}

int runtime_main(int(*func)()) {
    // sigset_t mask;
    // sigfillset(&mask);
    // assert(pthread_sigmask(SIG_BLOCK, &mask, NULL) == 0 && "failed to block signals");

    fiber_init((void(*)(void*))first_func, func);
    sleep(1000000); // Signal handling and some other stuff can happen in main thread

    return 0;
}


