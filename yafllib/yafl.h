#pragma once

// The runtime is built in strict ISO C mode (-std=c11), not gnu11. POSIX and
// OS facilities it relies on — clock_gettime, mmap/madvise, pthreads —
// are requested through the standard feature-test macros rather than the gnu11
// default's implicit superset. These must be set before any system header, so
// yafl.h must be the FIRST include in every translation unit (it is, including
// the compiler's generated C).
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif


#include <stdatomic.h>
#include <stdnoreturn.h>
#include <stdalign.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stddef.h>
#include <assert.h>

#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <errno.h>
#include <math.h>




#ifndef __STDC_NO_THREADS__
#include <threads.h>
#endif

#ifndef __STDC_NO_ATOMICS__
#include <stdatomic.h>
#endif

#define STACK_GROWS_DOWN    1
enum { GC_PAGE_SIZE = 16384 };


#if defined(_WIN32) || defined(__CYGWIN__)
#  define EXTERN __declspec(dllimport)
#  define EXPORT __declspec(dllexport)
#  define HIDDEN
#elif __GNUC__ >= 4
#  define EXTERN extern
#  define EXPORT __attribute__((visibility("default")))
#  define HIDDEN __attribute__((visibility("hidden")))
#endif


#if defined(_MSC_VER)
#  define INLINE static __forceinline
#  define NOINLINE      __declspec(noinline)
#  define NORETURN      __declspec(noreturn)
#  define COLD          __declspec(code_seg(".text$cold"))
#elif defined(__GNUC__)
#  define INLINE static __attribute__((always_inline)) inline
#  define NOINLINE      __attribute__((noinline))
#  define NORETURN      __attribute__((noreturn))
#  define COLD          __attribute__((cold))
#else
#  define INLINE
#  define NOINLINE
#  define NORETURN
#  define COLD
#endif


#if defined(__GNUC__)
  #define LIKELY(x)   __builtin_expect(!!(x), 1)
  #define UNLIKELY(x) __builtin_expect(!!(x), 0)
#else
  #define LIKELY(x)   (x)
  #define UNLIKELY(x) (x)
#endif


#define indexof(type, field) (offsetof(type, field) / sizeof(((type*)NULL)->field))
#define total_bits(type) (sizeof(type) * 8)


#if defined(__GNUC__)
#  define index_of_lowest_bit(value)             \
        _Generic( (value),                       \
            unsigned long long: __builtin_ctzll, \
            unsigned long: __builtin_ctzl,       \
            unsigned int: __builtin_ctz          \
        )(value)
#else
#  error "No implementation for index_of_lowest_bit"
#endif


#if UINTPTR_MAX == 0xFFFFFFFF
#  define WORD_SIZE 32
#elif UINTPTR_MAX == 0xFFFFFFFFFFFFFFFF
#  define WORD_SIZE 64
#else
#  error "Unknown pointer size or unsupported platform."
#endif


// The allocator's slot granule: every heap object occupies a multiple of
// this, on 32- and 64-bit alike. object.c's slot_t asserts it.
#define GC_ALLOC_GRANULE 32
#define ALIGNED     __attribute__((aligned(GC_ALLOC_GRANULE)))


