
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
    int32_t length;
    _Atomic(int32_t) result_counter;
    fun_t continuation;
    string_t* results[16];
};

static vtable_t test_gc_allocations_v = {
    .object_size = offsetof(struct test_gc_allocations_o, results[0]),
    .array_el_size = sizeof(string_t*),
    .object_pointer_locations = maskof(struct test_gc_allocations_o, .continuation.o),
    .array_el_pointer_locations = maskof(string_t*, ),
    .functions_mask = 0,
    .array_len_offset = offsetof(integer_t, length),
    .is_mutable = 1,
    .name = "test_gc_allocations",
    .implements_array = VTABLE_IMPLEMENTS(0),
};


static object_t* left_str = STR("Fred and bill went on a ride ");
static object_t* right_str = STR("together in the jeep.");
static const char* test_str = "Fred and bill went on a ride together in the jeep.";


static void complete_allocation_test(struct test_gc_allocations_o* self, string_t* result) {
    int32_t count = atomic_fetch_sub(&self->result_counter, 1) - 1;
    self->results[count] = result;
    if (count == 0) {
        fun_t continuation = self->continuation;
        ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, INTEGER_LITERAL_1(0, 0));
    }
}

static void do_allocation_test(struct test_gc_allocations_o* self) {
    struct test_gc_allocations_o* array[10] = {NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL};

    for (int count = 0; count < 10; ++count) {
        struct test_gc_allocations_o* obj = (struct test_gc_allocations_o*)array_create((vtable_t*)&test_gc_allocations_v, 3);
        array[count%10] = obj;
    }

    for (int count = 0; count < 1000; ++count) {
        struct test_gc_allocations_o* obj;

        for (int count2 = 0; count2 < 1000; ++count2) {
            string_t* str = (string_t*)string_append(left_str, right_str);
            obj = (struct test_gc_allocations_o*)array[count2%10];
            if (obj != NULL) {
                int i = (count ^ count2) % 3;
                object_set_reference((object_t*)obj, offsetof(struct test_gc_allocations_o, results[i]), (object_t*)str);
            }
        }

        for (int index = 0; index < 10; ++index) {
            obj = (struct test_gc_allocations_o*)array[index];

            if (obj != NULL) {
                assert(obj->results[0] == NULL || strcmp((char*)obj->results[0]->array, test_str) == 0);
                assert(obj->results[1] == NULL || strcmp((char*)obj->results[1]->array, test_str) == 0);
                assert(obj->results[2] == NULL || strcmp((char*)obj->results[2]->array, test_str) == 0);
            }
        }
    }

    complete_allocation_test(self, array[3]->results[0]);

    // TODO: Add an object name to the vtable header using a YAFL string
    //       Prints only the objects that survived the last GC, otherwise it could get quite noisy in the console
    // object_gc_print_heap();
}

void setup_allocation_test(object_t* _, fun_t continuation) {
    int32_t count = 1000;

    struct test_gc_allocations_o* o = (struct test_gc_allocations_o*)array_create(&test_gc_allocations_v, count);
    o->continuation = continuation;
    o->result_counter = count;

    while (--count >= 0) {
        worker_node_t* node = thread_work_prepare((fun_t){.f=do_allocation_test,.o=(object_t*)o});
        thread_work_post_fast(node);
    }
}




static void entrypoint(object_t* self, fun_t continuation) {
    struct test_results results = {0, 0};

    TEST_RUN(tag_literals)
    TEST_RUN(conversions)
    TEST_RUN(addition)
    TEST_RUN(subtraction)
    TEST_RUN(multiplication)
    TEST_RUN(division)
    TEST_RUN(remainder)

    setup_allocation_test(NULL, continuation);



    // ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, INTEGER_LITERAL_1(0, 0));


    // cheating_continuation = continuation;
    // worker_node_t* node = thread_work_prepare((fun_t){.f=otherthing,.o=NULL});
    // lazy_global_init(NULL, (object_t*)&lazy_flag, (fun_t){.f=init_thing,.o=NULL}, (fun_t){.f=otherthing, .o=NULL});
}


int main(int argc, char** argv) {
    previous_declare_roots = add_roots_declaration_func(declare_roots);
    thread_start(entrypoint);
}
