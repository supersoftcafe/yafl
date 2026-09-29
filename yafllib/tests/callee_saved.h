#pragma once

// Clobber list for an empty asm that forces every callee-saved register to be
// treated as overwritten, so no stale pointer survives in one for the
// conservative stack scan to find. The frame pointer and stack pointer are
// never listed. Unknown targets get the memory clobber alone.
#if defined(__x86_64__)
#define CALLEE_SAVED_CLOBBERS "memory", "rbx", "r12", "r13", "r14", "r15"
#elif defined(__aarch64__)
#define CALLEE_SAVED_CLOBBERS "memory", "x19", "x20", "x21", "x22", "x23", \
    "x24", "x25", "x26", "x27", "x28"
#elif defined(__s390x__)
#define CALLEE_SAVED_CLOBBERS "memory", "r6", "r7", "r8", "r9", "r10", "r12", "r13"
#else
#define CALLEE_SAVED_CLOBBERS "memory"
#endif
