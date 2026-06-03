
#include "test_framework.h"

/* ---- helpers ---- */

/* Big integer literals (mirrors the BL macros from main.c) */
#define BL2(sign, a, b)     INTEGER_LITERAL_2(sign, (a), (b))
#define BL3(sign, a, b, c)  INTEGER_LITERAL_N(sign, 3, \
        {INTEGER_LITERAL_N_2((a),(b)) INTEGER_LITERAL_SEP INTEGER_LITERAL_N_1((c))})
#define BL4(sign, a, b, c, d) INTEGER_LITERAL_N(sign, 3, \
        {INTEGER_LITERAL_N_2((a),(b)) INTEGER_LITERAL_SEP INTEGER_LITERAL_N_2((c),(d))})

/* ---- pointer tagging ---- */

TEST(ptr_tag_object_zero)
    /* NULL / zero pointer should look like an object pointer */
    ASSERT(PTR_IS_OBJECT(NULL));
TEST_END()

TEST(ptr_tag_integer_positive)
    object_t* v = I(1);
    ASSERT(PTR_IS_INTEGER(v));
    ASSERT(!PTR_IS_OBJECT(v));
    ASSERT(!PTR_IS_STRING(v));
TEST_END()

TEST(ptr_tag_integer_negative)
    object_t* v = I(-1);
    ASSERT(PTR_IS_INTEGER(v));
TEST_END()

TEST(ptr_tag_integer_zero)
    object_t* v = I(0);
    ASSERT(PTR_IS_INTEGER(v));
TEST_END()

TEST(literal_range_positive_boundary)
#if WORD_SIZE == 64
    /* On 64-bit, literals occupy the upper 62 bits of the pointer. */
    ASSERT(PTR_IS_INTEGER(BL2(0, 0, INT32_MAX/4)));
    ASSERT(!PTR_IS_INTEGER(BL2(0, 0, INT32_MAX/4+1)));
#else
    ASSERT(PTR_IS_INTEGER(INTEGER_LITERAL_1(0, INT32_MAX/2)));
    ASSERT(!PTR_IS_INTEGER(INTEGER_LITERAL_1(0, INT32_MAX/2+1)));
#endif
TEST_END()

TEST(literal_range_negative_boundary)
#if WORD_SIZE == 64
    ASSERT(PTR_IS_INTEGER(BL2(-1, 0, INT32_MAX/4+1)));
    ASSERT(!PTR_IS_INTEGER(BL2(-1, 0, INT32_MAX/4+2)));
#else
    ASSERT(PTR_IS_INTEGER(INTEGER_LITERAL_1(-1, INT32_MAX/2+1)));
    ASSERT(!PTR_IS_INTEGER(INTEGER_LITERAL_1(-1, INT32_MAX/2+2)));
#endif
TEST_END()

/* ---- integer_from_int32 / int32_from_integer roundtrips ---- */

TEST(roundtrip_zero)
    ASSERT_INT_EQ_I32(integer_from_int32(0), 0);
TEST_END()

TEST(roundtrip_positive)
    ASSERT_INT_EQ_I32(integer_from_int32(42), 42);
TEST_END()

TEST(roundtrip_negative)
    ASSERT_INT_EQ_I32(integer_from_int32(-42), -42);
TEST_END()

TEST(roundtrip_int32_max)
    ASSERT_INT_EQ_I32(integer_from_int32(INT32_MAX), INT32_MAX);
TEST_END()

TEST(roundtrip_int32_min)
    ASSERT_INT_EQ_I32(integer_from_int32(INT32_MIN), INT32_MIN);
TEST_END()

/* ---- addition ---- */

TEST(add_small_positive)
    ASSERT_INT_EQ(integer_add(I(20), I(1)), I(21));
TEST_END()

TEST(add_small_negative)
    ASSERT_INT_EQ(integer_add(I(-5), I(-3)), I(-8));
TEST_END()

TEST(add_mixed_signs_to_zero)
    ASSERT_INT_EQ(integer_add(I(7), I(-7)), I(0));
TEST_END()

TEST(add_mixed_signs_positive_result)
    ASSERT_INT_EQ(integer_add(I(10), I(-3)), I(7));
TEST_END()

