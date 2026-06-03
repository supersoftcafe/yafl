
#include "yafl.h"


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

#include <alloca.h>

EXPORT void abort_on_maths_error() {
    log_error_and_exit("Division by zero", stderr);
}

VTABLE_DECLARE_STRUCT(integer_vtable, 16);
EXPORT struct integer_vtable INTEGER_VTABLE = {
    .object_size = offsetof(integer_t, array[0]),
    .array_el_size = sizeof(intptr_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(integer_t, length),
    .name = "integer",
    .implements_array = VTABLE_IMPLEMENTS(0),
};

static integer_t* _integer_allocate(uint32_t length) {
    return (integer_t*)array_create((vtable_t*)&INTEGER_VTABLE, length);
}

#define _TAG_MASK PTR_TAG_INTEGER
#define _IS_LITERAL(x) (((intptr_t)(x)) & PTR_TAG_INTEGER)
#define _UNTAG_LITERAL(x) ((intptr_t)(x) >> 2)
#define _TAG_LITERAL(n) ((integer_t*)(((intptr_t)(n) << 2) | PTR_TAG_INTEGER))

// Portable limits
#if WORD_SIZE == 64
    #define _MAX_LITERAL_SHIFT 62
    typedef __int128_t dword_t;
    typedef __uint128_t udword_t;
#elif WORD_SIZE == 32
    #define _MAX_LITERAL_SHIFT 30
    typedef int64_t dword_t;
    typedef uint64_t udword_t;
#else
    #error "Unsupported WORD_SIZE"
#endif

// The `sign` field is a boolean: 0 = positive, 1 = negative. The literal
// macros (INTEGER_LITERAL_*) and the multiplication's `sign ^ sign` rely on
// this. Previously _sign_of returned +1/-1, which broke cross-form equality
// (a heap bigint from this function with sign=+1 compared unequal to a
// literal-form bigint with sign=0). Use the boolean form consistently.
static inline int32_t _sign_of(intptr_t x) {
    return x < 0 ? 1 : 0;
}

static inline uintptr_t _abs_val(intptr_t x) {
    return x < 0 ? -x : x;
}

#define _PROMOTE_LITERAL(name, literal)\
        integer_t* name;\
        if (!_IS_LITERAL(literal)) {\
            name = (integer_t*)literal;\
        } else {\
            name = alloca(offsetof(integer_t, array[1]));\
            name->sign = _sign_of(_UNTAG_LITERAL(literal));\
            name->length = 1;\
            name->array[0] = _abs_val(_UNTAG_LITERAL(literal));\
        }

static int _compare_abs(integer_t* a, integer_t* b) {
    if (a->length != b->length) {
        return a->length > b->length ? 1 : -1;
    }

    for (uint32_t i = a->length; i-- > 0; ) {
        if (a->array[i] != b->array[i]) {
            return a->array[i] > b->array[i] ? 1 : -1;
        }
    }

    return 0;
}

EXTERN int32_t integer_cmp(object_t* a, object_t* b) {
    if (_IS_LITERAL(a) && _IS_LITERAL(b)) {
        intptr_t av = (intptr_t)a;
        intptr_t bv = (intptr_t)b;
        if (av < bv) return -1;
        if (av > bv) return 1;
        return 0;
    }

    _PROMOTE_LITERAL(ha, a)
    _PROMOTE_LITERAL(hb, b)

    // Under sign=0/1 (pos/neg) convention: larger sign field ⇒ more negative.
    if (ha->sign > hb->sign) return -1;
    if (ha->sign < hb->sign) return 1;

    int32_t cmp = _compare_abs(ha, hb);

    return ha->sign ? -cmp : cmp;
}

static integer_t* _integer_from_intptr(intptr_t literal) {
    if (literal < INTPTR_MIN/4 || literal > INTPTR_MAX/4) {
        integer_t* r = _integer_allocate(1);
        r->sign = _sign_of(literal);
        r->array[0] = _abs_val(literal);
        return r;
    } else {
        return _TAG_LITERAL(literal);
    }
}

static integer_t* _normalize_integer(integer_t* result) {
    // A tagged literal is already canonical — and has no heap fields to read.
    // `_divide_abs` hands back tagged 0/1 for its early-exit cases, so the
    // div/rem callers can pass one straight in.
    if (_IS_LITERAL(result)) {
        return result;
    }
    // Trim trailing zeros
    while (result->length > 1 && result->array[result->length-1] == 0) {
        result->length -= 1;
    }

    // If the result can be a literal, convert it to a literal
    if (result->length == 1 && result->array[0] <= UINTPTR_MAX/4) {
        if (!result->sign || result->array[0] < UINTPTR_MAX/4) {
            return _TAG_LITERAL(result->sign ? -(intptr_t)result->array[0] : (intptr_t)result->array[0]);
        }
    }

    return result;
}

EXPORT object_t* integer_from_int32(int32_t value) {
    return (object_t*)_integer_from_intptr(value);
}

EXPORT object_t* integer_from_int32_noalloc(int32_t value) {
    intptr_t v = (intptr_t)value;
    if (v < INTPTR_MIN/4 || v > INTPTR_MAX/4) {
        log_error_and_exit("integer_from_int32_noalloc: value out of tagged range", stderr);
    }
    return (object_t*)_TAG_LITERAL(v);
}

EXPORT int32_t int32_from_integer(object_t* self) {
    int overflow;
    return int32_from_integer_with_overflow(self, &overflow);
}

// Wrap-on-overflow Int → Int<N>. Keeps the low N bits of the two's-complement
// value (matches Java's `(int) longValue`, Kotlin's `.toInt()`, BigInteger.intValue()).
// Distinct from int<N>_from_integer: that one signals overflow via an out-param
// so callers can fall back to bigint paths; these are the user-facing truncating
// casts.
//
// Implementation: route through int64 to get the low 64 bits, then narrow.
// `int64_from_integer_truncate` is the source of truth — the smaller widths
// just chop further. Avoids per-width sign-bit twiddling.
EXPORT int64_t int64_from_integer_truncate(object_t* self) {
    if (PTR_IS_INTEGER(self)) {
        // Tagged integers hold a 2-bit-shifted intptr_t; sign-extend into 64.
        return (int64_t)((intptr_t)self >> 2);
    }
    integer_t* a = (integer_t*)self;
    // On 64-bit hosts each limb is 64 bits → low 64 bits are array[0].
    // On 32-bit hosts each limb is 32 bits → low 64 bits = array[0] | array[1] << 32.
#if WORD_SIZE == 64
    uint64_t lo = (uint64_t)a->array[0];
#else
    uint64_t lo = (uint64_t)(uint32_t)a->array[0];
    if (a->length > 1) {
        lo |= ((uint64_t)(uint32_t)a->array[1]) << 32;
    }
#endif
    return a->sign ? (int64_t)(0ull - lo) : (int64_t)lo;
}

EXPORT int32_t int32_from_integer_truncate(object_t* self) {
    return (int32_t)int64_from_integer_truncate(self);
}
EXPORT int16_t int16_from_integer_truncate(object_t* self) {
    return (int16_t)int64_from_integer_truncate(self);
}
EXPORT int8_t int8_from_integer_truncate(object_t* self) {
    return (int8_t)int64_from_integer_truncate(self);
}

// Bigint creation from each fixed width. Int8/Int16 widen to int32 first
// (always fits the tagged path on any host). Int64 needs the full word-size
// branching because on 32-bit hosts values past 2^30 need a 2-limb heap object.
EXPORT object_t* integer_from_int8(int8_t v) {
    return integer_from_int32((int32_t)v);
}
EXPORT object_t* integer_from_int16(int16_t v) {
    return integer_from_int32((int32_t)v);
}
EXPORT object_t* integer_from_int64(int64_t v) {
#if WORD_SIZE == 64
    // On 64-bit hosts an int64 always fits in an intptr_t; the tagged-pointer
    // path handles up to ±(INTPTR_MAX/4). Larger magnitudes spill to a 1-limb
    // bigint with the sign held separately.
    return (object_t*)_integer_from_intptr((intptr_t)v);
#else
    // 32-bit host: values in tagged range (±2^30-ish) fit a literal; otherwise
    // build a 2-limb bigint by hand, magnitude in unsigned 64-bit.
    if (v >= (int64_t)(INTPTR_MIN/4) && v <= (int64_t)(INTPTR_MAX/4)) {
        return (object_t*)_TAG_LITERAL((intptr_t)v);
    }
    int sign = v < 0;
    uint64_t mag = sign ? (uint64_t)(0ull - (uint64_t)v) : (uint64_t)v;
    uint32_t hi = (uint32_t)(mag >> 32);
    integer_t* r = _integer_allocate(hi ? 2 : 1);
    r->sign = sign;
    r->array[0] = (uintptr_t)(uint32_t)mag;
    if (hi) r->array[1] = (uintptr_t)hi;
    return (object_t*)r;
#endif
}

// Decimal render of fixed-width ints. Max width across all of these is
// INT64_MIN's 20 bytes ("-9223372036854775808" + NUL).
EXPORT object_t* string_from_int8(int8_t v) {
    char buf[8];
    int n = snprintf(buf, sizeof(buf), "%d", (int)v);
    if (n < 0) n = 0;
    return string_from_bytes((uint8_t*)buf, n);
}
EXPORT object_t* string_from_int16(int16_t v) {
    char buf[8];
    int n = snprintf(buf, sizeof(buf), "%d", (int)v);
    if (n < 0) n = 0;
    return string_from_bytes((uint8_t*)buf, n);
}
EXPORT object_t* string_from_int32(int32_t value) {
    char buf[16];
    int n = snprintf(buf, sizeof(buf), "%d", value);
    if (n < 0) n = 0;
    return string_from_bytes((uint8_t*)buf, n);
}
EXPORT object_t* string_from_int64(int64_t v) {
    char buf[24];
    int n = snprintf(buf, sizeof(buf), "%lld", (long long)v);
    if (n < 0) n = 0;
    return string_from_bytes((uint8_t*)buf, n);
}

static integer_t* _add_abs(integer_t* a, integer_t* b, int32_t sign_result) {
    uint32_t len_a = a->length, len_b = b->length;
    uint32_t max_len = len_a > len_b ? len_a : len_b;

    integer_t* result = _integer_allocate(max_len + 1);
    result->sign = sign_result;

    uintptr_t carry = 0;
    for (uint32_t i = 0; i < max_len; ++i) {
        uintptr_t da = i < len_a ? a->array[i] : 0;
        uintptr_t db = i < len_b ? b->array[i] : 0;
        uintptr_t sum = da + db + carry;
        result->array[i] = sum;

        carry = (sum < da || sum < db || (carry && sum == da + db)) ? 1 : 0;
    }

    if (carry != 0) {
        result->array[max_len] = 1;
        result->length = max_len + 1;
    } else {
        result->length = max_len;
    }

    return result;
}

static integer_t* _subtract_abs(integer_t* a, integer_t* b, int32_t sign_result) {
    // assumes |a| ≥ |b|
    integer_t* result = _integer_allocate(a->length);
    result->sign = sign_result;

    uintptr_t borrow = 0;
    for (uint32_t i = 0; i < a->length; ++i) {
        uintptr_t da = a->array[i];
        uintptr_t db = i < b->length ? b->array[i] : 0;
        uintptr_t diff = da - db - borrow;

        borrow = da < db + borrow ? 1 : 0;
        result->array[i] = diff;
    }

    return _normalize_integer(result);
}

object_t* integer_add_full(object_t* oa, object_t* ob) {
    if (_IS_LITERAL(oa) && _IS_LITERAL(ob)) {
        intptr_t sum = _UNTAG_LITERAL(oa) + _UNTAG_LITERAL(ob);
        return (object_t*)_integer_from_intptr(sum);
    }

    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)

    if (ha->sign == hb->sign) {
        return (object_t*)_add_abs(ha, hb, ha->sign);
    }

    int cmp = _compare_abs(ha, hb);
    if (cmp == 0) {
        return (object_t*)_TAG_LITERAL(0);
    } else if (cmp > 0) {
        return (object_t*)_subtract_abs(ha, hb, ha->sign);
    } else {
        return (object_t*)_subtract_abs(hb, ha, hb->sign);
    }
}