// Spin-wait hint for a waiter on a busy lock: lets an SMT sibling (often the
// holder) run. Targets without an instruction for it get a compiler barrier.
static inline void cpu_relax(void) {
#if defined(__x86_64__) || defined(__i386__)
    __builtin_ia32_pause();
#elif defined(__aarch64__) || defined(__arm__)
    __asm__ volatile("yield" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}


#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#  define IS_LITTLE_ENDIAN 1
#elif defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#  define IS_LITTLE_ENDIAN 0
#elif defined(_WIN32)
#  define IS_LITTLE_ENDIAN 1
#else
#  error "Cannot determine endianness"
#endif


#if defined(__aarch64__) && defined(__APPLE__)
#  define CACHE_LINE_SIZE 128
#elif defined(__x86_64__) || defined(_M_X64)
#  define CACHE_LINE_SIZE 64
#else
#  define CACHE_LINE_SIZE 64
#endif

enum log_level {
    ULTRA, TRACE, DEBUG, INFO, WARN, ERROR, FATAL
};

EXTERN enum log_level LOG_LEVEL;
EXTERN void _LOG(enum log_level level, char const* format, ...);
#define LOG(level, ...)\
    do { if ((level) >= LOG_LEVEL) _LOG((level), __VA_ARGS__); } while (false)

EXTERN void log_error(char const* format, ...);
EXTERN noreturn void log_error_and_exit(char const* format, ...);
#define ERROR(...)  log_error_and_exit(__VA_ARGS__)
#ifndef NDEBUG
#  define DEBUG(...)  log_error(__VA_ARGS__)
#else
#  define DEBUG(...)
#endif


// Bitmask of which pointer-sized slots of an object/array-element are GC
// pointers, indexed by slot = byteoffset/sizeof(void*). One word covers an
// object's first 64 slots; wider objects extend the map through the vtable's
// `object_pointer_masks` window array (window w covers slots 64w..64w+63).
// Array-element masks and field-relative write-barrier masks stay single-word:
// `maskof` keeps the raw shift so exceeding it is a loud compile error there.
typedef uint64_t ptr_mask_t;

#define maskof(type, field)\
        ((ptr_mask_t)(((ptr_mask_t)1)<<(offsetof(struct {type o;}, o field)/sizeof(void*))))

// The slot index of `field`, and its mask bit within window `w` (0 when the
// field lives in another window). The modulo keeps the shift < 64 for ANY
// offset, so these are always well-defined constant expressions.
#define ptr_word_of(type, field)\
        (offsetof(struct {type o;}, o field)/sizeof(void*))
#define maskof_w(type, field, w)\
        ((ptr_mask_t)((ptr_word_of(type, field) / 64 == (size_t)(w))\
            ? (((ptr_mask_t)1) << (ptr_word_of(type, field) % 64)) : (ptr_mask_t)0))

// `o` FIRST: the GC word leads, so a function value lays out like a String
// value (str_t: GC-visible word 0, payload word 1) and a union of the two
// copies as plain words. Every initialiser is designated, so the order is
// free everywhere else.
typedef struct {
    void* o;
    void* f;
} fun_t;


typedef struct {
    intptr_t i;
    void*    f;
} vtable_entry_t;

typedef struct vtable {
    uint16_t object_size;
    uint16_t array_el_size;
    uint32_t functions_mask;     // Size-1, must be n^2-1, is the bit mask used to lookup function pointers
    uint64_t object_pointer_locations;
    uint64_t array_el_pointer_locations;
    uint16_t array_len_offset;   // Offset of uint32_t array length field
    uint16_t is_mutable:1;
    // Globally unique variant/union-member id (the compiler's discriminator
    // registry). Enum variants carry their own vtables, so the discriminant
    // lives here — once per TYPE — instead of a tag byte in every object.
    // 0 for types that never appear in a match dispatch.
    int32_t discriminator;
    // Extended pointer map for objects whose fields pass slot 63: masks[w]
    // covers slots 64w..64w+63 and masks[0] duplicates
    // object_pointer_locations. NULL for the common (<= 64 slot) case —
    // every walker treats NULL as a single-window map.
    const ptr_mask_t* object_pointer_masks;
    uint16_t object_pointer_mask_words;
    // Offset of a uint32_t CAPACITY field for arrays built in place (0 = none).
    // Capacity is in the same units as the array_len_offset field; the heap
    // owns only `length` elements, so any copy (compaction) trims the object
    // and resets capacity to length on the copy.
    uint16_t array_cap_offset;
    const char *name;
    struct vtable** implements_array; // Array of all classes that this class extends
#ifdef NDEBUG
    vtable_entry_t lookup[0];
#else
    vtable_entry_t lookup[16];   // The array size is nominal to help with debugging
#endif
} vtable_t;

#define VTABLE_DECLARE_STRUCT(NAME, LOOKUP_COUNT)\
        struct NAME {\
            uint16_t object_size;\
            uint16_t array_el_size;\
            uint32_t functions_mask;\
            uint64_t object_pointer_locations;\
            uint64_t array_el_pointer_locations;\
            uint16_t array_len_offset;\
            uint16_t is_mutable:1;\
            int32_t discriminator;\
            const ptr_mask_t* object_pointer_masks;\
            uint16_t object_pointer_mask_words;\
            uint16_t array_cap_offset;\
            const char* name;\
            struct vtable** implements_array;\
            vtable_entry_t lookup[LOOKUP_COUNT];\
        }

#define VTABLE_DECLARE(LOOKUP_COUNT)\
        (struct vtable*)&(const VTABLE_DECLARE_STRUCT(, LOOKUP_COUNT))

#define VTABLE_IMPLEMENTS(COUNT, ...) (vtable_t**)&(struct{vtable_t*p[COUNT];vtable_t*t;}){.p = {__VA_ARGS__}, .t = (vtable_t*)0 }

typedef struct {
    vtable_t* vtable;
} object_t;


// This calculation needs to work with positive signed 32 bit numbers
#define rotate_function_id(id)\
        ((id * sizeof(intptr_t) * 2) | (id / (134217728 / sizeof(intptr_t) * 8)))

// The vtable word carries a TAG BIT. Bit 1 is set on every real vtable
// pointer an object holds, and clear on a compaction forwarding pointer —
// which is a plain heap address, and heap objects are slot-aligned, so the
// bit is free. "Is this word a forwarding pointer?" is therefore one AND on
// a word the caller has already loaded.
//
// It used to be the managed-heap RANGE check (`vt - _memory_heap_base <
// _memory_heap_bytes`): correct, tag-free, but it reloads two mutable
// externs on every dispatch, instance test and resolve — and because they
// are mutable externs the C compiler must re-read them after any call it
// cannot see through, which also blocks CSE of repeated resolves of one
// pointer (lowering/pinnable_reads.py emits 3-6 per function).
EXTERN char*  _memory_heap_base;    // set once at heap init (mmap.c)
EXTERN size_t _memory_heap_bytes;

// Bit 0 is the PIN (see object pinning below); bit 1 marks "this word is a
// vtable, not a forwarding address". Both are stripped by vtable_untag.
enum { VTABLE_PIN_BIT = 0x1,
       VTABLE_TAG_BIT = 0x2,
       VTABLE_BITS    = VTABLE_PIN_BIT | VTABLE_TAG_BIT };

INLINE bool vtable_is_forward(vtable_t* vt) {
    return ((uintptr_t)vt & VTABLE_TAG_BIT) == 0;
}

// Applied wherever a vtable is INSTALLED in an object's header: object_new
// and array_create (below and in object.c), compaction's copy, and the
// static instances the code generator emits (there as `(char*)obj_X +
// VTABLE_TAG_BIT`, since `|` on an address is not a C constant expression).
INLINE vtable_t* vtable_tag(vtable_t* vt) {
    return (vtable_t*)((uintptr_t)vt | VTABLE_TAG_BIT);
}

// The same tag for a STATIC initialiser — every object built as a compound
// literal (string and integer literals below, and the code generator's static
// instances) needs it too, or its header reads as a forwarding pointer.
// Pointer arithmetic, not `|`: only an address constant plus an integer is a
// C constant expression, and vtables are aligned so +2 IS |2.
#define VTABLE_TAG_CONST(vt) ((vtable_t*)((char*)(vt) + VTABLE_TAG_BIT))

// The CURRENT copy of `o`, following any relocation. Ordinary immutable
// objects do not need this — every copy of one holds the same bytes forever,
// which is exactly why field reads are plain `->` accesses with no barrier.
//
// A [pinnable] object breaks that: a late write under the pin lands on the
// live copy only, so a pre-relocation pointer reads STALE fields. Two reads
// through such a pointer, either side of a write, disagree about the same
// object — and while cross-thread timing is undefined anyway (seeing NULL
// where another thread has just published is fine), a single thread seeing
// two different values for one field is not something a caller can defend
// against. So reads of [pinnable] fields resolve first; the compiler emits
// this around them (lowering/pinnable_reads.py) and nowhere else.
INLINE object_t* object_resolve(object_t* o) {
    vtable_t* vt = o->vtable;
    while (UNLIKELY(vtable_is_forward(vt))) {
        o  = (object_t*)vt;
        vt = o->vtable;
    }
    return o;
}

// ── object pinning ───────────────────────────────────────────────────────────
// A marker bit in the OBJECT's vtable word: compaction skips a pinned object
// (it stays at its address), letting a runtime primitive hold a raw pointer
// and mutate a not-yet-published field without racing lazy relocation —
// the concurrent-compaction contract ("either copy is fine") only covers
// immutable objects. Real vtables are aligned statics so bit 0 is free, and
// a pinned word still carries the vtable tag, so it is never mistaken for a
// forwarding pointer (the pin bit never appears on one anyway: compaction
// skips pinned objects, and the object stays pinned only while its owner
// holds it).
INLINE vtable_t* vtable_untag(vtable_t* vt) {
    return (vtable_t*)((uintptr_t)vt & ~(uintptr_t)VTABLE_BITS);
}

INLINE bool vtable_is_pinned(vtable_t* vt) {
    return ((uintptr_t)vt & VTABLE_PIN_BIT) != 0;
}

// EARLY pin — an object pinned from birth — is not a call: object_new and
// array_create take `pinned` and install the vtable word with the bit already
// set (free: it rides the store that installs the vtable). That is the
// array-tabulation, array-builder and list-builder-cell case. Only a LATE pin,
// on an object that may already be shared, needs the CAS below.

// LATE pin: take the pin on an object that is already shared and may already
// have aged, moved, or be moving. The bit doubles as a MUTEX — exactly one
// owner at a time, mutator or collector — so a caller that wins it may write
// the object's fields with plain stores, and the compactor that loses it
// simply leaves the object where it is.
//
// Fails (returns false) when someone else holds the pin, or when the object
// has been relocated: a forwarding word means this address is a stale copy
// and the caller must re-resolve and retry on the target, or its write would
// land somewhere nothing will read. object_pin_resolve does that loop.
//
// Acquire on success pairs with the release in object_unpin, so an owner sees
// every field the previous owner wrote.
INLINE bool object_try_pin(object_t* o) {
    vtable_t* vt = (vtable_t*)__atomic_load_n((uintptr_t*)&o->vtable, __ATOMIC_ACQUIRE);
    if (vtable_is_pinned(vt) || vtable_is_forward(vt))
        return false;
    uintptr_t expected = (uintptr_t)vt;
    return __atomic_compare_exchange_n((uintptr_t*)&o->vtable, &expected,
                                       expected | VTABLE_PIN_BIT, false,
                                       __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
}

// Unpin: any time, but only on a pinned object — the one release for every
// pin, early or late. Release order so every initialising store (the whole
// point of the pin) is visible before the object becomes movable/publishable.
// Returns `o` so generated code can emit it as a value (codegen has no void
// call); C callers ignore it.
INLINE object_t* object_unpin(object_t* o) {
    __atomic_store_n((uintptr_t*)&o->vtable,
                     (uintptr_t)o->vtable & ~(uintptr_t)VTABLE_PIN_BIT,
                     __ATOMIC_RELEASE);
    return o;
}

// Take a late pin on the CURRENT copy of `o`, following relocation and
// retrying against whoever else wants it. Returns the object actually pinned,
// which may differ from `o` if the collector moved it. Callers must write
// through the returned pointer, never through their original.
//
// The wait is bounded: the only other holders are a peer writer doing one
// field store, or the compactor doing one memcpy — neither allocates or
// suspends while holding it (see gc_compact_page, which allocates its target
// BEFORE claiming for exactly this reason), so no back-off is needed.
EXTERN object_t* object_pin_resolve(object_t* o);

// Announce that a late pin is about to write `o`. The store may install a
// reference to a YOUNG object, and minor cycles skip old pages, so a page
// that has aged into the old generation must return to the collection
// rotation — otherwise nothing would ever trace the new referent and prune
// would free it while the writer still holds it. The page's flag is set
// UNCONDITIONALLY (young pages included) and only then is `old` read: the
// promotion decision writes `old` before re-reading the flag, so whichever
// way the race falls, one side sees the other (a Dekker handshake — see
// gc_note_late_write and the promotion site in object.c). Cost is paid per
// WRITE, not per object per cycle, which is what makes a write-once
// structure cheap to keep.
EXTERN void gc_note_late_write(object_t* o);

enum {
    PTR_TAG_OBJECT  = 0x0,  // Just an ordinary object pointer.
    PTR_TAG_TASK    = 0x1,  // If lowest bit is set, this is a task pointer. Invisible to GC, so must not be stored.
    PTR_TAG_INTEGER = 0x2,  // Compressed integer in upper 30 or 62 bits.
    PTR_TAG_STRING  = 0x4,  // Comrpessed string in upper 3 or 7 bytes. Upper bits of lowest byte are the length.
    PTR_TAG_MASK    = 0x7
};

#define PTR_IS_OBJECT(ptr)  (((uintptr_t)(ptr)&PTR_TAG_MASK) == 0)
#define PTR_IS_TASK(ptr)    (((uintptr_t)(ptr)&PTR_TAG_TASK) != 0)
#define PTR_IS_INTEGER(ptr) (((uintptr_t)(ptr)&PTR_TAG_INTEGER) != 0)
#define PTR_IS_STRING(ptr)  (((uintptr_t)(ptr)&PTR_TAG_MASK) == PTR_TAG_STRING)

// Follows a call the compiler proved sync (lowering/sync_inference.py): the
// result must not be a task. Checked in unoptimised (debug) builds; an
// optimised build still evaluates the (side-effect-free) condition so the
// result it reads never counts as set-but-unused.
#ifdef __OPTIMIZE__
#  define YAFL_ASSERT_NOT_TASK(is_task) ((void)(is_task))
#else
#  define YAFL_ASSERT_NOT_TASK(is_task)\
        do { if (is_task) ERROR("a call proven sync returned a task"); } while (false)
#endif


EXTERN void gc_configure(void);   // before any worker starts (thread_start)
EXTERN void gc_start();

// ── GC heap geometry + the inline allocation fast path ─────────────────────
// These are THE allocator's definitions (object.c builds on them; its
// static_asserts cross-check the arithmetic). They live in the header so the
// compiler's generated C bump-allocates INLINE with the vtable constant
// visible per call site: object_size and is_mutable fold to literals, the
// branches vanish, and the zero-fill loop is elided by the C compiler's
// dead-store elimination wherever the object's fields are initialised
// immediately afterwards.

typedef uintptr_t mask_bits_t;
enum { GC_MASK_SIZE = sizeof(mask_bits_t) * 8 /* bits */ };
enum { GC_SLOT_SIZE = GC_ALLOC_GRANULE /* bytes */ };

typedef struct {
    mask_bits_t a[GC_PAGE_SIZE / GC_SLOT_SIZE / 8 / sizeof(mask_bits_t)];
} __attribute__((aligned(GC_PAGE_SIZE / GC_SLOT_SIZE / 8))) bitmap_t;

typedef struct slot_t {
    vtable_t *vt;
    struct slot_t *o1, *o2;
    uintptr_t a[(GC_SLOT_SIZE - sizeof(void*)*3) / sizeof(uintptr_t)];
} __attribute__((aligned(GC_SLOT_SIZE))) slot_t;

typedef struct page_head {
    struct {
        struct gc_page *next;
        struct gc_page *prev;
    } list; // Page belongs to a cicular list, somewhere

    struct {
        bitmap_t        seen; // Starting slot of each seen object
        bitmap_t     scanned; // Starting slot of each scanned object
        bitmap_t atomic_seen; // Strictly for the early stage atomic updates
        _Atomic(uint32_t) processed_by_epoch; // Scanned has processed this page..  Reset to false when something changes
        _Atomic(bool) requeue_pending; // a requeue request arrived while an executor
                                       // had this page CLAIMED (popped, on no list);
                                       // the owner consumes it after its final
                                       // re-merge and requeues the page itself
        bool          pinned; // Stack references found, which can't be re-written easily
    } scanner;

    bitmap_t objects; // Starting slot of each known object
    uint32_t     tag; // Safety check
    uint32_t   pages; // Number of pages, including this one, in the complete allocation
    bool     mutable; // Contains mutable objects.
    bool   compacted; // Don't compact again.
    bool         old; // Promoted to the old generation: exempt from minor cycles.
    _Atomic(bool) redirty; // A late pin wrote an object on this page while it
                      // was `old`. Set by the MUTATOR (gc_note_late_write),
                      // consumed at the next cycle's start, which demotes the
                      // page back into the rotation. One cycle of latency is
                      // sound: the referent the write installed was allocated
                      // on a birth-protected page, so the in-flight cycle
                      // cannot free it before the demotion takes effect.
    bool   dirty_old; // Aged page still holding young references: exempt from
                      // pruning, but force-marked as a root every cycle until
                      // its targets promote (then it graduates to `old`).
    uint8_t refs_defer;   // prunes left before re-walking gc_page_refs_are_old
    uint8_t refs_backoff; // last defer length; doubles per failed walk up to
                          // GC_REFS_BACKOFF_CAP, so permanently-blocked pages
                          // stop costing a full object walk every prune.
                          // Reset on instability and on major demotion. Sound
                          // while deferred: the page stays dirty-old, i.e. a
                          // force-marked root.
    uint32_t compacted_cycle; // DIAGNOSTIC (stats builds read it): cycle at
                           // which this page was evacuated. A compacted page
                           // holds only forwarding stubs, so it should die
                           // within a cycle or two — once its referrers are
                           // fixed up, nothing marks the stubs. One that
                           // LINGERS is evidence of a reference that could not
                           // be rewritten (a mutable container's slot, which
                           // fixup deliberately skips to avoid racing the
                           // mutator, or an old-generation referrer awaiting
                           // re-scan), and it is immortal until that reference
                           // dies. Age at death measures exactly that.
    bool          was_old; // Demoted by a major cycle and not yet re-pruned:
                           // deaths found at that prune mean its promotion was
                           // premature (a promotion MISTAKE; see
                           // gc_promote_volume). Sits in padding.
    uint64_t stable_since; // Allocation-clock reading (pages) at the last
                           // prune that found a death on this page — or
                           // UINT64_MAX before the first prune (a page's
                           // first prune is force-stable via birth
                           // protection, so it only STARTS the clock).
                           // Drives volume-based promotion.
    uint32_t local_epoch;  // Thread-local nursery (prototype, YAFL_LOCAL_GC):
                           // the owning thread's nursery epoch while this page
                           // is one of its birth-protected pages, 0 = not
                           // nursery (relocation targets, pre-start pages).
                           // A root scan retires every page by moving the
                           // thread's epoch on. See gc_local_collect.
    bitmap_t local_mark;   // Nursery collection's mark bits (owner-only).
    bitmap_t local_escaped; // ESCAPED objects (any thread may set, atomically):
                           // reachable from somewhere the owner's nursery
                           // collection cannot see, so never freed by it.
                           // Monotone until the owner's next root scan.

} __attribute__((aligned(GC_SLOT_SIZE))) page_head_t;

enum { PAGE_MAGIC_NUMBER = 0x71ea05c3 };
enum { SLOTS_PER_PAGE = (GC_PAGE_SIZE - sizeof(page_head_t)) / sizeof(slot_t) };

typedef struct gc_page {
    page_head_t head;
    slot_t     slots[SLOTS_PER_PAGE];
} __attribute__((aligned(GC_SLOT_SIZE))) gc_page_t;

enum { MAX_OBJECT_SIZE = sizeof(gc_page_t) - offsetof(gc_page_t, slots[0]) };

enum {
    GC_SAFE_POINT_SCAN_ROOTS = 0x001,
    GC_SAFE_POINT_CATCH_UP   = 0x002
};

// The highest set bit at or below `slot`: the object containing that slot.
INLINE long bitmap_prev_set(const bitmap_t* bm, long slot) {
    long wi = slot / GC_MASK_SIZE;
    long bi = slot % GC_MASK_SIZE;
    mask_bits_t w = bm->a[wi];
    if (bi != GC_MASK_SIZE - 1)
        w &= (((mask_bits_t)1 << (bi + 1)) - 1);
    for (;;) {
        if (w) return wi * GC_MASK_SIZE + (GC_MASK_SIZE - 1 - (long)__builtin_clzll(w));
        if (--wi < 0) return -1;
        w = bm->a[wi];
    }
}

INLINE bool bitmap_fetch_set(bitmap_t *bitmap, unsigned bit) {
    mask_bits_t mask = ((mask_bits_t)1) << (bit % GC_MASK_SIZE);
    mask_bits_t *ptr = &bitmap->a[bit / GC_MASK_SIZE];
    mask_bits_t bits = *ptr;
    *ptr = bits | mask;
    return (bits & mask) != 0;
}

INLINE bool atomic_bitmap_fetch_set(bitmap_t *bitmap, unsigned bit) {
    mask_bits_t mask = ((mask_bits_t)1) << (bit % GC_MASK_SIZE);
    _Atomic(mask_bits_t) *ptr = (_Atomic(mask_bits_t)*)&bitmap->a[bit / GC_MASK_SIZE];
    mask_bits_t bits = atomic_fetch_or(ptr, mask);
    return (bits & mask) != 0;
}

// Zero exactly the slots the new object occupies, at the point of allocation:
// the zero-writes land in L1 immediately under the field writes that follow.
// (The old scheme memset whole pages at claim time; by the time a page's
// later objects were carved out those lines had been evicted, so every first
// field write missed again.) The zero state is load-bearing — the generated
// code writes each pointer field through the GC write barrier, which marks
// the field's PRIOR value, and a partially-initialised object may be scanned;
// NULL is safe, garbage is not. Written UNCONDITIONALLY here: at each inlined
// call site the C compiler sees which zero-stores are overwritten before they
// can be observed and elides exactly those — do not hand-optimise this loop.
INLINE void zero_object_slots(void *object, size_t actual_size) {
    slot_t *s = (slot_t*)object;
    for (size_t k = 0; k < actual_size / sizeof(slot_t); ++k)
        s[k] = (slot_t){0};
}

typedef struct {
    char *bump; // -size to get next object reference
    char *base; // until <base_pointer, then we need to ask for more
} bump_pointers_t;

// The per-thread allocation state, split out of object.c's private
// gc_thread_info so the fast path can inline into generated code. The rest
// of the thread record stays private in object.c; it holds a pointer to this
// block for the collector's remote accesses (root-scan region reset,
// safe-point requests).
typedef struct {
    _Atomic(int_fast32_t) safe_point_request;   // GC_SAFE_POINT_* bits
    bump_pointers_t region_mutable;
    bump_pointers_t region_immutable;
    bool local_active;   // thread-local nursery collecting right now (prototype)
    uint32_t local_epoch; // its epoch (0 when none): the barrier's private test
} gc_alloc_tl_t;
EXTERN thread_local gc_alloc_tl_t gc_alloc_tl;

// The slow half: multi-page objects, and region refill — which is also where
// the GC pacing clock ticks. RAW contract: the returned memory is NOT zeroed;
// every caller goes through object_alloc_fast (which zeroes at the call site)
// except array_create's pointer-free-payload path, which zeroes the header
// slots only.
EXTERN void *object_alloc_slow_raw(size_t size, bool is_mutable);

// RAW bump allocation: claims and publishes the slots but does NOT zero them.
// Callers must either zero (object_alloc_fast) or prove the zero state is
// load-bearing for nothing (a pointer-free array payload — see array_create).
INLINE void *object_alloc_fast_raw(size_t size, bool is_mutable) {
    size_t actual_size = (size + sizeof(slot_t) - 1) / sizeof(slot_t) * sizeof(slot_t);
    bump_pointers_t *bp = is_mutable
        ? &gc_alloc_tl.region_mutable
        : &gc_alloc_tl.region_immutable;
    if (UNLIKELY(actual_size > (size_t)MAX_OBJECT_SIZE
                 || (size_t)(bp->bump - bp->base) < actual_size))
        return object_alloc_slow_raw(size, is_mutable);
    void *object = (bp->bump -= actual_size);

    // Publish into the page's objects bitmap. Non-atomic: the bump page is
    // this thread's own until its next root-scan safe point, which cannot
    // fall between here and the field initialisation that follows the call
    // (allocation + initialisation is straight-line code).
    gc_page_t *page = (gc_page_t*)((uintptr_t)object & ~(uintptr_t)(sizeof(gc_page_t)-1));
    unsigned slot = (unsigned)((slot_t*)object - page->slots);
    bitmap_fetch_set(&page->head.objects, slot);

    // Snapshot-smear guard: between a cycle opening and THIS thread's root
    // scan, objects allocated here land on pages that will be taken into the
    // current cycle's collection pool — no birth protection — and the stack
    // scan that would find them happens too late (the snapshot is ragged).
    // Allocate BLACK for exactly that window: mark the object seen at birth.
    // The window closes when this thread's scan clears the flag, so the cost
    // outside it is one thread-local load and a not-taken branch.
    if (UNLIKELY(gc_alloc_tl.safe_point_request & GC_SAFE_POINT_SCAN_ROOTS))
        atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, slot);

    return object;
}

INLINE void *object_alloc_fast(size_t size, bool is_mutable) {
    void *object = object_alloc_fast_raw(size, is_mutable);
    // Zeroed HERE, at the call site, so the C compiler sees which zero-stores
    // the immediate field writes make dead and elides exactly those (this now
    // covers the refill and multi-page paths too — the slow half is raw).
    size_t actual_size = (size + sizeof(slot_t) - 1) / sizeof(slot_t) * sizeof(slot_t);
    zero_object_slots(object, actual_size);
    return object;
}

// Allocate + install the vtable: what the generated code's NewObject emits.
// Every field is zero on return (see zero_object_slots — that NULL state is
// load-bearing for the write barrier and for scans of partially-initialised
// objects), and each call site's immediate field stores let the C compiler
// elide the redundant zeroes.
// `pinned`: born pinned (see object pinning) — constant at every call site,
// so it folds into the vtable store.
INLINE void *object_new(vtable_t *vtable, bool pinned) {
    object_t *object = (object_t*)object_alloc_fast(vtable->object_size, vtable->is_mutable);
    object->vtable = (vtable_t*)((uintptr_t)vtable_tag(vtable) | (pinned ? VTABLE_PIN_BIT : 0));
    return object;
}

// ── profiling (--profile) ────────────────────────────────────────────────────
// Programs compiled with --profile call yafl_prof_enter/leave around every
// function body and hand a descriptor table to yafl_prof_init from main().
// Split like gc_alloc_tl above: this block is only what the inline fast paths
// need; the sampler, timers and output live in prof.c. See
// docs/profiling-design.md.

typedef struct {
    const char* name;   // fully qualified YAFL name
    const char* file;   // defining source file ("" for synthesised functions)
    int32_t     line;   // 1-based definition line (0 for synthesised)
} yafl_prof_fn_t;

typedef struct {
    uint64_t*        counters;  // exact per-function call counts; single writer
                                // (this thread), read racily by the exit dump
    uint32_t*        stack;     // shadow stack of function ids, read by the
                                // sampling signal handler on this same thread
    _Atomic(int32_t) sp;        // logical depth; may exceed cap (see enter)
    int32_t          cap;
} yafl_prof_tl_t;
EXTERN thread_local yafl_prof_tl_t yafl_prof_tl;

// Called once from the generated main(), BEFORE thread_start — so it precedes
// every worker registration and every instrumented call.
EXTERN void yafl_prof_init(const yafl_prof_fn_t* functions, uint32_t n_functions);

// Exact call-graph edge: callee entered with `caller` on top of the shadow
// stack. One bounded hash probe in prof.c; covers direct, indirect and
// musttail calls identically. `caller` is 0xffffffff when the stack was
// beyond its cap (ancestry unknown — charged to the (truncated) row).
EXTERN void yafl_prof_edge(uint32_t callee, uint32_t caller);

// The per-call fast paths. Counters stay exact past the shadow-stack cap: sp
// keeps advancing (so enter/leave stay balanced) while element stores are
// skipped, and the sampler flags such samples as (truncated). The relaxed
// atomics on sp compile to plain moves; the signal fence orders the element
// store before the sp advance for the handler, which pairs it with an acquire
// fence after reading sp — an sp it reads covers only fully-stored elements.
INLINE void yafl_prof_enter(uint32_t id) {
    yafl_prof_tl_t* t = &yafl_prof_tl;
    if (UNLIKELY(t->counters == NULL))
        return;   // thread not registered (profiling off)
    t->counters[id]++;
    int32_t sp = atomic_load_explicit(&t->sp, memory_order_relaxed);
    if (LIKELY(sp > 0))
        yafl_prof_edge(id, sp <= t->cap ? t->stack[sp - 1] : 0xffffffffu);
    if (LIKELY(sp < t->cap))
        t->stack[sp] = id;
    atomic_signal_fence(memory_order_release);
    atomic_store_explicit(&t->sp, sp + 1, memory_order_relaxed);
}

INLINE void yafl_prof_leave(void) {
    yafl_prof_tl_t* t = &yafl_prof_tl;
    if (UNLIKELY(t->counters == NULL))
        return;
    int32_t sp = atomic_load_explicit(&t->sp, memory_order_relaxed);
    atomic_store_explicit(&t->sp, sp - 1, memory_order_relaxed);
}

EXTERN volatile bool gc_write_barrier_requested;


EXTERN void _gc_safe_point2(); // Arbitary safe point for GC magic to happen
EXTERN void _gc_write_barrier2(object_t **field, ptr_mask_t mask);
EXTERN void _gc_mark_as_seen2(object_t *object);

#define GC_SAFE_POINT()\
    do { if (UNLIKELY(atomic_load_explicit(&gc_alloc_tl.safe_point_request, memory_order_relaxed))) _gc_safe_point2(); } while (false)
// Thread-local nursery (prototype): a non-fresh pointer store may install a
// young pointer into an older container; the nursery must treat that slot as
// a root (gc_local_note_slot filters to the containers that need it).
EXTERN bool gc_local_enabled;
EXTERN volatile int gc_local_live;   // number of nurseries active right now
EXTERN void gc_local_note_slot(object_t *obj, object_t **slot, ptr_mask_t mask);
EXTERN void gc_local_escape_old(object_t **slot, ptr_mask_t mask);
EXTERN void gc_local_escape(object_t *value);
// The escape rules are about who else can reach an object, not whose store it
// is, so every thread runs them. A thread with an active nursery takes the
// full path. Any other thread (no nursery, not started, stood down) owes
// less: the value it stores came from elsewhere already escaped, or from its
// own pages, which no nursery collects. Only an OVERWRITTEN value sitting in
// someone's active nursery must escape, and only while any nursery is active.
//
// ORDER MATTERS: the old values are read BEFORE gc_local_live. A nursery
// raises gc_local_live before it allocates, so a value read from a slot that
// belongs to an active nursery guarantees a non-zero count on a later read.
// Reading the count first could see zero, stall, and then overwrite a value
// another nursery published meanwhile without escaping it.
// The store needs no record when its container is PRIVATE: an immutable
// object on a page of this thread's current nursery that has not escaped
// (gc_local_note_slot's first test, inline). Nothing outside the thread can
// reach it, and the nursery traces it, so whatever it gains stays reachable.
// The common case — construction, a builder still in its nursery — never
// leaves the caller. Skipping gc_local_note_slot also defers its flush of the
// previous pending store, which is allowed to wait for the next barrier call
// or nursery collection (both flush first).
// `obj` is the container itself (generated stores know it: ((T*)obj)->f),
// so its index on its page is direct — no search for the containing object.
INLINE bool gc_local_obj_private(object_t *obj) {
    if ((size_t)((char*)obj - _memory_heap_base) >= _memory_heap_bytes)
        return false;
    gc_page_t *page = (gc_page_t*)((uintptr_t)obj & ~(uintptr_t)(GC_PAGE_SIZE - 1));
    if (page->head.local_epoch != gc_alloc_tl.local_epoch || page->head.mutable
            || page->head.tag != PAGE_MAGIC_NUMBER)
        return false;
    unsigned c = (unsigned)(((char*)obj - (char*)page->slots) / GC_SLOT_SIZE);
    mask_bits_t esc = __atomic_load_n(&page->head.local_escaped.a[c / GC_MASK_SIZE], __ATOMIC_ACQUIRE);
    return ((esc >> (c % GC_MASK_SIZE)) & 1) == 0;
}

// The barrier of a thread with no active nursery: only the values being
// overwritten may need to escape (see above).
INLINE void gc_local_barrier_inactive(object_t **slot, ptr_mask_t mask) {
    // A FLAG, never the pointer: a local holding the value being dropped would
    // sit in the caller's frame (always inlined; at -O0 on the stack), where
    // the conservative scan would keep the dropped object alive.
    bool any = false;
    for (ptr_mask_t m = mask; m; m &= m - 1)
        any |= slot[__builtin_ctzll(m)] != NULL;
    atomic_signal_fence(memory_order_seq_cst);   // compiler order; x86 keeps load order
    if (any && gc_local_live)
        gc_local_escape_old(slot, mask);
}

// Generated stores: the container `obj` is known.
INLINE void gc_local_barrier_in(object_t *obj, object_t **slot, ptr_mask_t mask) {
    if (gc_alloc_tl.local_active) {
        if (!gc_local_obj_private(obj))
            gc_local_note_slot(obj, slot, mask);
        return;
    }
    gc_local_barrier_inactive(slot, mask);
}

// ── Barrier argument checks: plain asserts, stripped by NDEBUG ──────────────
// A heap store names its CONTAINER, and every nursery decision reads that
// container's own page header and object bit, so `obj` must truly be the BASE
// of an allocated heap object and `slot` must lie inside it. A ROOT slot, the
// other way round, must not be in the heap at all.
EXTERN size_t object_get_size(object_t* ptr);
INLINE bool gc_in_heap(const void *p) {
    return (size_t)((const char*)p - _memory_heap_base) < _memory_heap_bytes;
}
INLINE bool gc_is_container_of(object_t *obj, object_t **slot) {
    if (((uintptr_t)obj & (GC_SLOT_SIZE - 1)) != 0 || !gc_in_heap(obj))
        return false;                                             // aligned, in the heap
    gc_page_t *page = (gc_page_t*)((uintptr_t)obj & ~(uintptr_t)(GC_PAGE_SIZE - 1));
    if (page->head.tag != PAGE_MAGIC_NUMBER || (char*)obj < (char*)page->slots)
        return false;                                             // a real page header, past it
    uintptr_t c = ((uintptr_t)obj - (uintptr_t)page->slots) / GC_SLOT_SIZE;
    if (c >= SLOTS_PER_PAGE || ((page->head.objects.a[c / GC_MASK_SIZE] >> (c % GC_MASK_SIZE)) & 1) == 0)
        return false;                                             // an allocated object's base
    return (char*)slot >= (char*)obj && (char*)slot < (char*)obj + object_get_size(obj);
}

// A store into a field of the object `obj` (what generated code emits).
#define GC_WRITE_BARRIER_IN(obj, field, mask)\
    do {assert(gc_is_container_of((object_t*)(obj), (object_t**)&(field)));\
        if (UNLIKELY(gc_write_barrier_requested))\
            _gc_write_barrier2((object_t**)&(field), (mask));\
        gc_local_barrier_in((object_t*)(obj), (object_t**)&(field), (mask));\
    } while (false)
// A FILL store (codegen's ObjectField.fill): NULL -> value into a slot of an
// array not yet published, written once but across safe points — array
// tabulation and builder pushes. Nothing is overwritten, so the snapshot
// barrier owes nothing. The one question is whether the array's PAGE is in
// this thread's current nursery: then the nursery traces the array (an
// escaped one is a root), and the value stays reachable through it. If not —
// the page was promoted or handed over at a root scan, or belongs to another
// worker's nursery after a cross-worker resume — the pointer has left our
// control: the value ESCAPES (permanently seen by its nursery). Emitted AFTER
// the store, reading the slot back; no safe point falls between the two. A
// thread with no active nursery has epoch 0, as has every page outside a
// nursery, so it passes the test and owes nothing.
#define GC_FILL_BARRIER(obj, field, mask)\
    do {assert(gc_is_container_of((object_t*)(obj), (object_t**)&(field)));\
        gc_page_t *gc_fill_page_ = (gc_page_t*)((uintptr_t)(obj) & ~(uintptr_t)(GC_PAGE_SIZE - 1));\
        if (UNLIKELY(gc_fill_page_->head.local_epoch != gc_alloc_tl.local_epoch))\
            gc_local_escape_old((object_t**)&(field), (mask));\
    } while (false)
// A value handed to the runtime or another thread (queues, completions,
// lazy publication): for a nursery it ESCAPES, whatever the marker is doing.
// The value is in hand before gc_local_live is read (same order as above).
#define GC_MARK_SEEN(value)\
    do { if (UNLIKELY(gc_write_barrier_requested)) _gc_mark_as_seen2(value);\
         atomic_signal_fence(memory_order_seq_cst);\
         if (gc_local_live) gc_local_escape((object_t*)(value)); } while (false)

// ── The mutable-root contract ────────────────────────────────────────────────
// Declared roots are scanned ONCE, at cycle open (the SATB snapshot). Any
// code that MUTATES a declared root after that must tell the marker, exactly
// as the heap write barrier does for object fields:
//   gc_root_overwrite(slot) — call BEFORE removing/overwriting a root slot's
//       occupant: shades the outgoing value (SATB deletion). Without it, an
//       object whose only path was this root slot is invisible to the cycle.
//   gc_root_publish(value)  — call when storing into a root slot a value the
//       thread might drop from its stack before its own root-scan safe
//       point: shades the incoming value (the ragged-snapshot window).
// YAFL global lets never need these (written once, NULL→value, and the lazy
// machinery shades its own publication); they are for the runtime's mutable
// roots — scheduler queues, IO continuation slots — and any C host code that
// registers mutable roots.
EXTERN void _gc_root_overwrite2(object_t** slot);
EXTERN void _gc_root_publish2(object_t* value);
INLINE void gc_root_overwrite(object_t** slot) {
    assert(!gc_in_heap(slot));   // heap slots take GC_WRITE_BARRIER_IN
    // Field-based: a root slot can hold a pointer to a RELOCATED object (a
    // forwarder compaction left); the shade must follow the chain — and may
    // snap the slot — exactly as the root scan itself does.
    if (UNLIKELY(gc_write_barrier_requested)) _gc_root_overwrite2(slot);
    bool had = *slot != NULL;                      // a flag, not a copy (see gc_local_barrier_inactive)
    atomic_signal_fence(memory_order_seq_cst);     // the value before the count
    if (had && gc_local_live) gc_local_escape(*slot);   // may be held elsewhere
}
// Returns its argument so compiler-emitted code can use it in value position.
INLINE object_t* gc_root_publish(object_t* value) {
    if (UNLIKELY(gc_write_barrier_requested)) _gc_root_publish2(value);
    atomic_signal_fence(memory_order_seq_cst);
    if (gc_local_live) gc_local_escape(value);
    return value;
}


EXTERN size_t object_get_size(object_t* ptr);
// The hottest accessor in the system — 1.96e9 calls per compiler run when
// out-of-line (every dispatch, instance test and marker visit). INLINE with
// the pin-bit mask; object.c keeps an exported alias for existing callers.
INLINE vtable_t *object_get_vtable_inline(object_t *object) {
    vtable_t *vt = object->vtable;
    while (UNLIKELY(vtable_is_forward(vt))) {
        object_t *next_object = (object_t*)vt;
        vt = next_object->vtable;
    }
    return vtable_untag(vt);
}
#define object_get_vtable object_get_vtable_inline

EXTERN int64_t list_builder_slot(object_t *cell);
EXTERN bool list_builder_link(object_t *prev, object_t *cell, int64_t slot);
EXTERN bool list_builder_seal(object_t *tail);
EXTERN bool array_builder_seal(object_t *arr, int32_t length);
EXTERN bool gc_debug_major_now(object_t *ignored);
EXTERN vtable_t *object_get_vtable(object_t *object);

// TRUE virtual dispatch: probe the hashed function table. The pre-rotated
// id masked by the pre-rotated mask (rotate(size-1)) is a BYTE offset into
// lookup[], so the rotation factor cancels. The hash is near-perfect, not
// perfect: create_perfect_lookups stops after a bounded number of rounds and
// may leave a few collisions, which the generator places in the following
// slots — so the lookup walks on from the hashed slot until the ids match,
// exactly as object_lookup_vtable does. Signed arithmetic matters: blank
// entries hold id -1, so a miss stops at the first blank, whose function is
// abort_on_vtable_lookup. (A version that read only the hashed slot answered
// a collided method with its neighbour's function.)
INLINE fun_t vtable_lookup(object_t* object, intptr_t id) {
    vtable_t* vt = object_get_vtable(object);
    const vtable_entry_t* e =
        (const vtable_entry_t*)((const char*)vt->lookup + (id & vt->functions_mask));
    while ((e->i ^ id) > 0) e++;
    return (fun_t){ .f = e->f, .o = (void*)object };
}
EXTERN fun_t object_lookup_vtable(object_t *object, intptr_t id);

// Tag-aware "is-a" test for match-arm dispatch. True if `obj` is an instance
// of `target` either exactly (its vtable == target) or transitively (target
// appears in its vtable's implements_array). NULL and tagged pointers match
// the appropriate pseudo-vtable (INTEGER_VTABLE / STR_HEAD_VTABLE — an inline
// String's word 0 is a tagged word) and nothing else.
struct integer_vtable;
struct str_head_vtable;
EXTERN struct integer_vtable INTEGER_VTABLE;
EXTERN struct str_head_vtable STR_HEAD_VTABLE;
INLINE bool object_is_instance(object_t* obj, vtable_t* target) {
    uintptr_t raw = (uintptr_t)obj;
    if (raw == 0) return false;
    if (raw & PTR_TAG_INTEGER) return target == (vtable_t*)&INTEGER_VTABLE;
    if ((raw & PTR_TAG_MASK) == PTR_TAG_STRING) return target == (vtable_t*)&STR_HEAD_VTABLE;
    if (raw & PTR_TAG_TASK) return false;
    // Follow any forwarding pointers left by compaction: a relocated object's
    // old slot holds the new object's (heap) address, not a vtable. Mirrors
    // object_get_vtable.
    vtable_t* vt = obj->vtable;
    while (UNLIKELY(vtable_is_forward(vt))) {
        obj = (object_t*)vt;
        vt = obj->vtable;
    }
    vt = vtable_untag(vt);
    if (vt == target) return true;
    for (vtable_t** p = vt->implements_array; *p != NULL; p++) {
        if (*p == target) return true;
    }
    return false;
}


typedef void(*roots_declaration_func_t)(void(*)(object_t**));
typedef void(*thread_roots_declaration_func_t)(void*,void(*)(object_t**));

EXTERN roots_declaration_func_t add_roots_declaration_func(roots_declaration_func_t);
EXTERN void object_gc_init();
EXTERN void gc_io_begin();   // Start of potentially thread pausing IO
EXTERN void gc_io_end();     // End of potentially thread pausing IO
EXTERN void gc_declare_thread(thread_roots_declaration_func_t,void*,object_t** stack_anchor); // Any thread that can do allocation must call this early on; the anchor must be a local in the calling frame — it bounds the conservative stack scan
EXTERN void yafl_stack_guard_init(void); // Install the per-thread stack-overflow guard (called from gc_declare_thread)

EXTERN void object_gc_print_heap(); // Print objects that survived the last GC

// CLI arguments (set by the emitted main() shim before thread_start).
extern int    _yafl_argc;
extern char** _yafl_argv;
EXTERN object_t* sys_argc(object_t* self);

EXTERN void* object_create(vtable_t* vtable);
EXTERN void* array_create(vtable_t* vtable, int32_t length, bool pinned);

EXTERN void abort_on_maths_error();
EXTERN void abort_on_vtable_lookup();
EXTERN void abort_on_out_of_memory();
EXTERN void abort_on_too_large_object();
EXTERN void abort_on_heap_allocation_on_non_worker_thread();
EXTERN void abort_on_array_bounds();

// Bounds-checked array access: returns `array` when 0 <= index < length and
// aborts otherwise. The single unsigned comparison rejects negative and
// over-length indices together. The caller casts the result to the element
// pointer type and indexes it.
INLINE void* array_bounds_check(int32_t index, int32_t length, void* array) {
    if (UNLIKELY((uint32_t)index >= (uint32_t)length)) abort_on_array_bounds();
    return array;
}

EXTERN void* memory_pages_alloc(size_t page_count);
EXTERN void memory_pages_free(void* ptr, size_t page_count);
EXTERN bool memory_pages_is_alloc_head(void*ptr);
EXTERN void* memory_pages_alloc_head_of(void*ptr);
EXTERN size_t memory_count();
// GC-clocked scavenger: returns excess free pages to the OS, retaining `retain`
// warm free pages as allocation slack. fsa_lock holders only — see mmap.c.
EXTERN void memory_scavenge(size_t retain, size_t max_pages);
EXTERN void memory_scavenge_stats(size_t* returned, size_t* reclaimed, size_t* cold_now,
                                  size_t* reclaimed_runs);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Worker Threads
 **
 *****
 *************
 *****************************
 **********************************************************/


EXTERN void declare_roots_thread(void(*)(object_t**));
EXTERN void thread_start(void(*entrypoint)(object_t*, fun_t));
EXTERN int32_t thread_current_id(void);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Task
 **
 *****
 *************
 *****************************
 **********************************************************/

// task_t is a YAFL object: its layout matches what the compiler emits for any
// subclass that extends `task` — flat-prefix fields shared by every subtype so
// (task_t*) casts of a subtype pointer hit each prefix field at the right
// offset.  async_lower._TASK_FIELDS must mirror this declaration exactly.
//
// state is _Atomic(int32_t) (not int_fast32_t) so its width is fixed at 4
// bytes on every platform — the IR represents it as Int(32) and the field
// offsets must agree byte-for-byte.
typedef struct task_s {
    vtable_t*               type;          // == object_t.vtable
    _Atomic(int32_t)        state;
    int32_t                 thread_id;     // originating worker thread index
    fun_t                   callback;
    _Atomic(struct task_s*) next;          // intrusive queue link
} task_t;

// Strip the PTR_TAG_TASK bit and yield a YAFL object pointer.  Callers that
// need task-specific fields cast to (task_t*) themselves.
#define TASK_UNTAG(ptr) ((object_t*)((uintptr_t)(ptr) & ~(uintptr_t)PTR_TAG_MASK))

// task_obj_t: task subtype whose result is an object_t* (the compiler's
// "task$DataPointer" layout — used for YAFL return types String, Int (bigint),
// union types, etc). Flat-layout extension of task_t.
typedef struct {
    vtable_t*               type;
    _Atomic(int32_t)        state;
    int32_t                 thread_id;
    fun_t                   callback;
    _Atomic(struct task_s*) next;
    object_t*               result;
} task_obj_t;


EXTERN struct task_vtable TASK_VTABLE;
EXTERN struct task_vtable TASK_OBJ_VTABLE;

// Compiler-facing aliases for the runtime's task vtables. Defined as macros
// rather than const variables so they expand to a compile-time constant at
// every use site (needed inside VTABLE_IMPLEMENTS' static initializer).
#define obj_task     ((vtable_t*)&TASK_VTABLE)
#define obj_task_obj ((vtable_t*)&TASK_OBJ_VTABLE)

// Public task API — every entry takes object_t* (just like the rest of the
// YAFL runtime) and casts internally.  Subclasses inherit task_t's prefix
// fields the normal YAFL way, so passing any task subtype works.
EXTERN object_t* task_init       (object_t* self);
EXTERN object_t* task_create     (object_t* self);
EXTERN object_t* task_obj_create (object_t* self);
EXTERN object_t* task_complete   (object_t* self);
EXTERN object_t* task_on_complete(object_t* self, fun_t callback);
EXTERN void _task_fire(void* self); // worker-loop entry: fire a queued task's callback once, on a clean dispatch frame

// Defer completion to a worker iteration. Same effect as task_complete
// except the registered callback (if any) runs in a fresh stack frame
// instead of synchronously. Compilers building task-trampolines call
// this so a long completion chain doesn't recurse on the C stack.
EXTERN object_t* task_complete_deferred(object_t* self);

// Fixed-prefix layout for compiler-generated parallel join tasks.  Mirrors
// task_t through `next`, then adds `remaining` for the join counter.  Each
// per-callsite par_task struct (emitted by async_lower._par_task_object) is a
// flat extension of this prefix.
typedef struct {
    vtable_t*               type;
    _Atomic(int32_t)        state;
    int32_t                 thread_id;
    fun_t                   callback;
    _Atomic(struct task_s*) next;
    _Atomic(int32_t)        remaining;
} task_par_base_t;

// Atomically decrement remaining; call task_complete when it reaches 0.
EXTERN object_t* task_par_decrement(object_t* par_task);

// Post task to its designated worker thread (task->thread_id).
EXTERN void thread_work_post(object_t* task);
// Round-robin post across workers — use when spreading parallel work.
EXTERN object_t* thread_work_post_parallel(object_t* task);
// Advisory backpressure: true while the runnable backlog is small enough that
// __parallel__ sites should fork; false asks them to evaluate sequentially.
// Threshold = YAFL_TASK_BACKLOG (default 4) queued tasks per worker.
EXTERN bool thread_work_accepting(void);
// Create an ad-hoc dispatch task from a fun_t and post it to the current thread.
// Returns NULL; the object_t* return makes the symbol usable from the YAFL
// compiler's `Invoke` form (which always assigns the result into a discard slot).
EXTERN object_t* thread_dispatch(fun_t action);
// `[future]` bind-time spawn: post a task firing `cb` (the per-type
// future_run$<T> runner bound to the stub) on a worker; no-op when the pool
// is not accepting — the binding then degrades to exactly [lazy]. NULL return
// for the same Invoke-form reason as thread_dispatch.
EXTERN object_t* future_post(fun_t cb);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Lazy initialisation
 **
 *****
 *************
 *****************************
 **********************************************************/


// Returns 1 if the flag is the (task_t*)1 sentinel, 0 otherwise.  The
// compiler's `Invoke` declares the call's return type as `Int(8)`, so
// the C signature uses `int32_t` (not `_Bool`) to make the high-bit
// state explicit and platform-independent.
INLINE int32_t lazy_global_init_complete(object_t* flag_ptr) {return 1==(intptr_t)flag_ptr;}


// Shared waiter-chain protocol: lazy_thunk_t is the layout prefix every
// compiler-generated lazy stub extends with a `value: <T>` field whose
// IR type varies per stub class.  `flag` follows the lazy_global_init
// convention: NULL = uninitialised, task_t* chain = init in flight with
// waiters queued, (task_t*)1 = initialised.  `closure` carries the init
// fun_t; the compiler-emitted fetch function clears it (.f = .o = NULL)
// after the value is stored so the GC doesn't pin the captured env.
typedef struct {
    vtable_t*               type;
    _Atomic(task_t*)        flag;
    fun_t                   closure;
} lazy_thunk_t;

// Atomically swap the waiter chain at *flag_field with the (task_t*)1
// "init complete" sentinel; resume each waiter via task_complete_deferred.
// Each waiter is a task_t with no result slot (used by lazy_global_init —
// awaiters re-read the global slot themselves).
EXPORT object_t* lazy_drain_waiters(object_t* flag_field);

// Atomic chain primitives used by compiler-emitted `lazy_drain$<mangle>`
// — the type-aware write happens in IR via `ObjectField` on the
// per-IR-type waiter subtype, so the runtime only needs to manage the
// chain itself.
//
// Swap the waiter-chain root with the "init complete" sentinel and
// return the previous head.  The loop body iterates from there.
INLINE object_t* lazy_chain_swap_sentinel(object_t* flag_field) {
    return (object_t*)atomic_exchange((_Atomic(object_t*)*)flag_field, (object_t*)1);
}

// Atomically read head->next and clear it; returns the next chain link
// (NULL when this is the last waiter).
INLINE object_t* lazy_chain_step(object_t* head) {
    _Atomic(struct task_s*)* p = &((task_t*)head)->next;
    task_t* next = (task_t*)atomic_load(p);
    atomic_store(p, NULL);
    return (object_t*)next;
}

// Atomically append `waiter` to the chain at *flag_field.  Returns:
//   0 — appended (init in flight on another thread)
//   1 — this thread won the init race; caller must run init
//   2 — flag was already (task_t*)1 by the time we tried; caller should
//       task_complete(waiter) so a chained on_complete still fires
EXPORT int32_t lazy_thunk_enqueue(object_t* flag_field, object_t* waiter);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Primitive operations
 **
 *****
 *************
 *****************************
 **********************************************************/


EXTERN void __abort_on_overflow();


INLINE bool test_gt_int32(int32_t self, int32_t data) { return self  > data; }
INLINE bool test_eq_int32(int32_t self, int32_t data) { return self == data; }
INLINE bool test_lt_int32(int32_t self, int32_t data) { return self  < data; }


/**********************************************************
 *****************************
 *************
 *****
 **
 *                     Big integer
 **
 *****
 *************
 *****************************
 **********************************************************/


typedef struct integer {
    vtable_t* vtable;
    uint32_t length;
    int32_t sign;       // 0 = positive (incl. zero), 1 = negative
    uintptr_t array[];  // magnitude limbs, little-endian; length>=1 (flexible array member)
} ALIGNED integer_t;

struct integer_vtable;
EXTERN struct integer_vtable INTEGER_VTABLE;


#if WORD_SIZE == 64
#define INTEGER_LITERAL_N(sign, count, array) ((object_t*)&(struct{vtable_t*v;uint32_t l;int32_t s;intptr_t a[count];}){VTABLE_TAG_CONST(&INTEGER_VTABLE),((count)+1)/2,sign,array})
#define INTEGER_LITERAL_N_1(value1) ((intptr_t)(value1))
#define INTEGER_LITERAL_N_2(value1, value2) (((intptr_t)(value1)&0xffffffffull)|((intptr_t)(value2)<<32))
#define INTEGER_LITERAL_1(sign, value1) ((object_t*)((intptr_t)value1*(sign?-1:1)*4+PTR_TAG_INTEGER))
#define INTEGER_LITERAL_2(sign, value1, value2) (((!sign)&&(value2>INT32_MAX/4))||(value2>INT32_MAX/4+1)?INTEGER_LITERAL_N(sign,2,{INTEGER_LITERAL_N_2(value1, value2)}):(object_t*)((((intptr_t)value2<<32)+value1)*(sign?-1:1)*4+PTR_TAG_INTEGER))
#else
#define INTEGER_LITERAL_N(sign, count, array) ((object_t*)&(struct{vtable_t*v;uint32_t l;int32_t s;intptr_t a[count];}){VTABLE_TAG_CONST(&INTEGER_VTABLE),count,sign,array})
#define INTEGER_LITERAL_N_1(value1) value1
#define INTEGER_LITERAL_N_2(value1, value2) value1, value2
#define INTEGER_LITERAL_1(sign, value1) (((!sign)&&value1>INT32_MAX/4)||(value1>INT32_MAX/4+1)?INTEGER_LITERAL_N(sign,1,{value1}):(object_t*)((intptr_t)value1*(sign?-1:1)*4+PTR_TAG_INTEGER))
#define INTEGER_LITERAL_2(sign, value1, value2) INTEGER_LITERAL_N(sign, 2, {INTEGER_LITERAL_N_2(value1, value2)})
#endif
#define INTEGER_LITERAL_SEP ,


EXTERN object_t* integer_add_full(object_t* self, object_t* data);
INLINE object_t* integer_add(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data, vc;
    if (LIKELY(va&vb&PTR_TAG_INTEGER && !__builtin_add_overflow(va, vb^PTR_TAG_INTEGER, &vc))) {
        return (object_t*)vc;
    }
    return integer_add_full(self, data);
}

EXTERN object_t* integer_sub_full(object_t* self, object_t* data);
INLINE object_t* integer_sub(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data, vc;
    if (LIKELY(va&vb&PTR_TAG_INTEGER && !__builtin_sub_overflow(va, vb^PTR_TAG_INTEGER, &vc))) {
        return (object_t*)vc;
    }
    return integer_sub_full(self, data);
}

EXPORT object_t* integer_inv_full(object_t* o);
INLINE object_t* integer_inv(object_t* o) {
    intptr_t v = (intptr_t)o;
    if (v&PTR_TAG_INTEGER) {
        return (object_t*)(v ^ ((intptr_t)-4));
    }
    return integer_inv_full(o);
}

// Bitwise binary ops. Both-tagged fast path: AND/OR preserve the tag bit
// (x&x, x|x), but XOR cancels it and ANDNOT clears it, so those re-apply
// PTR_TAG_INTEGER. The result of a bitwise op never exceeds the wider operand,
// so a tagged-in result stays in range.
EXPORT object_t* integer_and_full(object_t* a, object_t* b);
EXPORT object_t* integer_or_full(object_t* a, object_t* b);
EXPORT object_t* integer_xor_full(object_t* a, object_t* b);
EXPORT object_t* integer_andnot_full(object_t* a, object_t* b);

INLINE object_t* integer_and(object_t* a, object_t* b) {
    intptr_t va = (intptr_t)a, vb = (intptr_t)b;
    if (va & vb & PTR_TAG_INTEGER) return (object_t*)(va & vb);
    return integer_and_full(a, b);
}
INLINE object_t* integer_or(object_t* a, object_t* b) {
    intptr_t va = (intptr_t)a, vb = (intptr_t)b;
    if (va & vb & PTR_TAG_INTEGER) return (object_t*)(va | vb);
    return integer_or_full(a, b);
}
INLINE object_t* integer_xor(object_t* a, object_t* b) {
    intptr_t va = (intptr_t)a, vb = (intptr_t)b;
    if (va & vb & PTR_TAG_INTEGER) return (object_t*)((va ^ vb) | PTR_TAG_INTEGER);
    return integer_xor_full(a, b);
}
INLINE object_t* integer_andnot(object_t* a, object_t* b) {
    intptr_t va = (intptr_t)a, vb = (intptr_t)b;
    if (va & vb & PTR_TAG_INTEGER) return (object_t*)((va & ~vb) | PTR_TAG_INTEGER);
    return integer_andnot_full(a, b);
}

EXTERN object_t* integer_div(object_t* self, object_t* data);
EXTERN object_t* integer_mul(object_t* self, object_t* data);
EXTERN object_t* integer_rem(object_t* self, object_t* data);
EXTERN int32_t   integer_cmp_full(object_t* self, object_t* data);
// Every Int comparison in generated code lands here — the tagged-literal
// fast path is a raw word compare (same tag bit; value in the upper bits,
// two's-complement order preserved by the shift encoding), so it belongs
// inline next to integer_add/sub rather than behind a cross-TU call.
INLINE int32_t integer_cmp(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    if (LIKELY(va & vb & PTR_TAG_INTEGER)) {
        if (va < vb) return -1;
        if (va > vb) return 1;
        return 0;
    }
    return integer_cmp_full(self, data);
}
EXTERN object_t* integer_shl(object_t* self, object_t* amount);
EXTERN object_t* integer_shr(object_t* self, object_t* amount);

EXTERN object_t* integer_add_int32(object_t* self, int32_t value);
EXTERN int32_t   integer_cmp_int32(object_t* self, int32_t value);
EXTERN int32_t   int32_from_integer(object_t* self);
// An int32 always fits the tagged-literal encoding (value << 2 | tag), so
// boxing one is three instructions and never allocates.
INLINE object_t* integer_from_int32(int32_t value) {
    return (object_t*)(((intptr_t)value << 2) | PTR_TAG_INTEGER);
}
EXTERN object_t* integer_from_int32_noalloc(int32_t value);

// Tagged-pointer fast path; caller guarantees `value` fits in signed 24 bits
// (i.e. INT24_MIN..INT24_MAX). Never allocates.  Use when the producer's
// range is statically bounded (byte values, compare results, small counts).
INLINE object_t* integer_from_int24(int32_t value) {
    return (object_t*)((intptr_t)value * 4 + PTR_TAG_INTEGER);
}

// Both paths inline — no out-of-line fallback. A call site, even on the cold
// path, forces the C compiler to assume caller-save clobbers across the
// branch, spilling hot-path values it would otherwise keep in registers.
INLINE int32_t int32_from_integer_with_overflow(object_t* self, int* overflow) {
    intptr_t result;
    *overflow = 0;
    if (PTR_IS_INTEGER(self)) {
        result = (int32_t)((intptr_t)self >> 2);
    } else {
        integer_t* a = (integer_t*)self;
        result = a->array[0];
        if (a->sign) {
            result = -result;
        }
        if (a->length > 1) {
            *overflow = 1;
        }
    }
#if WORD_SIZE == 64
    if (result < INT32_MIN || result > INT32_MAX) {
        *overflow = 1;
    }
#endif
    return (int32_t)result;
}

INLINE bool integer_test_gt(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&PTR_TAG_INTEGER && va>vb) || integer_cmp(self, data) > 0;
}
INLINE bool integer_test_ge(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&PTR_TAG_INTEGER && va>=vb) || integer_cmp(self, data) >= 0;
}
INLINE bool integer_test_eq(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&PTR_TAG_INTEGER && va==vb) || integer_cmp(self, data) == 0;
}
INLINE bool integer_test_lt(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&PTR_TAG_INTEGER && va<vb) || integer_cmp(self, data) < 0;
}
INLINE bool integer_test_le(object_t* self, object_t* data) {
    intptr_t va = (intptr_t)self, vb = (intptr_t)data;
    return LIKELY(va&vb&PTR_TAG_INTEGER && va<=vb) || integer_cmp(self, data) <= 0;
}

