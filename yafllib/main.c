
#include "yafl.h"
#include <stdio.h>
#include <stdlib.h>

static roots_declaration_func_t previous_declare_roots;

static void declare_roots(void(*declare)(object_t**)) {
    previous_declare_roots(declare);
}


struct test_results {
    int passed;
    int failed;
};

#define JOIN(prefix, name) prefix##name

#define TEST(name) \
        void JOIN(test_, name) (struct test_results* results) {\
            printf("Test: %s - ", #name);

#define TEST_ASSERT(condition) \
        if (!(condition)) { \
            printf("failed at line %d\n", __LINE__); \
            results->failed++; \
            return; \
        }

#define TEST_END() \
            printf("passed\n"); \
            results->passed++; \
        }

static bool is_literal(object_t* o) {
    return 1 == (1&(uintptr_t)o);
}

#define TEST_RUN(name) JOIN(test_, name) (&results);


#define L(number)           INTEGER_LITERAL_1(((number)<0?-1:0), ((number)<0?(uintptr_t)-(number):(uintptr_t)(number)))
#define BL1(sign, a)        INTEGER_LITERAL_1(sign, (a)
#define BL2(sign, a,b)      INTEGER_LITERAL_2(sign, (a), (b))
#define BL3(sign, a,b,c)    INTEGER_LITERAL_N(sign, 3, {INTEGER_LITERAL_N_2((a),(b)) INTEGER_LITERAL_SEP INTEGER_LITERAL_N_1((c))})
#define BL4(sign, a,b,c,d)  INTEGER_LITERAL_N(sign, 3, {INTEGER_LITERAL_N_2((a),(b)) INTEGER_LITERAL_SEP INTEGER_LITERAL_N_2((c), (d))})


#define TEST_ADD(result, left, right)   TEST_ASSERT(integer_test_eq(result, integer_add(left, right)))
#define TEST_SUB(result, left, right)   TEST_ASSERT(integer_test_eq(result, integer_sub(left, right)))
#define TEST_MUL(result, left, right)   TEST_ASSERT(integer_test_eq(result, integer_mul(left, right)))
#define TEST_DIV(result, left, right)   TEST_ASSERT(integer_test_eq(result, integer_div(left, right)))
#define TEST_REM(result, left, right)   TEST_ASSERT(integer_test_eq(result, integer_rem(left, right)))


TEST(tag_literals)
    TEST_ASSERT(is_literal(L(1)))
    TEST_ASSERT(is_literal(L(0)))
    TEST_ASSERT(is_literal(L(-1)))
#if WORD_SIZE == 64
    TEST_ASSERT(is_literal(BL2(0, 0,INT32_MAX/2)))
    TEST_ASSERT(!is_literal(BL2(0, 0,INT32_MAX/2+1)))
    TEST_ASSERT(is_literal(BL2(-1, 0,INT32_MAX/2+1)))
    TEST_ASSERT(!is_literal(BL2(-1, 0,INT32_MAX/2+2)))
#else
    TEST_ASSERT(is_literal(BL1(0, INT32_MAX/2)))
    TEST_ASSERT(!is_literal(BL1(0, INT32_MAX/2+1)))
    TEST_ASSERT(is_literal(BL1(-1, INT32_MAX/2+1)))
    TEST_ASSERT(!is_literal(BL1(-1, INT32_MAX/2+2)))
#endif
TEST_END()


TEST(conversions)
    int32_t x = integer_to_int32(INTEGER_LITERAL_1(0, 0));
TEST_END()


TEST(addition)
    TEST_ADD(L(21), L(20), L(1))
    TEST_ADD(BL3(0, 0,0,2), BL3(0, 0,0,1), BL3(0, 0,0,1))
    TEST_ADD(L(0), BL3(0, 0,0,1), BL3(-1, 0,0,1))
    TEST_ADD(BL3(0, 0,0,1), BL2(0, 0,0x80000000), BL2(0, 0,0x80000000))
    TEST_ADD(L(0), BL2(0, 0,0x80000000), BL2(-1, 0,0x80000000))
    TEST_ADD(L(-1), BL3(0, 0,0,0x80000000), BL3(-1, 1,0,0x80000000))
TEST_END()


TEST(subtraction)
    TEST_SUB(L(19), L(20), L(1))
    TEST_SUB(L(21), L(20), L(-1))
    TEST_SUB(L(-100), L(-50), L(50))
    TEST_SUB(BL3(-1, 0,3,0x80000000), BL3(-1,0,1,0x40000000), BL3(0,0,2,0x40000000))
TEST_END()


TEST(multiplication)
    TEST_MUL(L(100), L(10), L(10))
TEST_END()


TEST(division)
    TEST_DIV(L(1), L(10), L(10))
    TEST_DIV(L(10), BL4(0, 0,0,0,10), BL4(0, 0,0,0,1))
TEST_END()


TEST(remainder)
    TEST_REM(L(1), L(10), L(9))
    TEST_REM(L(10), BL3(0, 10,0,1), BL3(0, 0,0,1))
TEST_END()




struct test_gc_allocations_o {
    object_t parent;
    fun_t continuation;
    object_t* something;
    int32_t count;
};

static vtable_t test_gc_allocations_v = {
    .object_size = sizeof(struct test_gc_allocations_o),
    .array_el_size = 0,
    .object_pointer_locations = maskof(struct test_gc_allocations_o, .continuation.o),
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(integer_t, length),
    .implements_array = VTABLE_IMPLEMENTS(0),
};

static void test_gc_allocations_1(struct test_gc_allocations_o* heap) {
    fun_t next;
    if (--heap->count < 0) {
        next = heap->continuation;
    } else {
        for (int count2 = 1000; --count2 >= 0; ) {
            heap = (struct test_gc_allocations_o*)object_mutation((object_t*)heap);
            heap->something = string_allocate(100);
        }

        next = (fun_t){.f=test_gc_allocations_1, .o=heap};
    }

    worker_node_t* work = thread_work_prepare(next);
    thread_work_post_fast(work);
}

static void test_gc_allocations(object_t* self, fun_t continuation) {
    struct test_gc_allocations_o* heap = object_create((vtable_t*)&test_gc_allocations_v);
    heap->continuation = continuation;
    heap->something = NULL;
    heap->count = 1000000;

    worker_node_t* work = thread_work_prepare((fun_t){.f=test_gc_allocations_1, .o=heap});
    thread_work_post_fast(work);
}






static fun_t cheating_continuation;
static void otherthing(object_t* self)
{
    fun_t continuation = cheating_continuation;
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, INTEGER_LITERAL_1(0, 0));
}
static void init_thing(object_t* self, fun_t continuation)
{
    ((void(*)(object_t*))continuation.f)(continuation.o);
}
static object_t* lazy_flag;



static void entrypoint(object_t* self, fun_t continuation) {
    struct test_results results = {0, 0};

    TEST_RUN(tag_literals)
    TEST_RUN(conversions)
    TEST_RUN(addition)
    TEST_RUN(subtraction)
    TEST_RUN(multiplication)
    TEST_RUN(division)
    TEST_RUN(remainder)


    test_gc_allocations(NULL, continuation);

    // cheating_continuation = continuation;
    // worker_node_t* node = thread_work_prepare((fun_t){.f=otherthing,.o=NULL});
    // lazy_global_init(NULL, (object_t*)&lazy_flag, (fun_t){.f=init_thing,.o=NULL}, (fun_t){.f=otherthing, .o=NULL});
}


int main(int argc, char** argv) {
    previous_declare_roots = add_roots_declaration_func(declare_roots);
    thread_start(entrypoint);
}