object_t* integer_sub_full(object_t* oa, object_t* ob) {
    if (_IS_LITERAL(oa) && _IS_LITERAL(ob)) {
        intptr_t av = _UNTAG_LITERAL(oa);
        intptr_t bv = _UNTAG_LITERAL(ob);
        intptr_t sum = av - bv;
        return (object_t*)_integer_from_intptr(sum);
    }

    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)

    if (ha->sign != hb->sign) {
        return (object_t*)_add_abs(ha, hb, ha->sign);
    }

    // Same sign: a - b = ±(||a| - |b||). Result keeps ha's sign when
    // |a| >= |b|, and flips it when |a| < |b|. The previous version
    // passed `hb->sign` for the flipped case — fine when callers
    // synthesise sign as ±1 but wrong under the 0/1 boolean convention
    // (then `hb->sign == ha->sign`, so the flip never happens), which
    // made every `small - large` heap subtraction lose its negative sign.
    int cmp = _compare_abs(ha, hb);
    if (cmp == 0) {
        return (object_t*)_TAG_LITERAL(0);
    } else if (cmp > 0) {
        return (object_t*)_subtract_abs(ha, hb, ha->sign);
    } else {
        return (object_t*)_subtract_abs(hb, ha, !ha->sign);
    }
}

static integer_t* _multiply_abs(integer_t* a, integer_t* b, int32_t sign_result) {
    uint32_t alen = a->length, blen = b->length;
    uint32_t rlen = alen + blen;
    integer_t* result = _integer_allocate(rlen);
    result->sign = sign_result;

    memset(result->array, 0, rlen * sizeof(intptr_t));

    for (uint32_t i = 0; i < alen; ++i) {
        udword_t carry = 0;
        for (uint32_t j = 0; j < blen; ++j) {
            udword_t product = (udword_t)a->array[i] * (udword_t)b->array[j];
            udword_t sum = (udword_t)result->array[i + j] + product + carry;
            result->array[i + j] = (uintptr_t)sum;
            carry = sum >> WORD_SIZE;
        }
        result->array[i + blen] = (uintptr_t)carry;
    }

    // Trim trailing zeroes
    while (rlen > 1 && result->array[rlen - 1] == 0) {
        --rlen;
    }

    result->length = rlen;
    return result;
}

