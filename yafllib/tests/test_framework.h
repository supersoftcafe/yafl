#pragma once

#include "../yafl.h"
#include <stdio.h>

struct test_results {
    int passed;
    int failed;
    const char* current_test;
};

#define TEST(name) \
    static void test_##name(struct test_results* _r) { \
        _r->current_test = #name; \
        printf("  %-50s ", #name); fflush(stdout);

#define TEST_END() \
        printf("OK\n"); \
        _r->passed++; \
    }

#define ASSERT(condition) \
    do { \
        if (!(condition)) { \
            printf("FAIL\n    line %d: " #condition "\n", __LINE__); \
            _r->failed++; \
            return; \
        } \
    } while (0)

#define ASSERT_EQ_I32(actual, expected) \
    do { \
        int32_t _a = (actual); int32_t _e = (expected); \
        if (_a != _e) { \
            printf("FAIL\n    line %d: expected %d, got %d\n", __LINE__, _e, _a); \
            _r->failed++; \
            return; \
        } \
    } while (0)

/* Compare two yafl integers for equality */
#define ASSERT_INT_EQ(actual, expected) \
    do { \
        if (!integer_test_eq((actual), (expected))) { \
            printf("FAIL\n    line %d: integers not equal\n", __LINE__); \
            _r->failed++; \
            return; \
        } \
    } while (0)

/* Assert a yafl integer equals a C int32 value */
#define ASSERT_INT_EQ_I32(actual, expected_i32) \
    do { \
        int32_t _v = integer_to_int32(actual); \
        if (_v != (expected_i32)) { \
            printf("FAIL\n    line %d: expected %d, got %d\n", __LINE__, (expected_i32), _v); \
            _r->failed++; \
            return; \
        } \
    } while (0)

#define ASSERT_STR_EQ(actual, expected_cstr) \
    do { \
        object_t* _exp = string_from_bytes((uint8_t*)(expected_cstr), \
                                           (int32_t)strlen(expected_cstr)); \
        if (string_compare((actual), _exp) != 0) { \
            printf("FAIL\n    line %d: string mismatch\n", __LINE__); \
            _r->failed++; \
            return; \
        } \
    } while (0)

#define RUN(name) test_##name(_r)

#define PRINT_RESULTS(suite_name, _r) \
    printf("%s: %d passed, %d failed\n\n", (suite_name), (_r)->passed, (_r)->failed)

/* Shorthand integer literals for tests */
#define I(n) INTEGER_LITERAL_1(((n)<0?-1:0), ((n)<0?(uintptr_t)(-(n)):(uintptr_t)(n)))
