
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

/* ---- integer_create_from_int32 / integer_to_int32 roundtrips ---- */

TEST(roundtrip_zero)
    ASSERT_INT_EQ_I32(integer_create_from_int32(0), 0);
TEST_END()

TEST(roundtrip_positive)
    ASSERT_INT_EQ_I32(integer_create_from_int32(42), 42);
TEST_END()

TEST(roundtrip_negative)
    ASSERT_INT_EQ_I32(integer_create_from_int32(-42), -42);
TEST_END()

TEST(roundtrip_int32_max)
    ASSERT_INT_EQ_I32(integer_create_from_int32(INT32_MAX), INT32_MAX);
TEST_END()

TEST(roundtrip_int32_min)
    ASSERT_INT_EQ_I32(integer_create_from_int32(INT32_MIN), INT32_MIN);
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
    int32_t v = integer_to_int32_with_overflow(I(99), &ov);
    ASSERT_EQ_I32(v, 99);
    ASSERT(!ov);
TEST_END()

TEST(to_int32_overflow)
    /* A bigint bigger than INT32_MAX should set overflow */
    object_t* big = BL2(0, 0, 0x80000000);  /* > INT32_MAX on 64-bit */
    int ov = 0;
    integer_to_int32_with_overflow(big, &ov);
    ASSERT(ov);
TEST_END()

TEST(to_int32_overflow_three_word)
    /* Any heap integer with length > 1 sets overflow regardless of value,
       because the value may exceed int32 range. */
    object_t* big = BL3(0, 0, 0, 1);   /* 3-word heap integer */
    int ov = 0;
    integer_to_int32_with_overflow(big, &ov);
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

    object_t* status = integer_create_from_int32(r.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, status);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
