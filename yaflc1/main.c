
#include <stdio.h>
#include <unistd.h>
#include "fiber.h"
#include "blitz.h"

struct object;
struct vtable {
    struct {
        size_t lookup_mask;
        void(*delete)(struct object*);
    } head;
    size_t* methods[0];
};
struct object {
    struct vtable* vtable;
    size_t refcnt;
};





void crummy_func_1(void* message) {
    fprintf(stderr, "1: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}
void crummy_func_2(void* message) {
    fprintf(stderr, "2: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}
void crummy_func_3(void* message) {
    fprintf(stderr, "3: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}
void crummy_func_4(void* message) {
    fprintf(stderr, "4: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}
void crummy_func_5(void* message) {
    fprintf(stderr, "5: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}
void crummy_func_6(void* message) {
    fprintf(stderr, "6: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}
void crummy_func_7(void* message) {
    fprintf(stderr, "7: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}
void crummy_func_8(void* message) {
    fprintf(stderr, "8: Message is: %s and fiber is %lx\n", (char*)message, (uintptr_t)fiber_self());
}

void first_func(void* none) {
    void(*funcs[8])(void*) = {
            crummy_func_1,
            crummy_func_2,
            crummy_func_3,
            crummy_func_4,
            crummy_func_5,
            crummy_func_6,
            crummy_func_7,
            crummy_func_8
    };

    fiber_parallel("Hello world!", funcs, 8);
}


int main() {
    // sigset_t mask;
    // sigfillset(&mask);
    // assert(pthread_sigmask(SIG_BLOCK, &mask, NULL) == 0 && "failed to block signals");

    fiber_init(first_func, NULL);
    sleep(1000);

    return 0;
}