TEST(add_mixed_signs_negative_result)
    ASSERT_INT_EQ(integer_add(I(3), I(-10)), I(-7));
TEST_END()

TEST(add_big_cancels_to_zero)
    /* BL3(0,0,0,1) + BL3(-1,0,0,1) == 0 */
    ASSERT_INT_EQ(integer_add(BL3(0,0,0,1), BL3(-1,0,0,1)), I(0));
TEST_END()

TEST(add_big_carry)
    /* 0x80000000 + 0x80000000 == 0x100000000 */
    ASSERT_INT_EQ(integer_add(BL2(0,0,0x80000000), BL2(0,0,0x80000000)),
                  BL3(0,0,0,1));
TEST_END()

TEST(add_big_mixed)
    ASSERT_INT_EQ(integer_add(BL3(0,0,0,0x80000000), BL3(-1,1,0,0x80000000)),
                  I(-1));
TEST_END()

/* ---- subtraction ---- */

TEST(sub_basic)
    ASSERT_INT_EQ(integer_sub(I(20), I(1)), I(19));
TEST_END()

TEST(sub_negative_operand)
    ASSERT_INT_EQ(integer_sub(I(20), I(-1)), I(21));
TEST_END()

TEST(sub_both_negative)
    ASSERT_INT_EQ(integer_sub(I(-50), I(50)), I(-100));
TEST_END()

TEST(sub_big)
    /* BL3(-1,0,1,0x40000000) - BL3(0,0,2,0x40000000) = BL3(-1,0,3,0x80000000) */
    ASSERT_INT_EQ(
        integer_sub(BL3(-1,0,1,0x40000000), BL3(0,0,2,0x40000000)),
        BL3(-1,0,3,0x80000000));
TEST_END()

/* ---- multiplication ---- */

TEST(mul_basic)
    ASSERT_INT_EQ(integer_mul(I(10), I(10)), I(100));
TEST_END()

TEST(mul_by_zero)
    ASSERT_INT_EQ(integer_mul(I(12345), I(0)), I(0));
TEST_END()

TEST(mul_by_one)
    ASSERT_INT_EQ(integer_mul(I(12345), I(1)), I(12345));
TEST_END()

TEST(mul_negative)
    ASSERT_INT_EQ(integer_mul(I(-3), I(4)), I(-12));
TEST_END()

TEST(mul_both_negative)
    ASSERT_INT_EQ(integer_mul(I(-3), I(-4)), I(12));
TEST_END()

/* ---- division ---- */

TEST(div_basic)
    ASSERT_INT_EQ(integer_div(I(10), I(10)), I(1));
TEST_END()

TEST(div_remainder_discarded)
    ASSERT_INT_EQ(integer_div(I(10), I(3)), I(3));
TEST_END()

TEST(div_negative_dividend)
    ASSERT_INT_EQ(integer_div(I(-10), I(3)), I(-3));
TEST_END()

TEST(div_negative_divisor)
    ASSERT_INT_EQ(integer_div(I(10), I(-3)), I(-3));
TEST_END()

TEST(div_large)
    ASSERT_INT_EQ(integer_div(BL4(0,0,0,0,10), BL4(0,0,0,0,1)), I(10));
TEST_END()

/* ---- remainder ---- */

TEST(rem_basic)
    ASSERT_INT_EQ(integer_rem(I(10), I(9)), I(1));
TEST_END()

TEST(rem_exact)
    ASSERT_INT_EQ(integer_rem(I(10), I(5)), I(0));
TEST_END()

TEST(rem_large)
    ASSERT_INT_EQ(integer_rem(BL3(0,10,0,1), BL3(0,0,0,1)), I(10));
TEST_END()

TEST(rem_negative_dividend)
    /* Sign of remainder follows the dividend (C99 convention). -10 % 3 == -1 */
    ASSERT_INT_EQ(integer_rem(I(-10), I(3)), I(-1));
TEST_END()

TEST(rem_negative_divisor)
    /* Divisor sign does not affect remainder sign. 10 % -3 == 1 */
    ASSERT_INT_EQ(integer_rem(I(10), I(-3)), I(1));
TEST_END()

TEST(rem_both_negative)
    /* Both negative: sign still follows dividend. -10 % -3 == -1 */
    ASSERT_INT_EQ(integer_rem(I(-10), I(-3)), I(-1));