object_t* integer_mul(object_t* oa, object_t* ob) {
    if (_IS_LITERAL(oa) && _IS_LITERAL(ob)) {
        // Both are literals: unpack and multiply directly
        intptr_t av = _UNTAG_LITERAL(oa);
        intptr_t bv = _UNTAG_LITERAL(ob);
        dword_t rv = (dword_t)av * (dword_t)bv;
        if (rv >= INTPTR_MIN/2 && rv <= INTPTR_MAX/2) {
            return (object_t*)_TAG_LITERAL((intptr_t)rv);
        } else {
            integer_t* result = _integer_allocate(2);
            result->sign = rv < 0 ? 1 : 0;
            // urv must be the magnitude: -rv when rv is negative, rv itself
            // when positive. The previous form (`urv = -rv` unconditionally)
            // wrapped positive products into huge unsigned values, leaving
            // every overflowing positive multiplication with the wrong limbs.
            udword_t urv = (udword_t)(rv < 0 ? -rv : rv);
            result->array[0] = (uintptr_t)urv;
            result->array[1] = (uintptr_t)(urv >> WORD_SIZE);
            result->length = result->array[1] == 0 ? 1 : 2;
            return (object_t*)result;
        }
    }

    // If one is a literal 0 or 1, handle quickly
    if (_IS_LITERAL(oa)) {
        intptr_t av = _UNTAG_LITERAL(oa);
        if (av == 0) return (object_t*)_TAG_LITERAL(0);
        if (av == 1) return ob;
    }

    if (_IS_LITERAL(ob)) {
        intptr_t bv = _UNTAG_LITERAL(ob);
        if (bv == 0) return (object_t*)_TAG_LITERAL(0);
        if (bv == 1) return oa;
    }

    // Promote literals if needed
    _PROMOTE_LITERAL(ha, oa);
    _PROMOTE_LITERAL(hb, ob);

    // Perform full multiplication
    integer_t* r = _multiply_abs(ha, hb, ha->sign ^ hb->sign);
    return (object_t*)r;
}

