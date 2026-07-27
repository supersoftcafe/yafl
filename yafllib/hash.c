
#include "yafl.h"
#include <string.h>


EXPORT object_t* string_hash(object_t* s) {
    // Lazy cache: heap strings carry the masked hash in the header (0 =
    // uncomputed; a string that genuinely hashes to 0 is recomputed each
    // call, the Java trade). Packed short strings have no header and are
    // at most a word of bytes — computing is cheaper than any cache.
    int is_heap = !PTR_IS_STRING(s);
    if (is_heap) {
        uint32_t cached = ((string_t*)s)->hash;
        if (cached) return integer_from_int32((int32_t)cached);
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
    if (is_heap)
        // Plain idempotent store on an immutable object: a racing writer
        // stores the same value; a store lost to a compaction copy costs
        // one recompute.
        ((string_t*)s)->hash = masked;
    return integer_from_int32((int32_t)masked);
}


EXPORT object_t* float64_hash(double f) {
    // -0.0 == +0.0 but their bits differ; normalise to +0.0 so equal floats hash equal.
    if (f == 0.0) f = 0.0;
    uint64_t bits;
    memcpy(&bits, &f, sizeof(bits));
    // XOR-fold to 32 bits
    uint32_t h = (uint32_t)(bits ^ (bits >> 32));
    return integer_from_int32((int32_t)(h & 0x7fffffffu));
}


EXPORT object_t* float32_hash(float f) {
    if (f == 0.0f) f = 0.0f;  // collapse -0.0 / +0.0 — see float64_hash
    uint32_t bits;
    memcpy(&bits, &f, sizeof(bits));
    return integer_from_int32((int32_t)(bits & 0x7fffffffu));
}