TEST_END()

/* ---- bitwise invert ---- */
/* For two's-complement (which an arbitrary-precision integer models),
   ~x == -x - 1.  Small values take integer_inv's tagged fast path; the
   multi-word literals exercise integer_inv_full. */

TEST(inv_zero)
    ASSERT_INT_EQ(integer_inv(I(0)), I(-1));
TEST_END()

TEST(inv_minus_one)
    ASSERT_INT_EQ(integer_inv(I(-1)), I(0));
TEST_END()

TEST(inv_positive_small)
    /* ~5 == -6 */
    ASSERT_INT_EQ(integer_inv(I(5)), I(-6));
TEST_END()

TEST(inv_negative_small)
    /* ~(-6) == 5 */
    ASSERT_INT_EQ(integer_inv(I(-6)), I(5));
TEST_END()

TEST(inv_involution_small)
    /* ~~x == x */
    ASSERT_INT_EQ(integer_inv(integer_inv(I(12345))), I(12345));
TEST_END()

TEST(inv_matches_minus_one_minus_x_small)
    /* ~x == -1 - x, cross-checked against subtraction */
    ASSERT_INT_EQ(integer_inv(I(100)), integer_sub(I(-1), I(100)));
TEST_END()

/* The explicit-negative checks below use the identity ~X + X == -1 rather
   than hand-written negative literals: the BL* macros store the raw sign arg
   (-1) in the sign field, whereas a freshly computed negative carries the
   canonical sign (1), and integer_test_eq does not reconcile the two. */

TEST(inv_big_two_word)
    /* X = 2^63: ~X is heap (forces integer_inv_full), and ~X + X == -1 */
    ASSERT_INT_EQ(integer_add(integer_inv(BL2(0,0,0x80000000)),
                              BL2(0,0,0x80000000)), I(-1));
TEST_END()

TEST(inv_big_three_word)
    /* X = 2^64: ~X + X == -1 */
    ASSERT_INT_EQ(integer_add(integer_inv(BL3(0,0,0,1)),
                              BL3(0,0,0,1)), I(-1));
TEST_END()

TEST(inv_big_negative)
    /* ~(-(2^64 + 1)) == 2^64 — input sign propagates, result is canonical +ve */
    ASSERT_INT_EQ(integer_inv(BL3(-1,1,0,1)), BL3(0,0,0,1));
TEST_END()

TEST(inv_big_involution)
    /* ~~x == x for a genuine three-word value */
    ASSERT_INT_EQ(integer_inv(integer_inv(BL3(0,0,1,0x12345678))),
                  BL3(0,0,1,0x12345678));
TEST_END()

TEST(inv_big_matches_minus_one_minus_x)
    /* ~x == -1 - x for a big value, cross-checked against subtraction */
    object_t* x = BL3(0,0,1,0x12345678);
    ASSERT_INT_EQ(integer_inv(x), integer_sub(I(-1), x));
TEST_END()

/* Fixed-width invert is plain ~ truncated to the type's width. */
TEST(inv_fixed_width)
    ASSERT_EQ_I32(int8_inv((int8_t)0),    (int8_t)-1);
    ASSERT_EQ_I32(int8_inv((int8_t)-1),   (int8_t)0);
    ASSERT_EQ_I32(int8_inv((int8_t)5),    (int8_t)-6);
    ASSERT_EQ_I32(int16_inv((int16_t)0),  (int16_t)-1);
    ASSERT_EQ_I32(int16_inv((int16_t)0x1234), (int16_t)~0x1234);
    ASSERT_EQ_I32(int32_inv(0),           -1);
    ASSERT_EQ_I32(int32_inv(INT32_MAX),   INT32_MIN);
    ASSERT_EQ_I32(int32_inv(0x12345678),  ~0x12345678);
    ASSERT(int64_inv((int64_t)0)             == (int64_t)-1);
    ASSERT(int64_inv((int64_t)0x123456789ABCLL) == ~(int64_t)0x123456789ABCLL);
    ASSERT(int64_inv(INT64_MAX)              == INT64_MIN);
TEST_END()

/* ---- bitwise and / or / xor / andnot ---- */