// Helper function to shift left by one bit (multiply by 2)
static integer_t* _shift_left_one(integer_t* a) {
    if (_IS_LITERAL(a)) {
        intptr_t val = _UNTAG_LITERAL(a);
        if (val <= INTPTR_MAX/4 && val >= INTPTR_MIN/4) {
            return _TAG_LITERAL(val << 1);
        }
        // Need to promote to full integer
        integer_t* result = _integer_allocate(1);
        result->sign = _sign_of(val);
        result->array[0] = _abs_val(val) << 1;
        if (result->array[0] < _abs_val(val)) {
            // Overflow occurred, need two words
            result = _integer_allocate(2);
            result->sign = _sign_of(val);
            result->array[0] = 0;
            result->array[1] = 1;
        }
        return result;
    }

    integer_t* result = _integer_allocate(a->length + 1);
    result->sign = a->sign;

    uintptr_t carry = 0;
    for (uint32_t i = 0; i < a->length; i++) {
        uintptr_t temp = (a->array[i] << 1) | carry;
        carry = (a->array[i] >> (WORD_SIZE - 1)) & 1;
        result->array[i] = temp;
    }

    if (carry) {
        result->array[a->length] = 1;
        result->length = a->length + 1;
    } else {
        result->length = a->length;
    }

    return _normalize_integer(result);
}