// Fixed-width integer math: defined wrap on overflow via unsigned cast.
// Comparisons return bool; the _test_ infix is preserved here because the
// bigint side (`integer_test_*`) uses it and renaming both is out of scope.

INLINE int8_t   int8_add(int8_t a, int8_t b)   { return (int8_t)((uint8_t)a + (uint8_t)b); }
INLINE int8_t   int8_sub(int8_t a, int8_t b)   { return (int8_t)((uint8_t)a - (uint8_t)b); }
INLINE int8_t   int8_mul(int8_t a, int8_t b)   { return (int8_t)((uint8_t)a * (uint8_t)b); }
INLINE int8_t   int8_neg(int8_t a)             { return (int8_t)(0u - (uint8_t)a); }
INLINE int8_t   int8_inv(int8_t a)             { return (int8_t)(~(uint8_t)a); }
INLINE int8_t   int8_and(int8_t a, int8_t b)   { return (int8_t)((uint8_t)a & (uint8_t)b); }
INLINE int8_t   int8_or(int8_t a, int8_t b)    { return (int8_t)((uint8_t)a | (uint8_t)b); }
INLINE int8_t   int8_xor(int8_t a, int8_t b)   { return (int8_t)((uint8_t)a ^ (uint8_t)b); }
INLINE int8_t   int8_andnot(int8_t a, int8_t b){ return (int8_t)((uint8_t)a & (uint8_t)~(uint8_t)b); }
INLINE int8_t   int8_shl(int8_t a, int8_t b)   { return (int8_t)((uint8_t)a << ((uint8_t)b & 7)); }
INLINE int8_t   int8_shr(int8_t a, int8_t b)   { return (int8_t)(a >> ((uint8_t)b & 7)); }  /* arithmetic */
// Paper over INT_MIN / -1 — see int32_div below for context.
INLINE int8_t   int8_div(int8_t a, int8_t b)   { return b == -1 ? int8_neg(a) : (int8_t)(a / b); }
INLINE int8_t   int8_rem(int8_t a, int8_t b)   { return b == -1 ? 0           : (int8_t)(a % b); }
INLINE bool     int8_test_lt(int8_t a, int8_t b) { return a <  b; }
INLINE bool     int8_test_eq(int8_t a, int8_t b) { return a == b; }
INLINE bool     int8_test_gt(int8_t a, int8_t b) { return a >  b; }

