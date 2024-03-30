//
// Created by mbrown on 25/03/24.
//

#include "platform.h"

__asm__(
".global fiber_swap_context\n"
"fiber_swap_context:\n"
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
"    popq %rdi\n"   // As we exit_flag and RET is executed, this becomes the first arg to a new function.
"\n"
"    ret\n"
);


/*
// IMPORTANT COMPILER NOTICE
// Must compile with -fomit-frame-pointer, or the stack offsets are off by 1
__attribute__((noinline))
void fiber_swap_context(__attribute__((unused)) void*** source_sp_ptr, __attribute__((unused)) void*** target_sp_ptr) {
    // RIP was pushed onto the stack by the caller and so doesn't need to be saved/restored
    __asm__(
            "pushq %%rdi\n"  // Don't need to save this, but do so for parity with the later load of RDI
            "pushq %%rbx\n"
            "pushq %%rbp\n"
            "pushq %%r12\n"
            "pushq %%r13\n"
            "pushq %%r14\n"
            "pushq %%r15\n"

            "movq %%rsp, (%%rdi)\n"  // Save old stack pointer
            "loop:\n"
            "movq (%%rsi), %%rsp\n"  // Load new stack pointer
            "testq %%rsp, %%rsp\n"   // Not zero we hope
            "je loop\n"              // Oh it's zero, try again until the other thread has finished exiting
            "movq $0, (%%rsi)\n"     // Reset pointer as flag for thread safety

            "popq %%r15\n"
            "popq %%r14\n"
            "popq %%r13\n"
            "popq %%r12\n"
            "popq %%rbp\n"
            "popq %%rbx\n"
            "popq %%rdi\n"   // As we exit_flag and RET is executed, this becomes the first arg to a new function.
            :
            : // Without these, we get a SEGV
            :
            );
}

 */

