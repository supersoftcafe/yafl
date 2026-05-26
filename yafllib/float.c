
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
EXPORT double float64_from_integer(object_t* i) {
    int overflow = 0;
    int32_t lo = int32_from_integer_with_overflow(i, &overflow);
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
EXPORT object_t* integer_from_float64(double f) {
    if (!isfinite(f)) abort_on_maths_error();

    f = trunc(f);
    if (f >= (double)INT32_MIN && f <= (double)INT32_MAX) {
        return integer_from_int32((int32_t)f);
    }

    int neg = f < 0;
    if (neg) f = -f;

    // Build bigint by chunks of 2^30 (always fits int32_t).
    const double radix = (double)(1 << 30);
    object_t* acc = integer_from_int32(0);
    object_t* base = integer_from_int32(1 << 30);

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
        acc = integer_add_full(acc, integer_from_int32(digits[k]));
    }
    if (neg) acc = integer_sub_full(integer_from_int32(0), acc);
    return acc;
}


// Render a double as a YAFL String. %.17g gives a round-trip-safe form.
EXPORT object_t* string_from_float64(double f) {
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "%.17g", f);
    if (n < 0) n = 0;
    if (n > (int)sizeof(buf) - 1) n = (int)sizeof(buf) - 1;
    return string_from_bytes((uint8_t*)buf, n);
}


// Convert double → fixed-width int, truncating toward zero and clamping on
// overflow. NaN → 0; +inf or values ≥ 2^(N-1) → INT<N>_MAX; -inf or values
// < -2^(N-1) → INT<N>_MIN. Boundary constants use the exact float that's
// one past the representable max — this avoids the `(int)2.147483648e9`
// UB that bites a naive cast and gives every input a defined target.
EXPORT int8_t int8_from_float64(double f) {
    if (f != f) return 0;
    if (f >=  128.0)  return INT8_MAX;
    if (f <  -128.0)  return INT8_MIN;
    return (int8_t)trunc(f);
}
EXPORT int16_t int16_from_float64(double f) {
    if (f != f) return 0;
    if (f >=  32768.0)  return INT16_MAX;
    if (f <  -32768.0)  return INT16_MIN;
    return (int16_t)trunc(f);
}
EXPORT int32_t int32_from_float64(double f) {
    if (f != f) return 0;
    if (f >=  2147483648.0) return INT32_MAX;
    if (f <  -2147483648.0) return INT32_MIN;
    return (int32_t)trunc(f);
}
// 9223372036854775808.0 is the exact float for 2^63 — INT64_MAX rounds up
// to it as a double, so we have to compare `>=` rather than `>`.
EXPORT int64_t int64_from_float64(double f) {
    if (f != f) return 0;
    if (f >=  9223372036854775808.0) return INT64_MAX;
    if (f <  -9223372036854775808.0) return INT64_MIN;
    return (int64_t)trunc(f);
}

// Same shape as the float64 versions but starting from float. Boundary
// thresholds use float literals so the comparison happens in float, not
// double — keeps the clamp exact for values right at ±2^(N-1).
EXPORT int8_t int8_from_float32(float f) {
    if (f != f) return 0;
    if (f >=  128.0f)  return INT8_MAX;
    if (f <  -128.0f)  return INT8_MIN;
    return (int8_t)truncf(f);
}
EXPORT int16_t int16_from_float32(float f) {
    if (f != f) return 0;
    if (f >=  32768.0f)  return INT16_MAX;
    if (f <  -32768.0f)  return INT16_MIN;
    return (int16_t)truncf(f);
}
// 32-bit float has 24-bit mantissa — many int32 values aren't representable,
// but the clamp still respects exact boundary values (±2^31 are themselves
// representable in binary32).
EXPORT int32_t int32_from_float32(float f) {
    if (f != f) return 0;
    if (f >=  2147483648.0f) return INT32_MAX;
    if (f <  -2147483648.0f) return INT32_MIN;
    return (int32_t)truncf(f);
}
EXPORT int64_t int64_from_float32(float f) {
    if (f != f) return 0;
    if (f >=  9223372036854775808.0f) return INT64_MAX;
    if (f <  -9223372036854775808.0f) return INT64_MIN;
    return (int64_t)truncf(f);
}


// Parse a YAFL String into a double. On failure (empty, leftover chars, etc.)
// returns NaN — callers wrap into Float|None by checking float64_is_nan.
EXPORT double float64_parse_or_nan(object_t* self) {
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


/**********************************************************
 *
 *                      Float32
 *
 * Single-precision counterparts of the Float64 routines.
 * Math/compare/short conversions live as INLINE functions in
 * yafl.h; this file holds the bigint conversions, parsing,
 * formatting, and hashing that are too large to inline.
 *
 **********************************************************/


// Bigint → float. Same shape as float64_from_integer; we route through the
// float64 path to share the limb-walking and let the C compiler narrow at
// the return. Loses precision beyond 2^24 (IEEE-754 binary32).
EXPORT float float32_from_integer(object_t* i) {
    return (float)float64_from_integer(i);
}


// Float32 → bigint, truncating toward zero. NaN/inf abort. Reuses the
// float64 implementation so behaviour matches across both widths.
EXPORT object_t* integer_from_float32(float f) {
    return integer_from_float64((double)f);
}


// Float32 → fixed-width int conversions live with the other intN_from_float32
// helpers above; no duplicate definition here.


// Render float32 as a string. %.9g gives a round-trip-safe form for binary32.
EXPORT object_t* string_from_float32(float f) {
    char buf[24];
    int n = snprintf(buf, sizeof(buf), "%.9g", (double)f);
    if (n < 0) n = 0;
    if (n > (int)sizeof(buf) - 1) n = (int)sizeof(buf) - 1;
    return string_from_bytes((uint8_t*)buf, n);
}


// Parse a YAFL String into a float. Same contract as float64_parse_or_nan:
// returns NaN on any failure; callers wrap into Float32|None by checking
// float32_is_nan. Uses strtof so the result is the correctly-rounded binary32.
EXPORT float float32_parse_or_nan(object_t* self) {
    intptr_t local; int32_t len;
    char* src = string_to_cstr(self, &local, &len);
    if (len <= 0) return NAN;
    char* end = NULL;
    float v = strtof(src, &end);
    if (end != src + len) return NAN;
    return v;
}