// Helper function to shift right by one bit (divide by 2)
static integer_t* _shift_right_one(integer_t* a) {
    if (_IS_LITERAL(a)) {
        intptr_t val = _UNTAG_LITERAL(a);
        return _TAG_LITERAL(val >> 1);
    }

    if (a->length == 1 && a->array[0] == 1) {
        return _TAG_LITERAL(0);
    }

    integer_t* result = _integer_allocate(a->length);
    result->sign = a->sign;

    uintptr_t borrow = 0;
    for (uint32_t i = a->length; i-- > 0; ) {
        uintptr_t temp = (a->array[i] >> 1) | (borrow << (WORD_SIZE - 1));
        borrow = a->array[i] & 1;
        result->array[i] = temp;
    }

    // Trim leading zeros
    uint32_t len = a->length;
    while (len > 1 && result->array[len - 1] == 0) {
        len--;
    }
    result->length = len;

    return _normalize_integer(result);
}

// Helper function for absolute division using binary long division
// Pre-allocates all needed memory to avoid repeated allocations
static void _divide_abs(integer_t* dividend, integer_t* divisor, int32_t sign_result,
                       integer_t** quotient, integer_t** remainder) {
    // Handle division by zero
    if ((divisor->length == 1 && divisor->array[0] == 0) ||
        (_IS_LITERAL(divisor) && _UNTAG_LITERAL(divisor) == 0)) {
        *quotient = _TAG_LITERAL(0);
        *remainder = _TAG_LITERAL(0);
        return;
    }

    int cmp = _compare_abs(dividend, divisor);
    if (cmp < 0) {
        // |dividend| < |divisor|
        *quotient = _TAG_LITERAL(0);
        *remainder = dividend;
        return;
    }

    if (cmp == 0) {
        // |dividend| == |divisor|
        *quotient = _TAG_LITERAL(1);
        *remainder = _TAG_LITERAL(0);
        return;
    }

    // Get actual lengths and arrays for operands
    uint32_t dividend_len, divisor_len;
    uintptr_t *dividend_array, *divisor_array;

    if (_IS_LITERAL(dividend)) {
        dividend_len = 1;
        uintptr_t temp_dividend = _abs_val(_UNTAG_LITERAL(dividend));
        dividend_array = &temp_dividend;
    } else {
        dividend_len = dividend->length;
        dividend_array = dividend->array;
    }

    if (_IS_LITERAL(divisor)) {
        divisor_len = 1;
        uintptr_t temp_divisor = _abs_val(_UNTAG_LITERAL(divisor));
        divisor_array = &temp_divisor;
    } else {
        divisor_len = divisor->length;
        divisor_array = divisor->array;
    }

    // Calculate number of bits in dividend
    uint32_t bits = (dividend_len - 1) * WORD_SIZE;
    uintptr_t top_word = dividend_array[dividend_len - 1];
    while (top_word > 0) {
        top_word >>= 1;
        bits++;
    }

    // Pre-allocate all memory we'll need
    // Maximum possible length for quotient is dividend_len
    // Maximum possible length for remainder is divisor_len
    uint32_t max_q_len = dividend_len;
    uint32_t max_r_len = divisor_len + 1; // +1 for potential overflow during shifts

    integer_t* q = _integer_allocate(max_q_len); q->sign = sign_result;
    integer_t* r = _integer_allocate(max_r_len); r->sign = sign_result;

    // Initialize quotient and remainder to zero
    memset(q->array, 0, max_q_len * sizeof(uintptr_t));
    memset(r->array, 0, max_r_len * sizeof(uintptr_t));
    q->length = 1;
    r->length = 1;
    q->sign = 0;
    r->sign = 0;

    // Binary long division algorithm
    for (uint32_t i = bits; i-- > 0; ) {
        // Left shift remainder by 1 bit (r <<= 1)
        uintptr_t carry = 0;
        for (uint32_t j = 0; j < r->length; j++) {
            uintptr_t temp = (r->array[j] << 1) | carry;
            carry = (r->array[j] >> (WORD_SIZE - 1)) & 1;
            r->array[j] = temp;
        }
        if (carry && r->length < max_r_len) {
            r->array[r->length] = 1;
            r->length++;
        }

        // Get bit i of dividend and set it as LSB of remainder
        uint32_t word_idx = i / WORD_SIZE;
        uint32_t bit_idx = i % WORD_SIZE;

        if (word_idx < dividend_len) {
            int bit = (dividend_array[word_idx] >> bit_idx) & 1;
            if (bit) {
                r->array[0] |= 1;
            }
        }

        // if r >= divisor
        int r_cmp_divisor = 0;
        if (r->length != divisor_len) {
            r_cmp_divisor = r->length > divisor_len ? 1 : -1;
        } else {
            for (uint32_t k = r->length; k-- > 0; ) {
                if (r->array[k] != divisor_array[k]) {
                    r_cmp_divisor = r->array[k] > divisor_array[k] ? 1 : -1;
                    break;
                }
            }
        }

        if (r_cmp_divisor >= 0) {
            // r = r - divisor (subtract in place)
            uintptr_t borrow = 0;
            for (uint32_t j = 0; j < r->length; j++) {
                uintptr_t da = r->array[j];
                uintptr_t db = j < divisor_len ? divisor_array[j] : 0;
                uintptr_t diff = da - db - borrow;

                borrow = da < db + borrow ? 1 : 0;
                r->array[j] = diff;
            }

            // Trim leading zeros from remainder
            while (r->length > 1 && r->array[r->length - 1] == 0) {
                r->length--;
            }

            // Set bit i in quotient (q |= (1 << i))
            uint32_t q_word_idx = i / WORD_SIZE;
            uint32_t q_bit_idx = i % WORD_SIZE;

            if (q_word_idx >= q->length) {
                // Extend quotient length if needed
                q->length = q_word_idx + 1;
            }

            q->array[q_word_idx] |= (1UL << q_bit_idx);
        }
    }

    // Trim leading zeros from quotient
    while (q->length > 1 && q->array[q->length - 1] == 0) {
        q->length--;
    }

    // Check if results can be converted to literals
    *quotient = q;
    *remainder = r;
}