/* Two-limb (length 2) heap operands for the big-value cases.
   X.limbs = [0x12345678F0F0F0F0, 0x0BADF00D]
   Y.limbs = [0xFFFF00000F0F0F0F, 0x00C0FFEE] */
#define BIG_X BL3(0, 0xF0F0F0F0, 0x12345678, 0x0BADF00D)
#define BIG_Y BL3(0, 0x0F0F0F0F, 0xFFFF0000, 0x00C0FFEE)
#define BIG_Z BL3(-1, 1, 0, 1)               /* -(2^64 + 1): heap, negative */

TEST(and_small)
    ASSERT_INT_EQ(integer_and(I(12), I(10)), I(8));
    ASSERT_INT_EQ(integer_and(I(-1), I(5)),  I(5));    /* all-ones & x == x */
    ASSERT_INT_EQ(integer_and(I(-8), I(-3)), I(-8));   /* both negative */
TEST_END()

TEST(or_small)
    ASSERT_INT_EQ(integer_or(I(12), I(10)), I(14));
    ASSERT_INT_EQ(integer_or(I(-1), I(5)),  I(-1));
    ASSERT_INT_EQ(integer_or(I(-8), I(-3)), I(-3));
TEST_END()

TEST(xor_small)
    ASSERT_INT_EQ(integer_xor(I(12), I(10)), I(6));
    ASSERT_INT_EQ(integer_xor(I(-1), I(5)),  I(-6));   /* x ^ -1 == ~x */
    ASSERT_INT_EQ(integer_xor(I(-8), I(-3)), I(5));
TEST_END()

TEST(andnot_small)
    ASSERT_INT_EQ(integer_andnot(I(12), I(10)), I(4)); /* 12 & ~10 */
    ASSERT_INT_EQ(integer_andnot(I(5),  I(3)),  I(4));
    ASSERT_INT_EQ(integer_andnot(I(-1), I(5)),  I(-6));/* ~5 */
TEST_END()

/* Concrete multi-limb results, hand-computed limb by limb (positive → the
   BL sign field is the canonical 0, so direct comparison is safe). */
TEST(and_big)
    ASSERT_INT_EQ(integer_and(BIG_X, BIG_Y), BL3(0, 0, 0x12340000, 0x0080F00C));
TEST_END()

TEST(or_big)
    ASSERT_INT_EQ(integer_or(BIG_X, BIG_Y), BL3(0, 0xFFFFFFFF, 0xFFFF5678, 0x0BEDFFEF));
TEST_END()

TEST(xor_big)
    ASSERT_INT_EQ(integer_xor(BIG_X, BIG_Y), BL3(0, 0xFFFFFFFF, 0xEDCB5678, 0x0B6D0FE3));
TEST_END()

TEST(andnot_big)
    ASSERT_INT_EQ(integer_andnot(BIG_X, BIG_Y), BL3(0, 0xF0F0F0F0, 0x00005678, 0x0B2D0001));
TEST_END()

/* Algebraic identities — sign-encoding-agnostic, and cover negative/mixed
   operands (BIG_Z) where hand-written negative literals would be unreliable. */
TEST(bitwise_identities_big)
    ASSERT_INT_EQ(integer_and(BIG_X, BIG_X), BIG_X);
    ASSERT_INT_EQ(integer_or(BIG_X, BIG_X),  BIG_X);
    ASSERT_INT_EQ(integer_xor(BIG_X, BIG_X), I(0));
    ASSERT_INT_EQ(integer_or(BIG_X, I(0)),   BIG_X);
    ASSERT_INT_EQ(integer_and(BIG_X, I(0)),  I(0));
    ASSERT_INT_EQ(integer_andnot(BIG_X, I(0)), BIG_X);
    ASSERT_INT_EQ(integer_andnot(BIG_X, BIG_X), I(0));
TEST_END()

TEST(andnot_equals_and_inv_big)
    /* a andnot b == a & ~b — including a negative left operand */
    ASSERT_INT_EQ(integer_andnot(BIG_X, BIG_Y),
                  integer_and(BIG_X, integer_inv(BIG_Y)));
    ASSERT_INT_EQ(integer_andnot(BIG_Z, BIG_X),
                  integer_and(BIG_Z, integer_inv(BIG_X)));
TEST_END()

