//
// Created by Michael Brown on 04/02/2023.
//

#ifndef YAFLC1_FIBER_H
#define YAFLC1_FIBER_H


struct fiber;
typedef struct fiber fiber_t;


void fiber_init(void(*)(void*), void*);

fiber_t* fiber_create(void(*)(void*), void*);
void fiber_schedule(fiber_t*);
fiber_t* fiber_self() __attribute__ ((const));
void fiber_yield();

void fiber_parallel(void* param, void(**funcs)(void*), size_t count);

// void fiber_enter(fiber_t*);
// void fiber_free(fiber_t*);

#endif //YAFLC1_FIBER_H