INLINE int16_t  int16_add(int16_t a, int16_t b) { return (int16_t)((uint16_t)a + (uint16_t)b); }
INLINE int16_t  int16_sub(int16_t a, int16_t b) { return (int16_t)((uint16_t)a - (uint16_t)b); }
INLINE int16_t  int16_mul(int16_t a, int16_t b) { return (int16_t)((uint16_t)a * (uint16_t)b); }
INLINE int16_t  int16_neg(int16_t a)            { return (int16_t)(0u - (uint16_t)a); }
INLINE int16_t  int16_inv(int16_t a)            { return (int16_t)(~(uint16_t)a); }
INLINE int16_t  int16_and(int16_t a, int16_t b) { return (int16_t)((uint16_t)a & (uint16_t)b); }
INLINE int16_t  int16_or(int16_t a, int16_t b)  { return (int16_t)((uint16_t)a | (uint16_t)b); }
INLINE int16_t  int16_xor(int16_t a, int16_t b) { return (int16_t)((uint16_t)a ^ (uint16_t)b); }
INLINE int16_t  int16_andnot(int16_t a, int16_t b) { return (int16_t)((uint16_t)a & (uint16_t)~(uint16_t)b); }
INLINE int16_t  int16_shl(int16_t a, int16_t b) { return (int16_t)((uint16_t)a << ((uint16_t)b & 15)); }
INLINE int16_t  int16_shr(int16_t a, int16_t b) { return (int16_t)(a >> ((uint16_t)b & 15)); }  /* arithmetic */
INLINE int16_t  int16_div(int16_t a, int16_t b) { return b == -1 ? int16_neg(a) : (int16_t)(a / b); }
INLINE int16_t  int16_rem(int16_t a, int16_t b) { return b == -1 ? 0            : (int16_t)(a % b); }
INLINE bool     int16_test_lt(int16_t a, int16_t b) { return a <  b; }
INLINE bool     int16_test_eq(int16_t a, int16_t b) { return a == b; }
INLINE bool     int16_test_gt(int16_t a, int16_t b) { return a >  b; }