TEST(de_morgan_big)
    /* ~(a & b) == ~a | ~b ;  ~(a | b) == ~a & ~b (with a negative operand) */
    ASSERT_INT_EQ(integer_inv(integer_and(BIG_X, BIG_Y)),
                  integer_or(integer_inv(BIG_X), integer_inv(BIG_Y)));
    ASSERT_INT_EQ(integer_inv(integer_or(BIG_Z, BIG_Y)),
                  integer_and(integer_inv(BIG_Z), integer_inv(BIG_Y)));
TEST_END()

TEST(xor_identity_big)
    /* a ^ b == (a | b) andnot (a & b), with a negative operand */
    ASSERT_INT_EQ(integer_xor(BIG_X, BIG_Z),
                  integer_andnot(integer_or(BIG_X, BIG_Z),
                                 integer_and(BIG_X, BIG_Z)));
TEST_END()

TEST(bitwise_fixed_width)
    ASSERT_EQ_I32(int32_and(0xF0F0, 0x0FF0),    0x00F0);
    ASSERT_EQ_I32(int32_or(0xF0F0, 0x0FF0),     0xFFF0);
    ASSERT_EQ_I32(int32_xor(0xF0F0, 0x0FF0),    0xFF00);
    ASSERT_EQ_I32(int32_andnot(0xF0F0, 0x0FF0), 0xF000);
    ASSERT_EQ_I32(int32_and(-1, 5),  5);
    ASSERT_EQ_I32(int32_or(-1, 5),   -1);
    ASSERT_EQ_I32(int8_and((int8_t)0x3C, (int8_t)0x0F), (int8_t)0x0C);
    ASSERT_EQ_I32(int8_xor((int8_t)-1, (int8_t)0x0F),   (int8_t)0xF0);
    ASSERT(int16_or((int16_t)0x00FF, (int16_t)0xFF00)  == (int16_t)0xFFFF);
    ASSERT(int64_andnot((int64_t)0xFF, (int64_t)0x0F)  == (int64_t)0xF0);
TEST_END()

/* ---- bit shifts ---- */
/* `<<` is multiply-by-2^k; `>>` is an arithmetic (floor) shift. */

TEST(shl_small)
    ASSERT_INT_EQ(integer_shl(I(1), I(4)), I(16));
    ASSERT_INT_EQ(integer_shl(I(3), I(2)), I(12));
    ASSERT_INT_EQ(integer_shl(I(5), I(0)), I(5));      /* no-op */
TEST_END()

TEST(shl_big)
    ASSERT_INT_EQ(integer_shl(I(1), I(63)), BL2(0,0,0x80000000));  /* 2^63 */
    ASSERT_INT_EQ(integer_shl(I(1), I(64)), BL3(0,0,0,1));         /* 2^64 */
TEST_END()

TEST(shl_negative)
    ASSERT_INT_EQ(integer_shl(I(-1), I(4)), I(-16));
    ASSERT_INT_EQ(integer_shl(I(-3), I(1)), I(-6));
TEST_END()

TEST(shr_small)
    ASSERT_INT_EQ(integer_shr(I(16),  I(2)), I(4));
    ASSERT_INT_EQ(integer_shr(I(100), I(3)), I(12));
    ASSERT_INT_EQ(integer_shr(I(7),   I(0)), I(7));    /* no-op */
TEST_END()

TEST(shr_arithmetic_negative)
    /* floor division by 2^k, not truncation toward zero */
    ASSERT_INT_EQ(integer_shr(I(-5), I(1)), I(-3));
    ASSERT_INT_EQ(integer_shr(I(-8), I(2)), I(-2));
    ASSERT_INT_EQ(integer_shr(I(-1), I(1)), I(-1));
    ASSERT_INT_EQ(integer_shr(I(-7), I(1)), I(-4));
TEST_END()

TEST(shr_big)
    ASSERT_INT_EQ(integer_shr(BL3(0,0,0,1), I(64)), I(1));         /* 2^64 >> 64 */
    ASSERT_INT_EQ(integer_shr(BL2(0,0,0x80000000), I(63)), I(1));  /* 2^63 >> 63 */
TEST_END()