// Public division function
EXPORT object_t* integer_div(object_t* oa, object_t* ob) {
    // Handle literal remainder for common cases
    if (_IS_LITERAL(ob)) {
        intptr_t bv = _UNTAG_LITERAL(ob);

        // Handle division by zero
        if (bv == 0) {
            abort_on_maths_error();
            return NULL;
        }

        // Fast path
        if (_IS_LITERAL(oa)) {
            intptr_t av = _UNTAG_LITERAL(oa);
            intptr_t result = av / bv;
            return (object_t*)_integer_from_intptr(result);
        }
    }

    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)

    integer_t* quotient;
    integer_t* remainder;

    _divide_abs(ha, hb, ha->sign ^ hb->sign, &quotient, &remainder);

    return (object_t*)_normalize_integer(quotient);
}

// Public remainder function
EXPORT object_t* integer_rem(object_t* oa, object_t* ob) {
    // Handle literal remainder for common cases
    if (_IS_LITERAL(ob)) {
        intptr_t bv = _UNTAG_LITERAL(ob);

        // Handle division by zero
        if (bv == 0) {
            abort_on_maths_error();
            return NULL;
        }

        // Fast path
        if (_IS_LITERAL(oa)) {
            intptr_t av = _UNTAG_LITERAL(oa);
            intptr_t result = av % bv;
            return (object_t*)_integer_from_intptr(result);
        }
    }

    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)

    integer_t* quotient;
    integer_t* remainder;

    _divide_abs(ha, hb, ha->sign, &quotient, &remainder);

    return (object_t*)_normalize_integer(remainder);
}