INLINE int32_t  int32_add(int32_t self, int32_t data) { return self + data; }
INLINE int32_t  int32_sub(int32_t self, int32_t data) { return self - data; }
INLINE int32_t  int32_mul(int32_t self, int32_t data) { return self * data; }
INLINE int32_t  int32_neg(int32_t self)                { return (int32_t)(0u - (uint32_t)self); }
INLINE int32_t  int32_inv(int32_t self)                { return (int32_t)(~(uint32_t)self); }
INLINE int32_t  int32_and(int32_t a, int32_t b)        { return (int32_t)((uint32_t)a & (uint32_t)b); }
INLINE int32_t  int32_or(int32_t a, int32_t b)         { return (int32_t)((uint32_t)a | (uint32_t)b); }
INLINE int32_t  int32_xor(int32_t a, int32_t b)        { return (int32_t)((uint32_t)a ^ (uint32_t)b); }
INLINE int32_t  int32_andnot(int32_t a, int32_t b)     { return (int32_t)((uint32_t)a & ~(uint32_t)b); }
INLINE int32_t  int32_shl(int32_t a, int32_t b)        { return (int32_t)((uint32_t)a << ((uint32_t)b & 31)); }
INLINE int32_t  int32_shr(int32_t a, int32_t b)        { return (int32_t)(a >> ((uint32_t)b & 31)); }  /* arithmetic */
// On x86 INT_MIN / -1 raises SIGFPE because the true quotient (+2^31) overflows
// the destination register — `idiv`'s overflow trap shares the divide-by-zero
// signal. Paper over by defining INT_MIN / -1 = INT_MIN (Java/Kotlin convention)
// and INT_MIN % -1 = 0. Cheap predictable branch on the cold path.
INLINE int32_t  int32_div(int32_t self, int32_t data) { return data == -1 ? int32_neg(self) : self / data; }
INLINE int32_t  int32_rem(int32_t self, int32_t data) { return data == -1 ? 0               : self % data; }
INLINE bool int32_test_gt(int32_t self, int32_t data) { return self > data; }
INLINE bool int32_test_eq(int32_t self, int32_t data) { return self ==data; }
INLINE bool int32_test_lt(int32_t self, int32_t data) { return self < data; }

