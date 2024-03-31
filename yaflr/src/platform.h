//
// Created by mbrown on 25/03/24.
//

#ifndef YAFLR_PLATFORM_H
#define YAFLR_PLATFORM_H

// Target should point at the word just after the stack. Init will adjust it as required.
void fiber_init_stack(void ***target_sp_ptr, void(*exit_func)(void), void(*func)(void*), void* param);

// Save the current caller context into the source and use the target context before returning.
void fiber_swap_context(void ***source_sp_ptr, void ***target_sp_ptr);

#endif //YAFLR_PLATFORM_H