EXPORT object_t* integer_inv_full(object_t* o) {
    integer_t* i = (integer_t*)o;
    if (_IS_LITERAL(i)) {
        return (object_t*)(((intptr_t)i) ^ ((intptr_t)-4));
    }
    /* _add_abs/_subtract_abs need a real integer, not a tagged literal. */
    _PROMOTE_LITERAL(one, INTEGER_LITERAL_1(0, 1))
    if (i->sign) {
        return (object_t*)_subtract_abs(i, one, 0);   /* i<0:  ~i = |i|-1 */
    } else {
        return (object_t*)_add_abs(i, one, 1);        /* i>=0: ~i = -(i+1) */
    }
}


typedef enum { BIT_AND, BIT_OR, BIT_XOR, BIT_ANDNOT } bitop_t;

static inline uintptr_t _bit_combine(bitop_t op, uintptr_t x, uintptr_t y) {
    switch (op) {
        case BIT_AND:    return x & y;
        case BIT_OR:     return x | y;
        case BIT_XOR:    return x ^ y;
        case BIT_ANDNOT: return x & ~y;   /* a AND NOT b */
    }
    return 0; /* unreachable */
}

// Bitwise op over the infinite-width two's-complement view of two
// sign-magnitude integers.  For each limb (low to high) we read the operand's
// two's-complement form (lazily complementing a negative magnitude, ~mag + 1),
// combine, take the result sign from the op of the operands' sign bits, and
// convert a negative result back to sign-magnitude.  a and b are already
// promoted (real integer_t*, never tagged literals).
static integer_t* _integer_bitwise(integer_t* a, integer_t* b, bitop_t op) {
    int32_t sr = (int32_t)(_bit_combine(op, (uintptr_t)a->sign, (uintptr_t)b->sign) & 1);

    uint32_t la = a->length, lb = b->length;
    uint32_t n = (la > lb ? la : lb) + 1;   // +1: headroom for the negate carry

    integer_t* result = _integer_allocate(n);
    result->sign = sr;

    uintptr_t ca = 1, cb = 1, cr = 1;       // the +1 in each ~x+1 conversion
    for (uint32_t i = 0; i < n; ++i) {
        uintptr_t ta = i < la ? a->array[i] : 0;
        if (a->sign) { uintptr_t t = ~ta + ca; ca = t < ca; ta = t; }

        uintptr_t tb = i < lb ? b->array[i] : 0;
        if (b->sign) { uintptr_t t = ~tb + cb; cb = t < cb; tb = t; }

        uintptr_t tr = _bit_combine(op, ta, tb);

        if (sr) { uintptr_t t = ~tr + cr; cr = t < cr; result->array[i] = t; }
        else    { result->array[i] = tr; }
    }
    return _normalize_integer(result);
}

