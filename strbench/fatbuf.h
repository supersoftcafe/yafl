// Growable head buffer shared by the fat-string prototypes (fatstr32.h,
// fatstr16.h). Layout L1:
//
//   length field = used + 1   (the string_t convention: bytes + NUL)
//   hash slot    = capacity + 1, on a buffer vtable whose array_cap_offset
//                  points at it
//
// `used` is the high-water mark: the largest head_len any value over this
// buffer has claimed; bytes [0, used) never change again. The GC sizes the
// object by `length`, so compaction copies only the used bytes, and the
// runtime's capacity reset (array_cap_offset) makes the copy's capacity equal
// its length: a moved buffer never extends in place.
//
// A value may extend in place only when it owns the end of the buffer
// (head_len == used) and capacity suffices — checked under the object PIN,
// which is also the mutex compaction honours (the runtime re-reads the size
// under the pin, since `length` grows here). Everything else copies.
#ifndef FATBUF_H
#define FATBUF_H

#include "yafl.h"
#include <string.h>

#if !IS_LITTLE_ENDIAN
#error "prototype assumes little-endian"
#endif

#ifdef FAT_STATS
static long fs_inplace, fs_copy; static long long fs_bytes_inplace, fs_bytes_copy;
#define FS(x) (x)
#else
#define FS(x) ((void)0)
#endif

// Only buffers get the capacity reset (plain strings keep their hash cache
// in that slot). Implements STRING_VTABLE for match dispatch.
static vtable_t fat_buf_vt = {
    .object_size = offsetof(string_t, array),
    .array_el_size = sizeof(uint8_t),
    .array_len_offset = offsetof(string_t, length),
    .array_cap_offset = offsetof(string_t, hash),
    .name = "fat_buffer",
    .implements_array = VTABLE_IMPLEMENTS(1, (vtable_t*)&STRING_VTABLE),
};

#define BUF_LEN(b)   (((string_t*)(b))->length)
#define BUF_HASH(b)  (((string_t*)(b))->hash)
#define BUF_BYTES(b) (((string_t*)(b))->array)

static inline uint32_t buf_used(object_t* b) { return BUF_LEN(b) - 1; }
static inline uint32_t buf_cap(object_t* b)  { return BUF_HASH(b) - 1; }

// Caller holds the pin, or the buffer is not yet published.
static inline void buf_set_used(object_t* b, uint32_t used) {
    BUF_BYTES(b)[used] = 0;
    BUF_LEN(b) = used + 1;
}

static inline bool buf_in_heap(object_t* o) {
    return (uintptr_t)((char*)o - _memory_heap_base) < _memory_heap_bytes;
}

// Fresh buffer holding head[0,hl) ++ a[0,na) ++ b[0,nb): 2x growth,
// perfect-filled to the allocator granule.
static object_t* buf_new(const uint8_t* head, uint32_t hl,
                         const uint8_t* a, uint32_t na,
                         const uint8_t* b, uint32_t nb) {
    int64_t want = (int64_t)hl + na + nb;
    int64_t overhead = (int64_t)offsetof(string_t, array) + 1;
    int64_t total = want + want + overhead;
    total = (total + GC_ALLOC_GRANULE - 1) / GC_ALLOC_GRANULE * GC_ALLOC_GRANULE;
    int64_t cap = total - overhead;
    if (cap > INT32_MAX) __abort_on_overflow();
    object_t* buf = (object_t*)array_create(&fat_buf_vt, (int32_t)cap + 1);
    memcpy(BUF_BYTES(buf), head, hl);
    memcpy(BUF_BYTES(buf) + hl, a, na);
    memcpy(BUF_BYTES(buf) + hl + na, b, nb);
    BUF_HASH(buf) = (uint32_t)cap + 1;
    buf_set_used(buf, (uint32_t)want);
    return buf;
}

// Head holding h[0,hl) ++ a ++ b: `h` itself when this value owns the end of
// it and it has room, else a copy. Pin FIRST, then read used/capacity.
static inline object_t* buf_append(object_t* h, uint32_t hl,
                                   const uint8_t* a, uint32_t na,
                                   const uint8_t* b, uint32_t nb) {
    uint32_t extra = na + nb;
    if (h != NULL && buf_in_heap(h) && object_try_pin(h)) {
        if (buf_used(h) == hl && buf_cap(h) - hl >= extra) {
            uint8_t* dst = BUF_BYTES(h) + hl;
            memcpy(dst, a, na);
            memcpy(dst + na, b, nb);
            buf_set_used(h, hl + extra);   // plain stores: we hold the pin
            object_unpin(h);               // release: bytes + length visible
            FS((fs_inplace++, fs_bytes_inplace += extra));
            return h;
        }
        object_unpin(h);
    }
    // Not the owner, no room, or couldn't pin: copy. A forwarded `h` is a
    // stale but byte-identical copy of [0, hl), so reading it is fine.
    FS((fs_copy++, fs_bytes_copy += (long long)hl + extra));
    return buf_new(h ? BUF_BYTES(h) : NULL, hl, a, na, b, nb);
}

static inline uint32_t fnv_bytes(uint32_t h, const uint8_t* p, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { h ^= p[i]; h *= 16777619u; }
    return h;
}

#endif