TEST(shift_round_trip)
    ASSERT_INT_EQ(integer_shr(integer_shl(I(5),  I(40)), I(40)), I(5));
    ASSERT_INT_EQ(integer_shr(integer_shl(I(-5), I(40)), I(40)), I(-5));
TEST_END()

TEST(shift_fixed_width)
    ASSERT_EQ_I32(int32_shl(1, 4),         16);
    ASSERT_EQ_I32(int32_shl(0xFF, 8),      0xFF00);
    ASSERT_EQ_I32(int32_shl(-1, 1),        -2);
    ASSERT_EQ_I32(int32_shl(1, 32),        1);      /* count masked: 32 & 31 == 0 */
    ASSERT_EQ_I32(int32_shr(16, 2),        4);
    ASSERT_EQ_I32(int32_shr(-16, 2),       -4);     /* arithmetic */
    ASSERT_EQ_I32(int32_shr(-1, 1),        -1);
    ASSERT_EQ_I32(int32_shr(INT32_MIN, 31), -1);
    ASSERT_EQ_I32(int8_shl((int8_t)1, (int8_t)7),   (int8_t)0x80);  /* -128 */
    ASSERT_EQ_I32(int8_shr((int8_t)-1, (int8_t)1),  (int8_t)-1);
    ASSERT(int64_shl((int64_t)1, (int64_t)40)      == ((int64_t)1 << 40));
    ASSERT(int64_shr((int64_t)-1024, (int64_t)2)   == (int64_t)-256);
TEST_END()

/* ---- comparison ---- */

TEST(cmp_equal)
    ASSERT_EQ_I32(integer_cmp(I(5), I(5)), 0);
TEST_END()

TEST(cmp_less)
    ASSERT(integer_cmp(I(3), I(5)) < 0);
TEST_END()

TEST(cmp_greater)
    ASSERT(integer_cmp(I(5), I(3)) > 0);
TEST_END()

TEST(cmp_negative_vs_positive)
    ASSERT(integer_cmp(I(-1), I(1)) < 0);
TEST_END()

TEST(cmp_both_negative)
    ASSERT(integer_cmp(I(-5), I(-3)) < 0);
TEST_END()

TEST(test_eq_predicate)
    ASSERT(integer_test_eq(I(7), I(7)));
    ASSERT(!integer_test_eq(I(7), I(8)));
TEST_END()

TEST(test_lt_predicate)
    ASSERT(integer_test_lt(I(3), I(5)));
    ASSERT(!integer_test_lt(I(5), I(3)));
TEST_END()

TEST(test_gt_predicate)
    ASSERT(integer_test_gt(I(5), I(3)));
    ASSERT(!integer_test_gt(I(3), I(5)));
TEST_END()

TEST(test_le_predicate)
    ASSERT(integer_test_le(I(3), I(5)));
    ASSERT(integer_test_le(I(5), I(5)));
    ASSERT(!integer_test_le(I(6), I(5)));
TEST_END()

TEST(test_ge_predicate)
    ASSERT(integer_test_ge(I(5), I(3)));
    ASSERT(integer_test_ge(I(5), I(5)));
    ASSERT(!integer_test_ge(I(4), I(5)));
TEST_END()

/* ---- to_int32_with_overflow ---- */

TEST(to_int32_no_overflow)
    int ov = 0;
    int32_t v = int32_from_integer_with_overflow(I(99), &ov);
    ASSERT_EQ_I32(v, 99);
    ASSERT(!ov);
TEST_END()

TEST(to_int32_overflow)
    /* A bigint bigger than INT32_MAX should set overflow */
    object_t* big = BL2(0, 0, 0x80000000);  /* > INT32_MAX on 64-bit */
    int ov = 0;
    int32_from_integer_with_overflow(big, &ov);
    ASSERT(ov);
TEST_END()

TEST(to_int32_overflow_three_word)
    /* Any heap integer with length > 1 sets overflow regardless of value,
       because the value may exceed int32 range. */
    object_t* big = BL3(0, 0, 0, 1);   /* 3-word heap integer */
    int ov = 0;
    int32_from_integer_with_overflow(big, &ov);
    ASSERT(ov);
TEST_END()

/* ---- normalization ---- */

