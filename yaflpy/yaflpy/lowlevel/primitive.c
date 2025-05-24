#include "yafl.h"
#line 3 "integer.c"

EXPORT decl_no_inline
void __abort_on_overflow() {
    fputs("Aborting due to integer overflow", stderr);
    abort();
    __builtin_unreachable();
}

#undef DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK
#define DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(type, operation)\
        EXPORT decl_func\
        type ## _t __OP_ ## operation ## _ ## type ## __(type ## _t a, type ## _t b) {\
            type ## _t result;\
            if (__builtin_ ## operation ## _overflow(a, b, &result))\
                __abort_on_overflow();\
            return result;\
        }

DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int8 , add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int16, add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int32, add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int64, add)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int8 , sub)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int16, sub)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int32, sub)
DECLARE_OP_MATH_INT_WITH_OVERFLOW_CHECK(int64, sub)

#undef DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK
#define DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(from_type, to_type)\
        EXPORT decl_func\
        to_type ## _t __OP_convert_ ## from_type ## _to_ ## to_type ## __(from_type ## _t a) {\
            to_type ## _t discard;\
            if (__builtin_add_overflow(a, (from_type ## _t)0, &discard))\
                __abort_on_overflow();\
            return (to_type ## _t)a;\
        }

DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int8 , int16)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int8 , int32)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int8 , int64)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int16, int8 )
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int16, int32)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int16, int64)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int32, int8 )
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int32, int16)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int32, int64)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int64, int8 )
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int64, int16)
DECLARE_OP_CONVERT_INT_WITH_OVERFLOW_CHECK(int64, int32)