EXPORT object_t* integer_and_full(object_t* oa, object_t* ob) {
    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)
    return (object_t*)_integer_bitwise(ha, hb, BIT_AND);
}

EXPORT object_t* integer_or_full(object_t* oa, object_t* ob) {
    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)
    return (object_t*)_integer_bitwise(ha, hb, BIT_OR);
}

EXPORT object_t* integer_xor_full(object_t* oa, object_t* ob) {
    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)
    return (object_t*)_integer_bitwise(ha, hb, BIT_XOR);
}

EXPORT object_t* integer_andnot_full(object_t* oa, object_t* ob) {
    _PROMOTE_LITERAL(ha, oa)
    _PROMOTE_LITERAL(hb, ob)
    return (object_t*)_integer_bitwise(ha, hb, BIT_ANDNOT);
}


// 2^bits as a fresh positive bigint. Normalised, so a small power comes back as
// a tagged literal — other ops assume heap integers are never a single small
// limb (that form is always tagged), and an un-normalised one mis-divides.
static integer_t* _pow2(uint32_t bits) {
    uint32_t word_bits = (uint32_t)(sizeof(uintptr_t) * 8);
    uint32_t limbs = bits / word_bits + 1;
    integer_t* r = _integer_allocate(limbs);
    r->sign = 0;
    for (uint32_t i = 0; i + 1 < limbs; ++i) r->array[i] = 0;
    r->array[limbs - 1] = (uintptr_t)1 << (bits % word_bits);
    r->length = limbs;
    return _normalize_integer(r);
}

// Bit shifts on the arbitrary-precision integer. `<<` is `self * 2^amount`;
// `>>` is an *arithmetic* (floor) shift, `floor(self / 2^amount)`, matching the
// fixed-width and Java/Python `>>`. Implemented via the (tested) multiply and
// truncating divide rather than a bespoke limb shift — simpler and correct; a
// shift is not a hot path. A non-positive amount is a no-op.
EXPORT object_t* integer_shl(object_t* self, object_t* amount) {
    int32_t k = int32_from_integer(amount);
    if (k <= 0) return self;
    return integer_mul(self, (object_t*)_pow2((uint32_t)k));
}

EXPORT object_t* integer_shr(object_t* self, object_t* amount) {
    int32_t k = int32_from_integer(amount);
    if (k <= 0) return self;
    object_t* p = (object_t*)_pow2((uint32_t)k);
    object_t* q = integer_div(self, p);   // truncates toward zero
    // Arithmetic shift floors toward -inf: a negative value with any bit
    // shifted out rounds down by one.
    if (integer_cmp(self, INTEGER_LITERAL_1(0, 0)) < 0
            && integer_cmp(integer_rem(self, p), INTEGER_LITERAL_1(0, 0)) != 0) {
        q = integer_sub(q, INTEGER_LITERAL_1(0, 1));
    }
    return q;
}









