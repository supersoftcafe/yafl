//
// Created by Michael Brown on 04/02/2023.
//

#ifndef YAFLC1_FIBER_H
#define YAFLC1_FIBER_H


#include "object.h"


struct fiber;
typedef struct fiber fiber_t;

/* Create one thread per core.
 * Launch entry fiber.
 */
void fiber_start(void(*)(void*), void*);

/* Create or borrow from free list, a fiber....   If the fiber we have has been used more
 * than N times already, discard it and try again.
 */
// fiber_t* fiber_create(void(*enter)(void*), void*);

/* Take a sleeping fiber and schedule it on this thread.
 * If called from outside a fiber context, schedule it on a round-robin basis.
 */
void fiber_schedule(fiber_t*);

fiber_t* fiber_self() __attribute__ ((const));

/* Go to the back of the queue on this thread.
 */
void fiber_yield();

/* Create a fiber for each function and wait for them all to return.
 */
void fiber_parallel(void* param, void(**funcs)(void*), int count);



/* Wrapper for the object library method that uses the fiber local heap.
 */
object_t* fiber_object_create(vtable_t* vtable);

/* Wrapper for the object library method that uses the fiber local heap.
 */
object_t* fiber_object_create_array(vtable_t* vtable, uint32_t length);

/* Wrapper for the object library method that uses the fiber local heap.
 */
void fiber_object_heap_compact2(shadow_stack_t *shadow_stack);
void fiber_object_heap_compact(int count, object_t **array);


#endif //YAFLC1_FIBER_H