INLINE int64_t  int64_add(int64_t a, int64_t b) { return (int64_t)((uint64_t)a + (uint64_t)b); }
INLINE int64_t  int64_sub(int64_t a, int64_t b) { return (int64_t)((uint64_t)a - (uint64_t)b); }
INLINE int64_t  int64_mul(int64_t a, int64_t b) { return (int64_t)((uint64_t)a * (uint64_t)b); }
INLINE int64_t  int64_neg(int64_t a)            { return (int64_t)(0u - (uint64_t)a); }
INLINE int64_t  int64_inv(int64_t a)            { return (int64_t)(~(uint64_t)a); }
INLINE int64_t  int64_and(int64_t a, int64_t b) { return (int64_t)((uint64_t)a & (uint64_t)b); }
INLINE int64_t  int64_or(int64_t a, int64_t b)  { return (int64_t)((uint64_t)a | (uint64_t)b); }
INLINE int64_t  int64_xor(int64_t a, int64_t b) { return (int64_t)((uint64_t)a ^ (uint64_t)b); }
INLINE int64_t  int64_andnot(int64_t a, int64_t b) { return (int64_t)((uint64_t)a & ~(uint64_t)b); }
INLINE int64_t  int64_shl(int64_t a, int64_t b) { return (int64_t)((uint64_t)a << ((uint64_t)b & 63)); }
INLINE int64_t  int64_shr(int64_t a, int64_t b) { return (int64_t)(a >> ((uint64_t)b & 63)); }  /* arithmetic */
INLINE int64_t  int64_div(int64_t a, int64_t b) { return b == -1 ? int64_neg(a) : a / b; }
INLINE int64_t  int64_rem(int64_t a, int64_t b) { return b == -1 ? 0            : a % b; }
INLINE bool     int64_test_lt(int64_t a, int64_t b) { return a <  b; }
INLINE bool     int64_test_eq(int64_t a, int64_t b) { return a == b; }
INLINE bool     int64_test_gt(int64_t a, int64_t b) { return a >  b; }

// Int↔Int width conversions. The narrowing direction wraps by taking the
// low N bits (defined via unsigned cast); widening is sign-extending.
INLINE int16_t  int16_from_int8 (int8_t  v) { return (int16_t)v; }
INLINE int32_t  int32_from_int8 (int8_t  v) { return (int32_t)v; }
INLINE int64_t  int64_from_int8 (int8_t  v) { return (int64_t)v; }
INLINE int32_t  int32_from_int16(int16_t v) { return (int32_t)v; }
INLINE int64_t  int64_from_int16(int16_t v) { return (int64_t)v; }
INLINE int64_t  int64_from_int32(int32_t v) { return (int64_t)v; }
INLINE int8_t   int8_from_int16 (int16_t v) { return (int8_t)v; }
INLINE int8_t   int8_from_int32 (int32_t v) { return (int8_t)v; }
INLINE int8_t   int8_from_int64 (int64_t v) { return (int8_t)v; }
INLINE int16_t  int16_from_int32(int32_t v) { return (int16_t)v; }
INLINE int16_t  int16_from_int64(int64_t v) { return (int16_t)v; }
INLINE int32_t  int32_from_int64(int64_t v) { return (int32_t)v; }

// Float ↔ fixed-width int. Widening to float (int32_t → double, etc.) is
// inline cast; narrowing (float → intN) clamps + truncs and lives out-of-line.
INLINE double   float64_from_int8 (int8_t  i) { return (double)i; }
INLINE double   float64_from_int16(int16_t i) { return (double)i; }
INLINE double   float64_from_int32(int32_t i) { return (double)i; }
INLINE double   float64_from_int64(int64_t i) { return (double)i; }
INLINE float    float32_from_int8 (int8_t  i) { return (float)i;  }
INLINE float    float32_from_int16(int16_t i) { return (float)i;  }
// (float32_from_int32 and float32_from_int64 declared further down with the
//  Float32 block so they sit next to other float32 declarations.)

EXTERN int8_t    int8_from_float64 (double f);
EXTERN int16_t   int16_from_float64(double f);
EXTERN int32_t   int32_from_float64(double f);
EXTERN int64_t   int64_from_float64(double f);
EXTERN int8_t    int8_from_float32 (float  f);
EXTERN int16_t   int16_from_float32(float  f);
EXTERN int32_t   int32_from_float32(float  f);
EXTERN int64_t   int64_from_float32(float  f);

// Bigint ↔ fixed-width int. Truncate variants take the low N bits in
// two's-complement. The non-truncate Int↔bigint conversions are exact —
// they preserve the value for the widening direction (int → bigint) but
// abort on overflow for narrowing; callers that want wrap-on-overflow
// should use the _truncate variant.
EXTERN object_t* integer_from_int8 (int8_t  v);
EXTERN object_t* integer_from_int16(int16_t v);
// integer_from_int32 / integer_from_int32_noalloc declared above.
EXTERN object_t* integer_from_int64(int64_t v);
EXTERN int8_t    int8_from_integer_truncate (object_t* self);
EXTERN int16_t   int16_from_integer_truncate(object_t* self);
EXTERN int32_t   int32_from_integer_truncate(object_t* self);
EXTERN int64_t   int64_from_integer_truncate(object_t* self);


// Decimal-render an arbitrary-precision Int into a CALLER-SUPPLIED buffer.
// Allocates nothing — neither YAFL heap nor malloc — so it is usable from the
// logger, from a GC worker, and anywhere allocation would be a re-entrancy
// hazard. `size` includes the NUL; returns bytes written excluding it. If the
// exact value does not fit, NOTHING partial is written: the buffer gets
// `<int:~N digits>` instead, because a truncated numeral reads as a genuine
// smaller number. See integer.c for the full contract.
EXTERN int32_t   integer_to_cstr(object_t* self, char* buf, int32_t size);



/**********************************************************
 *****************************
 *************
 *****
 **
 *                       Float
 **
 *****
 *************
 *****************************
 **********************************************************/

INLINE double   float64_add(double a, double b) { return a + b; }
INLINE double   float64_sub(double a, double b) { return a - b; }
INLINE double   float64_mul(double a, double b) { return a * b; }
INLINE double   float64_div(double a, double b) { return a / b; }
INLINE double   float64_neg(double a)            { return -a; }
INLINE double   float64_rem(double a, double b)  { return fmod(a, b); }
INLINE double   float64_sqrt(double a)           { return sqrt(a); }
INLINE float    float32_sqrt(float a)            { return sqrtf(a); }
INLINE bool     float64_lt (double a, double b)  { return a <  b; }
INLINE bool     float64_eq (double a, double b)  { return a == b; }
INLINE bool     float64_gt (double a, double b)  { return a >  b; }
// ge/le exist for match RANGE arms: IEEE gives false for NaN on every
// comparison, so NaN matches no range (the !(a<b) negation would not).
INLINE bool     float64_ge (double a, double b)  { return a >= b; }
INLINE bool     float64_le (double a, double b)  { return a <= b; }
INLINE bool     float64_is_nan(double a)         { return a != a; }

EXTERN double    float64_from_integer(object_t* i);
EXTERN object_t* integer_from_float64(double f);

INLINE float    float32_add(float a, float b) { return a + b; }
INLINE float    float32_sub(float a, float b) { return a - b; }
INLINE float    float32_mul(float a, float b) { return a * b; }
INLINE float    float32_div(float a, float b) { return a / b; }
INLINE float    float32_neg(float a)           { return -a; }
INLINE float    float32_rem(float a, float b)  { return fmodf(a, b); }
INLINE bool     float32_lt (float a, float b)  { return a <  b; }
INLINE bool     float32_eq (float a, float b)  { return a == b; }
INLINE bool     float32_gt (float a, float b)  { return a >  b; }
INLINE bool     float32_ge (float a, float b)  { return a >= b; }
INLINE bool     float32_le (float a, float b)  { return a <= b; }
INLINE bool     float32_is_nan(float a)        { return a != a; }

