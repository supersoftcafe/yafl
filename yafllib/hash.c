
#include "yafl.h"
#include <string.h>


EXPORT int32_t string_hash(object_t* s) {
    // Lazy cache: heap strings carry the hash in the header, 0 = not yet
    // computed. A string hash is NEVER 0 (masked-zero maps to 1 below), so
    // 0 is a true reserved sentinel — in the header cache and for any
    // caller wanting in-band "no hash yet". Packed short strings have no
    // header and are at most a word of bytes — computing beats any cache.
    int is_heap = !PTR_IS_STRING(s);
    if (is_heap) {
        uint32_t cached = ((string_t*)s)->hash;
        if (cached) return (int32_t)cached;
    }
    intptr_t buf;
    int32_t len;
    const char* data = string_to_cstr(s, &buf, &len);
    // FNV-1a 32-bit
    uint32_t h = 2166136261u;
    for (int32_t i = 0; i < len; i++) {
        h ^= (uint8_t)data[i];
        h *= 16777619u;
    }
    uint32_t masked = h & 0x7fffffffu;
    if (masked == 0) masked = 1;  // reserve 0: the never-0 contract
    if (is_heap)
        // Plain idempotent store on an immutable object: a racing writer
        // stores the same value; a store lost to a compaction copy costs
        // one recompute.
        ((string_t*)s)->hash = masked;
    return (int32_t)masked;
}


EXPORT int32_t float64_hash(double f) {
    // -0.0 == +0.0 but their bits differ; normalise to +0.0 so equal floats hash equal.
    if (f == 0.0) f = 0.0;
    uint64_t bits;
    memcpy(&bits, &f, sizeof(bits));
    // XOR-fold to 32 bits
    uint32_t h = (uint32_t)(bits ^ (bits >> 32));
    return (int32_t)(h & 0x7fffffffu);
}


EXPORT int32_t float32_hash(float f) {
    if (f == 0.0f) f = 0.0f;  // collapse -0.0 / +0.0 — see float64_hash
    uint32_t bits;
    memcpy(&bits, &f, sizeof(bits));
    return (int32_t)(bits & 0x7fffffffu);
}

// ── the [hashed] slot ────────────────────────────────────────────────────────
// A `[hashed]` enum's every leaf carries a hidden int32 `$hash` slot placed
// DIRECTLY AFTER the vtable pointer — a fixed offset shared by all [hashed]
// types, which is what lets these two functions exist once instead of per
// type. 0 means "not yet computed"; a computed 0 is stored and returned as 1,
// deterministically (the same reservation string_hash documents).
//
// The store is a plain racy write, and that is deliberate: the value is a
// deterministic function of immutable content, so two threads racing write
// the same word, and a write lost to a concurrent compaction move just means
// a later recompute. No CAS, no write barrier (scalar), and NOT [mutable] —
// pinning every hashed object from compaction would cost far more than the
// occasional recompute.
int32_t yafl_hash_peek(object_t* v) {
    return *(int32_t*)((char*)v + sizeof(vtable_t*));
}

int32_t yafl_hash_store(object_t* v, int32_t h) {
    if (h == 0) h = 1;
    *(int32_t*)((char*)v + sizeof(vtable_t*)) = h;
    return h;
}
