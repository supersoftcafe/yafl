//
// Created by mbrown on 25/03/24.
//

#include <stdlib.h>
#include "platform.h"




__attribute__((noinline, naked))
void fiber_swap_context(void ***source_sp_ptr, void ***target_sp_ptr) {
    __asm__(
            "\n"
            "    pushq %rdi\n"  // Don't need to save this, but do so for parity with the later load of RDI
            "    pushq %rbx\n"
            "    pushq %rbp\n"
            "    pushq %r12\n"
            "    pushq %r13\n"
            "    pushq %r14\n"
            "    pushq %r15\n"
            "\n"
            "    movq %rsp, (%rdi)\n"  // Save old stack pointer
            "loop:\n"
            "    movq (%rsi), %rsp\n"  // Load new stack pointer
            "    testq %rsp, %rsp\n"   // Not zero we hope
            "    je loop\n"              // Oh it's zero, try again until the other thread has finished exiting
            "    movq $0, (%rsi)\n"     // Reset pointer as flag for thread safety
            "\n"
            "    popq %r15\n"
            "    popq %r14\n"
            "    popq %r13\n"
            "    popq %r12\n"
            "    popq %rbp\n"
            "    popq %rbx\n"
            "    popq %rdi\n"   // As we exit and RET is executed, this becomes the first arg to a new function.
            "\n"
            "    ret\n"
            );
}


static void fiber_donothing(void) {
    // Its only purpose is to call 'ret' and pop one more item off of the stack
}

void fiber_init_stack(void ***target_sp_ptr, void(*exit_func)(void), void(*func)(void*), void* param) {
    void** target = (*target_sp_ptr) -= 11;
    target[10] = NULL;
    target[9] = exit_func; // When entry function exits, it'll automatically branch to the exit function. Neat!
    target[8] = fiber_donothing;    // Filler. It pops the next item, that's all.
    target[7] = func;
    target[6] = param;
    target[5] = NULL;
    target[4] = NULL;
    target[3] = NULL;
    target[2] = NULL;
    target[1] = NULL;
    target[0] = NULL;
}