TEST(add_result_normalizes_to_literal)
    /* When big-integer arithmetic produces a result small enough for a tagged
       literal, _normalize_integer must return a tagged pointer, not a heap object.
       PTR_IS_INTEGER distinguishes tagged integers from heap integers. */
    object_t* result = integer_add(BL3(0,0,0,1), BL3(-1,0,0,1));
    ASSERT(PTR_IS_INTEGER(result));
    ASSERT_INT_EQ_I32(result, 0);
TEST_END()

/* ---- entrypoint ---- */

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) { prev_roots(declare); }

static void run_tests(object_t* _, fun_t continuation) {
    struct test_results r = {0, 0, NULL};
    struct test_results* _r = &r;

    printf("=== integer tests ===\n");

    /* tagging */
    RUN(ptr_tag_object_zero);
    RUN(ptr_tag_integer_positive);
    RUN(ptr_tag_integer_negative);
    RUN(ptr_tag_integer_zero);
    RUN(literal_range_positive_boundary);
    RUN(literal_range_negative_boundary);

    /* roundtrips */
    RUN(roundtrip_zero);
    RUN(roundtrip_positive);
    RUN(roundtrip_negative);
    RUN(roundtrip_int32_max);
    RUN(roundtrip_int32_min);

    /* addition */
    RUN(add_small_positive);
    RUN(add_small_negative);
    RUN(add_mixed_signs_to_zero);
    RUN(add_mixed_signs_positive_result);
    RUN(add_mixed_signs_negative_result);
    RUN(add_big_cancels_to_zero);
    RUN(add_big_carry);
    RUN(add_big_mixed);

    /* subtraction */
    RUN(sub_basic);
    RUN(sub_negative_operand);
    RUN(sub_both_negative);
    RUN(sub_big);

    /* multiplication */
    RUN(mul_basic);
    RUN(mul_by_zero);
    RUN(mul_by_one);
    RUN(mul_negative);
    RUN(mul_both_negative);

    /* division */
    RUN(div_basic);
    RUN(div_remainder_discarded);
    RUN(div_negative_dividend);
    RUN(div_negative_divisor);
    RUN(div_large);

    /* remainder */
    RUN(rem_basic);
    RUN(rem_exact);
    RUN(rem_large);
    RUN(rem_negative_dividend);
    RUN(rem_negative_divisor);
    RUN(rem_both_negative);

    /* bitwise invert */
    RUN(inv_zero);
    RUN(inv_minus_one);
    RUN(inv_positive_small);
    RUN(inv_negative_small);
    RUN(inv_involution_small);
    RUN(inv_matches_minus_one_minus_x_small);
    RUN(inv_big_two_word);
    RUN(inv_big_three_word);
    RUN(inv_big_negative);
    RUN(inv_big_involution);
    RUN(inv_big_matches_minus_one_minus_x);
    RUN(inv_fixed_width);

    /* bitwise and/or/xor/andnot */
    RUN(and_small);
    RUN(or_small);
    RUN(xor_small);
    RUN(andnot_small);
    RUN(and_big);
    RUN(or_big);
    RUN(xor_big);
    RUN(andnot_big);
    RUN(bitwise_identities_big);
    RUN(andnot_equals_and_inv_big);
    RUN(de_morgan_big);
    RUN(xor_identity_big);
    RUN(bitwise_fixed_width);

    /* bit shifts */
    RUN(shl_small);
    RUN(shl_big);
    RUN(shl_negative);
    RUN(shr_small);
    RUN(shr_arithmetic_negative);
    RUN(shr_big);
    RUN(shift_round_trip);
    RUN(shift_fixed_width);

    /* comparison */
    RUN(cmp_equal);
    RUN(cmp_less);
    RUN(cmp_greater);
    RUN(cmp_negative_vs_positive);
    RUN(cmp_both_negative);
    RUN(test_eq_predicate);
    RUN(test_lt_predicate);
    RUN(test_gt_predicate);
    RUN(test_le_predicate);
    RUN(test_ge_predicate);

    /* overflow */
    RUN(to_int32_no_overflow);
    RUN(to_int32_overflow);
    RUN(to_int32_overflow_three_word);

    /* normalization */
    RUN(add_result_normalizes_to_literal);

    PRINT_RESULTS("integer", _r);

    object_t* status = integer_from_int32(r.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, status);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