INLINE float    float32_from_float64(double d) { return (float)d; }
INLINE double   float64_from_float32(float f)  { return (double)f; }
INLINE float    float32_from_int32(int32_t i)  { return (float)i; }
INLINE float    float32_from_int64(int64_t i)  { return (float)i; }
EXTERN float    float32_from_integer(object_t* i);
EXTERN object_t* integer_from_float32(float f);
EXTERN int32_t float32_hash(float f);



/**********************************************************
 *****************************
 *************
 *****
 **
 *                   Strings
 **
 *****
 *************
 *****************************
 **********************************************************/

// The heap head of a String value: every heap-held String's bytes live in
// one — a growable buffer (STR_BUF_VTABLE) or a read-only head (a static
// literal, STR_HEAD_VTABLE) — so a head's bytes are always at the same offset.
typedef struct str_head {
    vtable_t* vtable;
    uint32_t length;
    // Growable heads (STR_BUF_VTABLE): capacity + 1. It is the vtable's
    // array_cap_offset, so compaction resets it to `length` on a copy (the
    // copy owns no spare room). 0 on every read-only head.
    uint32_t capacity;
    // Hash cache: (covered length << 32) | hash of array[0, covered length);
    // 0 = none. The covered bytes never change (a head only grows past its
    // used length), so one atomic word is the whole protocol — a racing
    // writer stores a correct value too, and a compaction copy carries a
    // still-valid entry.
    _Atomic(uint64_t) hash;
    uint8_t array[16];
} ALIGNED str_head_t;

struct str_head_vtable;
EXTERN struct str_head_vtable STR_HEAD_VTABLE;

// Compile-time length of a C string literal.
#define STRING_LEN(str) (sizeof(str) - 1)


/**********************************************************
 *****
 *************
 *****************************
 *                   String values (str_t)
 **
 *****
 *************
 *****************************
 **********************************************************/

// A YAFL String is a 16-byte VALUE, two modes told apart by word 0:
//
//   INLINE (length <= 15): `head` is a packed-string word, low byte
//     len << 3 | PTR_TAG_STRING (the GC reads any tagged word as a
//     non-pointer); content bytes 0..14 are bytes 1..15 of the value.
//   HEAP (length >= 16): `head` is a buffer (str_head_t layout); `meta` holds
//     head_len (low 29 bits) | tail_len << 29, `tail` up to 4 more bytes.
//
//   content = inline bytes, or head->array[0 .. head_len) ++ tail[0 .. tail_len)
//
// CANONICAL BY LENGTH: inline exactly when length <= 15, and unused inline
// bytes are always zero — so short strings are equal iff their 16 bytes are.
//
// Growable heads carry STR_BUF_VTABLE: `length` = used + 1 (the GC sizes the
// object by it, so compaction trims spare capacity) and the hash slot =
// capacity + 1 (array_cap_offset: compaction resets it to length on the
// copy). `used` is the high-water mark; a value extends a head in place only
// when it holds the PIN and owns the end (head_len == used) — see str.c.
// Any other head (a static literal, STR_HEAD_VTABLE) is read-only.
//
// Union values that contain String use str_t too: word 0 dispatches exactly
// like a one-word union (NULL = None, tagged Int, class pointer, or a
// string), word 1 is String payload.
// 16 bytes on every word size. 64-bit: 4 tail bytes, head_len 29 bits.
// 32-bit: `head` is 4 bytes, so the tail is 8 and head_len 28 bits (4 bits of
// tail_len). Inline content is always value bytes 1..15, and the tail always
// starts at `tail` — C reaches both through byte pointers, never by word.
#if WORD_SIZE == 32
typedef struct str {
    object_t* head;
    uint32_t  meta;
    uint32_t  tail[2];
} str_t;
#define STR_TAIL_MAX      8
#define STR_META_LEN_BITS 28
#else
typedef struct str {
    object_t* head;
    uint32_t  meta;
    uint32_t  tail[1];
} str_t;
#define STR_TAIL_MAX      4
#define STR_META_LEN_BITS 29
#endif
_Static_assert(sizeof(str_t) == 16, "str_t is 16 bytes on every target");

#define STR_INLINE_MAX    15
#define STR_META_LEN_MASK ((1u << STR_META_LEN_BITS) - 1)
// The tag byte — `head`'s low byte, which carries PTR_TAG_STRING and the
// inline length — sits at this offset in memory: first on little-endian,
// last in the word on big-endian. An inline value's 15 content bytes are the
// other 15, in memory order: bytes 1..15 on little-endian; on big-endian the
// bytes before the tag byte, then the bytes after it.
#define STR_TAG_BYTE (IS_LITTLE_ENDIAN ? 0 : (int)sizeof(void*) - 1)
// Offset within the value of inline content byte i (0..14).
INLINE int str_inline_off(int i) { return i < STR_TAG_BYTE ? i : i + 1; }
INLINE uint8_t* str_tail_bytes(str_t* s)   { return (uint8_t*)s->tail; }

EXTERN struct str_head_vtable STR_BUF_VTABLE;

INLINE bool str_is_inline(str_t s) {
    return ((uintptr_t)s.head & PTR_TAG_MASK) == PTR_TAG_STRING;
}
INLINE int32_t str_length(str_t s) {
    return str_is_inline(s) ? (int32_t)(((uintptr_t)s.head & 0xff) >> 3)
                            : (int32_t)((s.meta & STR_META_LEN_MASK) + (s.meta >> STR_META_LEN_BITS));
}

// Literals. The compiler picks the form from the UTF-8 byte length. The
// short form spells the 16 bytes as byte 0 = tag, bytes 1..15 = content,
// assembled into whichever words this target has.
#define STR16_B(c, i) ((uint64_t)(uint8_t)(STRING_LEN(c) > (i) ? (c)[i] : 0))
#define STR16_TAGB(c) ((uint64_t)(STRING_LEN(c) * (PTR_TAG_MASK+1) + PTR_TAG_STRING))
#if IS_LITTLE_ENDIAN
// Little-endian word of value bytes [o, o+4) where value byte 0 is the tag.
#define STR16_W32(c, o) ((uint32_t)( \
      ((o) == 0 ? STR16_TAGB(c) : STR16_B(c, (o)-1)) \
    | STR16_B(c, (o))   << 8 | STR16_B(c, (o)+1) << 16 | STR16_B(c, (o)+2) << 24))
#else
// Big-endian word of content bytes [k, k+4), and the head word's last word,
// whose final byte is the tag.
#define STR16_BE32(c, k) ((uint32_t)( \
      STR16_B(c, (k)) << 24 | STR16_B(c, (k)+1) << 16 | STR16_B(c, (k)+2) << 8 | STR16_B(c, (k)+3)))
#define STR16_BE32_TAG(c, k) ((uint32_t)( \
      STR16_B(c, (k)) << 24 | STR16_B(c, (k)+1) << 16 | STR16_B(c, (k)+2) << 8 | STR16_TAGB(c)))
#endif
#if WORD_SIZE == 32 && IS_LITTLE_ENDIAN
#define STR16_SHORT(c) ((str_t){ \
    .head = (object_t*)(uintptr_t)STR16_W32(c, 0), \
    .meta = STR16_W32(c, 4), .tail = { STR16_W32(c, 8), STR16_W32(c, 12) } })
#elif IS_LITTLE_ENDIAN
#define STR16_SHORT(c) ((str_t){ \
    .head = (object_t*)(uintptr_t)((uint64_t)STR16_W32(c, 0) | (uint64_t)STR16_W32(c, 4) << 32), \
    .meta = STR16_W32(c, 8), .tail = { STR16_W32(c, 12) } })
#elif WORD_SIZE == 32
// content 0..2 + tag | 3..6 | 7..10 | 11..14
#define STR16_SHORT(c) ((str_t){ \
    .head = (object_t*)(uintptr_t)STR16_BE32_TAG(c, 0), \
    .meta = STR16_BE32(c, 3), .tail = { STR16_BE32(c, 7), STR16_BE32(c, 11) } })
#else
// content 0..3 | 4..6 + tag | 7..10 | 11..14
#define STR16_SHORT(c) ((str_t){ \
    .head = (object_t*)(uintptr_t)((uint64_t)STR16_BE32(c, 0) << 32 | (uint64_t)STR16_BE32_TAG(c, 4)), \
    .meta = STR16_BE32(c, 7), .tail = { STR16_BE32(c, 11) } })
#endif
#define STR16_LONG(c) ((str_t){ \
    .head = (object_t*)&(struct { vtable_t* v; uint32_t l; uint32_t cap; uint64_t h; char a[sizeof(c)]; }) \
        { VTABLE_TAG_CONST(&STR_HEAD_VTABLE), sizeof(c), 0, 0, c }, \
    .meta = STRING_LEN(c), .tail = { 0 } })

// A one-word union member (None = NULL, a tagged Int, an object) placed in a
// two-word union value: word 0 carries it, the payload words are zero.
INLINE str_t str_word(object_t* word) {
    str_t s;
    memset(&s, 0, sizeof s);
    s.head = word;
    return s;
}

// Word 0 of a wide union can also be a SPARE code: a packed-string tagged word
// whose length field is 16..31 — a length no inline string has — so the GC
// ignores it (it is tagged) and a string test that checks the length never
// mistakes it for a string. Code k names a scalar member's TYPE globally (the
// same k in every union — the compiler's table — so values widen between
// unions untouched); its payload is value bytes 8..15. None stays NULL.
#define STR_SPARE_WORD(k) ((object_t*)(uintptr_t)((16 + (k)) * (PTR_TAG_MASK + 1) + PTR_TAG_STRING))
INLINE bool str_word_is_string(object_t* w) {
    uintptr_t r = (uintptr_t)w;
    if ((r & PTR_TAG_MASK) == PTR_TAG_STRING) return ((r & 0xff) >> 3) <= STR_INLINE_MAX;
    return w != NULL && object_is_instance(w, (vtable_t*)&STR_HEAD_VTABLE);
}
// The spare code in word 0, or -1 when it is not one.
INLINE int32_t str_word_code(object_t* w) {
    uintptr_t r = (uintptr_t)w;
    uint32_t len = (uint32_t)(r & 0xff) >> 3;
    return ((r & PTR_TAG_MASK) == PTR_TAG_STRING && len > STR_INLINE_MAX) ? (int32_t)len - 16 : -1;
}
INLINE str_t str_pack_bits(int32_t code, uint64_t bits) {
    str_t s;
    memset(&s, 0, sizeof s);
    s.head = STR_SPARE_WORD(code);
    memcpy((uint8_t*)&s + 8, &bits, sizeof bits);
    return s;
}
INLINE uint64_t str_unpack_bits(str_t s) {
    uint64_t bits;
    memcpy(&bits, (uint8_t*)&s + 8, sizeof bits);
    return bits;
}
INLINE str_t   str_pack_int8(int32_t code, int8_t v)    { return str_pack_bits(code, (uint8_t)v); }
INLINE str_t   str_pack_int16(int32_t code, int16_t v)  { return str_pack_bits(code, (uint16_t)v); }
INLINE str_t   str_pack_int32(int32_t code, int32_t v)  { return str_pack_bits(code, (uint32_t)v); }
INLINE str_t   str_pack_int64(int32_t code, int64_t v)  { return str_pack_bits(code, (uint64_t)v); }
INLINE str_t   str_pack_float32(int32_t code, float v)  { uint32_t b; memcpy(&b, &v, 4); return str_pack_bits(code, b); }
INLINE str_t   str_pack_float64(int32_t code, double v) { uint64_t b; memcpy(&b, &v, 8); return str_pack_bits(code, b); }
INLINE int8_t  str_unpack_int8(str_t s)    { return (int8_t)(uint8_t)str_unpack_bits(s); }
INLINE int16_t str_unpack_int16(str_t s)   { return (int16_t)(uint16_t)str_unpack_bits(s); }
INLINE int32_t str_unpack_int32(str_t s)   { return (int32_t)(uint32_t)str_unpack_bits(s); }
INLINE int64_t str_unpack_int64(str_t s)   { return (int64_t)str_unpack_bits(s); }
INLINE float   str_unpack_float32(str_t s) { uint32_t b = (uint32_t)str_unpack_bits(s); float v; memcpy(&v, &b, 4); return v; }
INLINE double  str_unpack_float64(str_t s) { uint64_t b = str_unpack_bits(s); double v; memcpy(&v, &b, 8); return v; }

// A FUNCTION member of a wide union: word 0 is its environment (the GC word,
// as in fun_t {o, f}) and value bytes 8.. its code pointer. A NULL environment
// cannot be NULL here (that is None): it is spare code 0 instead. Such a union
// has no class members (a bound method's environment IS a class instance), so
// any other untagged, non-string, non-integer word is a function environment.
#define STR_CODE_FUN_NULL_ENV 0
INLINE str_t str_from_fun(fun_t f) {
    str_t s;
    memset(&s, 0, sizeof s);
    s.head = f.o ? (object_t*)f.o : STR_SPARE_WORD(STR_CODE_FUN_NULL_ENV);
    memcpy((uint8_t*)&s + 8, &f.f, sizeof f.f);
    return s;
}
INLINE fun_t str_to_fun(str_t s) {
    fun_t f;
    f.o = str_word_code(s.head) == STR_CODE_FUN_NULL_ENV ? NULL : (void*)s.head;
    memcpy(&f.f, (uint8_t*)&s + 8, sizeof f.f);
    return f;
}
INLINE bool str_word_is_fun(object_t* w) {
    if ((uintptr_t)w & PTR_TAG_MASK) return str_word_code(w) == STR_CODE_FUN_NULL_ENV;
    return w != NULL && !object_is_instance(w, (vtable_t*)&STR_HEAD_VTABLE)
                     && !object_is_instance(w, (vtable_t*)&INTEGER_VTABLE);
}

