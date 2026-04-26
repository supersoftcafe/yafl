
#include "yafl.h"


/**********************************************************
 *
 *                       Float
 *
 * Unboxed primitive doubles. The trivial arithmetic and
 * comparison ops live as INLINE functions in yafl.h; this
 * file holds the heavier ones (bigint conversions, parsing,
 * formatting) that are too large to inline.
 *
 **********************************************************/


// Convert bigint (object_t*) → double. Loses precision beyond 2^53 — that's
// inherent to IEEE-754 binary64.
EXPORT double float_from_int(object_t* i) {
    int overflow = 0;
    int32_t lo = integer_to_int32_with_overflow(i, &overflow);
    if (!overflow) return (double)lo;

    // Fall back to a generic conversion for bigints that don't fit int32.
    // Walk the limbs from high to low, accumulating in double. Each limb is
    // sizeof(intptr_t)*8 bits; on 64-bit that's 64 bits per limb.
    integer_t* a = (integer_t*)i;
    double result = 0.0;
    double base = ldexp(1.0, (int)(sizeof(intptr_t) * 8));
    for (uint32_t k = a->length; k-- > 0; ) {
        result = result * base + (double)a->array[k];
    }
    return a->sign ? -result : result;
}


// Convert double → bigint, truncating toward zero. NaN/inf abort.
EXPORT object_t* int_from_float(double f) {
    if (!isfinite(f)) abort_on_maths_error();

    f = trunc(f);
    if (f >= (double)INT32_MIN && f <= (double)INT32_MAX) {
        return integer_create_from_int32((int32_t)f);
    }

    int neg = f < 0;
    if (neg) f = -f;

    // Build bigint by chunks of 2^30 (always fits int32_t).
    const double radix = (double)(1 << 30);
    object_t* acc = integer_create_from_int32(0);
    object_t* base = integer_create_from_int32(1 << 30);

    // Split f into base-radix digits, most significant first.
    int32_t digits[16];  // 2^(30*16) > 10^144 — far more than IEEE-754 can represent.
    int n = 0;
    while (f >= 1.0 && n < (int)(sizeof(digits)/sizeof(digits[0]))) {
        double chunk = fmod(f, radix);
        digits[n++] = (int32_t)chunk;
        f = trunc(f / radix);
    }

    for (int k = n; k-- > 0; ) {
        acc = integer_mul(acc, base);
        acc = integer_add_full(acc, integer_create_from_int32(digits[k]));
    }
    if (neg) acc = integer_sub_full(integer_create_from_int32(0), acc);
    return acc;
}


// Render a double as a YAFL String. %.17g gives a round-trip-safe form.
EXPORT object_t* string_from_float(double f) {
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "%.17g", f);
    if (n < 0) n = 0;
    if (n > (int)sizeof(buf) - 1) n = (int)sizeof(buf) - 1;
    return string_from_bytes((uint8_t*)buf, n);
}


// Parse a YAFL String into a double. On failure (empty, leftover chars, etc.)
// returns NaN — callers wrap into Float|None by checking float_is_nan.
EXPORT double float_parse_or_nan(object_t* self) {
    intptr_t local; int32_t len;
    char* src = string_to_cstr(self, &local, &len);

    if (len <= 0) return NAN;

    // strtod requires NUL-termination. Heap strings are NUL-terminated already
    // (string_to_cstr returns the raw array, and string.c always appends '\0'
    // past the length). Packed strings sit in `local`, which is at least
    // sizeof(intptr_t) bytes wide and zero-fills its unused tail bytes — so it
    // is also NUL-terminated within the buffer for any len < sizeof(intptr_t).
    char* end = NULL;
    double v = strtod(src, &end);
    if (end != src + len) return NAN;
    return v;
}
