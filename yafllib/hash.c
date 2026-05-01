
#include "yafl.h"
#include <string.h>


EXPORT object_t* string_hash(object_t* s) {
    intptr_t buf;
    int32_t len;
    const char* data = string_to_cstr(s, &buf, &len);
    // FNV-1a 32-bit
    uint32_t h = 2166136261u;
    for (int32_t i = 0; i < len; i++) {
        h ^= (uint8_t)data[i];
        h *= 16777619u;
    }
    return integer_create_from_int32((int32_t)(h & 0x7fffffffu));
}


EXPORT object_t* float64_hash(double f) {
    // -0.0 == +0.0 but their bits differ; normalise to +0.0 so equal floats hash equal.
    if (f == 0.0) f = 0.0;
    uint64_t bits;
    memcpy(&bits, &f, sizeof(bits));
    // XOR-fold to 32 bits
    uint32_t h = (uint32_t)(bits ^ (bits >> 32));
    return integer_create_from_int32((int32_t)(h & 0x7fffffffu));
}