EXTERN str_t     str_from_bytes(const uint8_t* data, int32_t length);
EXTERN str_t     str_from_cstr(const char* cstr);
// Copy bytes [from, from + n) of `s` to `dst` (the range must lie within s).
EXTERN void      str_copy_range(str_t s, int32_t from, int32_t n, uint8_t* dst);
// Copy all str_length(s) bytes of `s` to `dst`.
EXTERN void      str_copy_bytes(str_t s, uint8_t* dst);
// `s` as a NUL-terminated C string (for fopen, getenv, …): in `buf` when it
// fits, else in a malloc'd block returned through `*heap` for the caller to
// free (NULL otherwise). Embedded NULs are the caller's concern.
EXTERN char*     str_cstr(str_t s, char* buf, int32_t size, char** heap);
// At most size-1 bytes of `s` into `buf`, NUL-terminated (truncating); the
// number of bytes copied.
EXTERN int32_t   str_copy_cstr(str_t s, char* buf, int32_t size);
EXTERN object_t* print_string(object_t* self, str_t s);
// The process arguments and environment (object.c).
EXTERN str_t     sys_argv_at(object_t* self, object_t* o_index);
EXTERN str_t     sys_getenv(object_t* self, str_t name);   // String|None
// This process's private temp folder, created on first call and deleted at
// exit (tempdir.c).
EXTERN str_t     sys_tempdir(object_t* self);               // String|None

// task_str_t: task subtype whose result is a String value, or a union that
// shares its representation (the compiler's "task_str"). result.head sits at
// the offset task_obj_t keeps its object result, so a runtime job embedding a
// task_str_t serves one-word results through word 0 unchanged.
typedef struct {
    vtable_t*               type;
    _Atomic(int32_t)        state;
    int32_t                 thread_id;
    fun_t                   callback;
    _Atomic(struct task_s*) next;
    str_t                   result;
} task_str_t;
_Static_assert(offsetof(task_str_t, result) == offsetof(task_obj_t, result),
               "task_str_t.result.head shares task_obj_t.result's offset");
EXTERN struct task_vtable TASK_STR_VTABLE;
#define obj_task_str ((vtable_t*)&TASK_STR_VTABLE)
EXTERN object_t* task_str_create(object_t* self);
// Appending two INLINE values that still fit inline is pure bit arithmetic:
// canonical zero padding means b's content can be shifted in after a's with
// no masking. Everything else — any heap side, or a result past 15 bytes —
// goes out of line.
EXTERN str_t     str_append_slow(str_t a, str_t b);
INLINE str_t     str_append(str_t a, str_t b) {
#if defined(__SIZEOF_INT128__) && IS_LITTLE_ENDIAN
    if (str_is_inline(a) && str_is_inline(b)) {
        uint32_t la = (uint32_t)str_length(a), lb = (uint32_t)str_length(b);
        if (la + lb <= STR_INLINE_MAX) {
            unsigned __int128 va, vb;
            memcpy(&va, &a, sizeof va);
            memcpy(&vb, &b, sizeof vb);
            va |= (vb >> 8) << (8 * (la + 1));              // b's content after a's
            va = (va & ~(unsigned __int128)0xFF)
               | (unsigned __int128)((la + lb) * (PTR_TAG_MASK + 1) + PTR_TAG_STRING);
            str_t r;
            memcpy(&r, &va, sizeof r);
            return r;
        }
    }
#endif
    return str_append_slow(a, b);
}
EXTERN str_t     str_concat_n(int32_t count, ...);
EXTERN int       str_compare(str_t a, str_t b);
INLINE bool      str_eq(str_t a, str_t b) {
    // The same 16 bytes are the same string: for inline values that is the
    // whole test (canonical by length); for heap values it is the same head,
    // length and tail — the common case of a dict key found by itself.
    if (memcmp(&a, &b, sizeof a) == 0) return true;
    if (str_is_inline(a) || str_is_inline(b)) return false;
    if (str_length(a) != str_length(b)) return false;
    return str_compare(a, b) == 0;
}
INLINE bool      str_lt(str_t a, str_t b) { return str_compare(a, b) < 0; }
INLINE bool      str_gt(str_t a, str_t b) { return str_compare(a, b) > 0; }
INLINE object_t* str_compare_int(str_t a, str_t b) {
    int r = str_compare(a, b);
    return integer_from_int32(r < 0 ? -1 : r > 0 ? 1 : 0);
}
INLINE object_t* str_length_int(str_t s) { return integer_from_int32(str_length(s)); }
// Hashing. The byte stream 8 bytes per multiply, length mixed in, 31 bits,
// never 0 (0 stays the "no hash" sentinel). The fast paths live here, at the
// call site: an INLINE value is its own zero-padded 15 content bytes — two
// words, no loop — and needs no cache (it can never equal a heap string: those
// are all longer); a tail-less HEAP value whose head caches the hash of exactly
// its length is one load and one compare. Everything else: str_hash_heap.
#define STR_HASH_SEED 0x243F6A8885A308D3ull
INLINE uint64_t str_hash_mix(uint64_t h, uint64_t w) {
    h ^= w;
    h *= 0x9E3779B97F4A7C15ull;
    return h ^ (h >> 32);
}
INLINE int32_t str_hash_finish(uint64_t h) {
    h ^= h >> 29;
    h *= 0xBF58476D1CE4E5B9ull;
    h ^= h >> 32;
    uint32_t m = (uint32_t)h & 0x7fffffffu;
    return (int32_t)(m ? m : 1);
}
INLINE uint64_t str_load_le64(const void* p) {
    uint64_t w;
    memcpy(&w, p, sizeof w);
#if !IS_LITTLE_ENDIAN
    w = __builtin_bswap64(w);
#endif
    return w;
}
EXTERN int32_t   str_hash_heap(str_t s);
INLINE int32_t   str_hash(str_t s) {
    if (str_is_inline(s)) {
        // The same words the heap path hashes: content bytes 0..7, 8..14.
        uint64_t h = STR_HASH_SEED ^ (uint64_t)str_length(s);
#if IS_LITTLE_ENDIAN
        const uint8_t* b = (const uint8_t*)&s;           // byte 0 is the tag
        h = str_hash_mix(h, str_load_le64(b + 1));
        h = str_hash_mix(h, str_load_le64(b + 8) >> 8);
#else
        uint8_t c[16] = { 0 };                           // gather around the tag byte
        for (int i = 0; i < STR_INLINE_MAX; i++) c[i] = ((const uint8_t*)&s)[str_inline_off(i)];
        h = str_hash_mix(h, str_load_le64(c));
        h = str_hash_mix(h, str_load_le64(c + 8));
#endif
        return str_hash_finish(h);
    }
    if ((s.meta >> STR_META_LEN_BITS) == 0) {
        uint64_t k = atomic_load_explicit(&((str_head_t*)s.head)->hash, memory_order_relaxed);
        if ((uint32_t)(k >> 32) == (s.meta & STR_META_LEN_MASK))
            return (int32_t)(uint32_t)k;
    }
    return str_hash_heap(s);
}
EXTERN str_t     str_slice(str_t s, object_t* start, object_t* end);
// Unsigned byte value [0..255], or -1 when the index is out of range. Inline:
// parsers call it per byte.
INLINE int32_t   str_byte_at(str_t s, object_t* o_index) {
    int overflow = 0;
    int32_t i = int32_from_integer_with_overflow(o_index, &overflow);
    if (overflow || i < 0 || i >= str_length(s)) return -1;
    // Each read carries its own bound (redundant after the length check, but
    // visible to the compiler once a constant index is propagated in).
    if (str_is_inline(s))
        return (uint32_t)i < STR_INLINE_MAX ? ((const uint8_t*)&s)[str_inline_off(i)] : -1;
    uint32_t hl = s.meta & STR_META_LEN_MASK;
    if ((uint32_t)i < hl)
        return ((const uint8_t*)s.head + offsetof(str_head_t, array))[i];
    uint32_t t = (uint32_t)i - hl;
    return t < STR_TAIL_MAX ? str_tail_bytes(&s)[t] : -1;
}
EXTERN object_t* str_find_byte(str_t s, int32_t byte, object_t* from);
EXTERN object_t* str_index_of(str_t s, str_t needle, object_t* from);
EXTERN object_t* str_find_any(str_t s, str_t accept, object_t* from);
EXTERN object_t* str_skip_any(str_t s, str_t accept, object_t* from);
EXTERN object_t* str_parse_int(str_t s);
EXTERN int32_t   str_codepoint_at(str_t s, object_t* from);
EXTERN object_t* str_codepoint_count(str_t s);
EXTERN bool      str_valid_utf8(str_t s);
EXTERN str_t     str_ascii(int32_t byte);
EXTERN str_t     str_wchar(int32_t codepoint);
EXTERN str_t     str_from_int8(int8_t v);
EXTERN str_t     str_from_int16(int16_t v);
EXTERN str_t     str_from_int32(int32_t v);
EXTERN str_t     str_from_int64(int64_t v);
EXTERN str_t     str_from_float32(float v);
EXTERN str_t     str_from_float64(double v);
EXTERN double    str_parse_float64(str_t s);
EXTERN float     str_parse_float32(str_t s);

EXTERN int32_t float64_hash(double f);
INLINE bool yafl_ref_eq(object_t* a, object_t* b) { return a == b; }
// The value-representation half of yafl_hash_store: no slot to write, but
// the 0-is-reserved contract still holds, so a computed 0 becomes 1.
INLINE int32_t yafl_hash_norm(int32_t h) { return h == 0 ? 1 : h; }
// SAME — is this thing EXACTLY the other thing: bit-identical representation.
// One macro covers every case: on a pointer variable memcmp compares the
// pointer words (reference equality), on a scalar the value, on a value
// struct the bytes — embedded references compare as pointer words in place.
// Struct padding can only cause a false NEGATIVE (one avoidable allocation),
// never a wrong answer.
// VARIADIC in the second operand: a value-representation enum's field read
// lowers to a COMPOUND LITERAL — `(struct_anon_1_t){._s0 = x, ._tag = y}` —
// whose braces contain commas the preprocessor splits on, so a two-parameter
// macro sees three arguments and fails to expand ("too many arguments
// provided to function-like macro invocation"). __VA_ARGS__ absorbs them and
// the extra parentheses make the reconstructed compound literal addressable.
// Only reachable once `with` is used on a value enum — the AST rewrites use
// boxed nodes, so this went unexercised until the IR rewrites adopted it.
#define yafl_same(a, ...) (memcmp(&(a), &((__VA_ARGS__)), sizeof(a)) == 0)
EXTERN int32_t yafl_hash_peek(object_t* v);
EXTERN int32_t yafl_hash_store(object_t* v, int32_t h);


/**********************************************************
 *****************************
 *************
 *****
 **
 *                   I/O
 **
 *****
 *************
 *****************************
 **********************************************************/

EXPORT object_t* io_stdin (object_t* self);
EXPORT object_t* io_stdout(object_t* self);
EXPORT object_t* io_stderr(object_t* self);
EXPORT object_t* io_create    (object_t* self, str_t path);
EXPORT object_t* io_open_read (object_t* self, str_t path);
EXPORT object_t* io_open_write(object_t* self, str_t path, int8_t truncate);  // YAFL Bool ABI is int8_t
EXPORT str_t     io_read (object_t* self, object_t* length);   // String|Int|None
EXPORT object_t* io_write(object_t* self, str_t data);
EXPORT object_t* io_close(object_t* self);

// Filesystem metadata.  Both ops dispatch through the IO threadpool so
// the blocking syscalls (access/stat) never run on a worker thread.
//
// fs_exists returns a tagged-task wrapper whose result is a packed Int
// (0 for false, 1 for true).  Permission errors and any other failure
// map to false — exists never surfaces an IOError.  Use fs_stat when
// you want errors visible.
//
// fs_stat returns a tagged-task wrapper whose result is either a
// _FileInfo handle (on success) or a packed Int holding `-errno` on
// failure.  The five accessors below read individual fields from a
// successfully-resolved _FileInfo; all are sync (no task dispatch).
EXPORT object_t* fs_exists   (object_t* self, str_t path);
EXPORT object_t* fs_stat     (object_t* self, str_t path);
// fs_mkdir creates ONE directory and resolves to a packed Int: 0 on success
// (an already-existing directory counts as success, as `mkdir -p` does) or
// -errno. Creating parents is the caller's loop over the path components.
EXPORT object_t* fs_mkdir    (object_t* self, str_t path);
EXPORT object_t* fs_fi_size  (object_t* self);
EXPORT object_t* fs_fi_mtime (object_t* self);
EXPORT object_t* fs_fi_isdir (object_t* self);
EXPORT object_t* fs_fi_isreg (object_t* self);
EXPORT object_t* fs_fi_mode  (object_t* self);

// Directory cursor.  open returns a tagged-task wrapper resolving to
// either a _Dir handle (success) or a packed Int holding -errno.  next
// resolves to String (next entry name), None (end of stream), or Int
// (-errno).  close resolves to None (success) or Int (-errno).
EXPORT object_t* fs_open_dir (object_t* self, str_t path);
EXPORT str_t     fs_dir_next (object_t* self);   // String|Int|None
EXPORT object_t* fs_dir_close(object_t* self);


