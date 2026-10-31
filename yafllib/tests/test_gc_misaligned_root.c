// Deterministic, single-stepped test: an object whose only reference is a
// pointer stored at a MISALIGNED stack address survives full cycles.
//
// An optimising C compiler may keep a pointer at an address that is not a
// multiple of the word size. clang's SROA gives a slice of an aggregate its
// own stack slot aligned only as far as the slice's start offset allows, and
// a slice that starts in padding and carries a pointer field puts the pointer
// at 4 mod 8 (seen in the self-compile: a 20-byte `[20 x i8], align 4` slice
// of a result struct, holding a list's head at offset 4). The conservative
// scan must find such a pointer: no other word on the stack holds it.
//
//   1. hide(): allocate T and write its address, byte by byte, to offset 4 of
//      a word-aligned stack buffer in the caller's frame. The aligned words
//      around it hold only halves of the address.
//   2. Two full cycles run the root scan.
//   3. T, read back from the buffer, must still be the object it was.
//
// Run with YAFL_THREADS=1 and YAFL_GC_POISON=1.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1 };

enum { MARK = 0x5a, OFFSET = 4 };

struct target { object_t parent; int64_t id; char pad[48]; };
static vtable_t target_vt = {
    .object_size = sizeof(struct target), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "misaligned_target", .implements_array = VTABLE_IMPLEMENTS(0),
};

static fun_t _exit_cont;

static void fail(const char* what, long got) {
    fprintf(stderr, "test_gc_misaligned_root: FAIL %s (got %ld)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    for (int guard = 0; gc_debug_stage() == ST_IDLE; ++guard) {
        if (guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    for (int guard = 0; gc_debug_stage() != ST_IDLE; ++guard) {
        if (guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        gc_debug_step();
    }
}

// Each step runs in a frame of its own, so no aligned copy of T's address
// lingers in a live frame or a callee-saved register; scrub() overwrites what
// those frames left below the stack pointer.
static void __attribute__((noinline)) hide(volatile unsigned char* buf) {
    object_t* t = object_create(&target_vt);
    ((struct target*)t)->id = 42;
    memset(((struct target*)t)->pad, MARK, sizeof ((struct target*)t)->pad);
    uintptr_t a = (uintptr_t)t;
    for (size_t i = 0; i < sizeof a; ++i)
        buf[OFFSET + i] = (unsigned char)(a >> (8 * i));
}

static object_t* __attribute__((noinline)) fetch(volatile unsigned char* buf) {
    uintptr_t a = 0;
    for (size_t i = 0; i < sizeof a; ++i)
        a |= (uintptr_t)buf[OFFSET + i] << (8 * i);
    return (object_t*)a;
}

static void __attribute__((noinline)) scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : ARCH_CALLEE_SAVED_CLOBBERS);
}

static void check(const char* when, object_t* t) {
    if (gc_debug_object_state(t) != 1) fail(when, gc_debug_object_state(t));
    struct target* c = (struct target*)object_resolve(t);
    if (vtable_untag(c->parent.vtable) != &target_vt) fail("the object's vtable changed", 0);
    if (c->id != 42) fail("the object's id changed", (long)c->id);
    for (size_t i = 0; i < sizeof c->pad; ++i)
        if ((unsigned char)c->pad[i] != MARK) fail("the object was overwritten", (long)i);
}

// The buffer lives in this frame, above every collection the steps below run.
static void __attribute__((noinline)) scenario(void) {
    _Alignas(8) volatile unsigned char buf[24];
    for (size_t i = 0; i < sizeof buf; ++i) buf[i] = 0x11;
    hide(buf);
    scrub();
    run_one_cycle();
    run_one_cycle();
    check("lost to a full cycle", fetch(buf));
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != ST_IDLE) gc_debug_step();

    scenario();
    printf("test_gc_misaligned_root: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // Set before any allocation.
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    thread_start(_entrypoint);
    return 0;
}
