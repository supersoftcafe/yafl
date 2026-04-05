
#include "test_framework.h"
#include <string.h>


/* ---- short string tagging ---- */

TEST(str_literal_macro_tagged)
    /* STR() should produce a tagged short string for short content */
    object_t* s = STR("hi");
    ASSERT(PTR_IS_STRING(s));
    ASSERT(!PTR_IS_OBJECT(s));
TEST_END()

TEST(str_literal_macro_heap_for_long)
    /* A string longer than MAX_SHORT_LEN must be a heap object */
    object_t* s = STR("this is definitely too long to fit inline");
    ASSERT(PTR_IS_OBJECT(s));
    ASSERT(!PTR_IS_STRING(s));
TEST_END()

TEST(str_length_short)
    object_t* s = STR("hi");
    ASSERT_EQ_I32(string_length(s), 2);
TEST_END()

TEST(str_length_empty)
    object_t* s = STR("");
    ASSERT_EQ_I32(string_length(s), 0);
TEST_END()

TEST(str_length_heap)
    object_t* s = STR("hello, world!");
    ASSERT_EQ_I32(string_length(s), 13);
TEST_END()

/* ---- string_from_bytes ---- */

TEST(create_from_bytes_short_tagged)
    uint8_t data[] = "hi";
    object_t* s = string_from_bytes(data, 2);
    ASSERT(PTR_IS_STRING(s));
TEST_END()

TEST(create_from_bytes_short_content)
    uint8_t data[] = "hi";
    object_t* s = string_from_bytes(data, 2);
    ASSERT_STR_EQ(s, "hi");
TEST_END()

TEST(create_from_bytes_long_heap)
    uint8_t data[] = "this is definitely too long to fit inline";
    int32_t len = (int32_t)strlen((char*)data);
    object_t* s = string_from_bytes(data, len);
    ASSERT(PTR_IS_OBJECT(s));
TEST_END()

TEST(create_from_bytes_long_content)
    const char* text = "this is definitely too long to fit inline";
    object_t* s = string_from_bytes((uint8_t*)text, (int32_t)strlen(text));
    ASSERT_STR_EQ(s, text);
TEST_END()

TEST(create_from_bytes_single_char)
    uint8_t data[] = "X";
    object_t* s = string_from_bytes(data, 1);
    ASSERT_STR_EQ(s, "X");
TEST_END()

/* ---- string_append ---- */

TEST(append_two_short_result)
    object_t* a = STR("ab");
    object_t* b = STR("cd");
    object_t* r = string_append(a, b);
    ASSERT_STR_EQ(r, "abcd");
TEST_END()

TEST(append_short_and_long)
    object_t* a = STR("Hello, ");
    object_t* b = STR("world!");
    object_t* r = string_append(a, b);
    ASSERT_STR_EQ(r, "Hello, world!");
TEST_END()

TEST(append_empty_left)
    object_t* a = STR("");
    object_t* b = STR("hello");
    object_t* r = string_append(a, b);
    ASSERT_STR_EQ(r, "hello");
TEST_END()

TEST(append_empty_right)
    object_t* a = STR("hello");
    object_t* b = STR("");
    object_t* r = string_append(a, b);
    ASSERT_STR_EQ(r, "hello");
TEST_END()

TEST(append_two_long)
    object_t* a = STR("Fred and bill went on a ride ");
    object_t* b = STR("together in the jeep.");
    object_t* r = string_append(a, b);
    ASSERT_STR_EQ(r, "Fred and bill went on a ride together in the jeep.");
TEST_END()

TEST(append_length)
    object_t* a = STR("abc");
    object_t* b = STR("de");
    object_t* r = string_append(a, b);
    ASSERT_EQ_I32(string_length(r), 5);
TEST_END()

/* ---- string_allocate ---- */

TEST(allocate_gives_heap_object)
    object_t* s = string_allocate(20);
    ASSERT(PTR_IS_OBJECT(s));
    ASSERT_EQ_I32(string_length(s), 20);
TEST_END()

/* ---- string_slice ---- */

TEST(slice_full_range)
    object_t* s = STR("hello");
    object_t* r = string_slice(s, I(0), I(5));
    ASSERT_STR_EQ(r, "hello");
TEST_END()

TEST(slice_prefix)
    object_t* s = STR("hello");
    object_t* r = string_slice(s, I(0), I(3));
    ASSERT_STR_EQ(r, "hel");
TEST_END()

TEST(slice_suffix)
    object_t* s = STR("hello");
    object_t* r = string_slice(s, I(2), I(5));
    ASSERT_STR_EQ(r, "llo");
TEST_END()

TEST(slice_empty_result)
    object_t* s = STR("hello");
    object_t* r = string_slice(s, I(2), I(2));
    ASSERT_EQ_I32(string_length(r), 0);
TEST_END()

TEST(slice_inverted_clamps_to_empty)
    object_t* s = STR("hello");
    object_t* r = string_slice(s, I(4), I(2));
    ASSERT_EQ_I32(string_length(r), 0);
TEST_END()

TEST(slice_clamps_beyond_end)
    object_t* s = STR("hello");
    object_t* r = string_slice(s, I(0), I(100));
    ASSERT_STR_EQ(r, "hello");
TEST_END()

TEST(slice_clamps_negative_start)
    object_t* s = STR("hello");
    object_t* r = string_slice(s, I(-5), I(3));
    ASSERT_STR_EQ(r, "hel");
TEST_END()

/* ---- string_compare ---- */

TEST(compare_equal_strings)
    object_t* a = STR("hello");
    object_t* b = STR("hello");
    ASSERT_EQ_I32(string_compare(a, b), 0);
TEST_END()

TEST(compare_less_than)
    object_t* a = STR("abc");
    object_t* b = STR("abd");
    ASSERT(string_compare(a, b) < 0);
TEST_END()

TEST(compare_greater_than)
    object_t* a = STR("abd");
    object_t* b = STR("abc");
    ASSERT(string_compare(a, b) > 0);
TEST_END()

TEST(compare_shorter_less_than_longer)
    object_t* a = STR("abc");
    object_t* b = STR("abcd");
    ASSERT(string_compare(a, b) < 0);
TEST_END()

TEST(compare_longer_greater_than_shorter)
    object_t* a = STR("abcd");
    object_t* b = STR("abc");
    ASSERT(string_compare(a, b) > 0);
TEST_END()

TEST(compare_empty_strings)
    object_t* a = STR("");
    object_t* b = STR("");
    ASSERT_EQ_I32(string_compare(a, b), 0);
TEST_END()

/* ---- wchar_to_string ---- */

TEST(wchar_ascii)
    /* 'A' = 0x41, 1-byte UTF-8 */
    object_t* s = wchar_to_string(I(0x41));
    ASSERT_STR_EQ(s, "A");
    ASSERT_EQ_I32(string_length(s), 1);
TEST_END()

TEST(wchar_two_byte)
    /* U+00E9 = 'é', encodes as 0xC3 0xA9 */
    object_t* s = wchar_to_string(I(0xE9));
    ASSERT_EQ_I32(string_length(s), 2);
    char data[8]; string_copy_cstr(s, data, sizeof(data));
    ASSERT((uint8_t)data[0] == 0xC3);
    ASSERT((uint8_t)data[1] == 0xA9);
TEST_END()

TEST(wchar_three_byte)
    /* U+4E2D = '中', encodes as 0xE4 0xB8 0xAD */
    object_t* s = wchar_to_string(I(0x4E2D));
    ASSERT_EQ_I32(string_length(s), 3);
    char data[8]; string_copy_cstr(s, data, sizeof(data));
    ASSERT((uint8_t)data[0] == 0xE4);
    ASSERT((uint8_t)data[1] == 0xB8);
    ASSERT((uint8_t)data[2] == 0xAD);
TEST_END()

TEST(wchar_four_byte)
    /* U+1F600 = emoji, encodes as 0xF0 0x9F 0x98 0x80 */
    object_t* s = wchar_to_string(I(0x1F600));
    ASSERT_EQ_I32(string_length(s), 4);
    char data[8]; string_copy_cstr(s, data, sizeof(data));
    ASSERT((uint8_t)data[0] == 0xF0);
    ASSERT((uint8_t)data[1] == 0x9F);
    ASSERT((uint8_t)data[2] == 0x98);
    ASSERT((uint8_t)data[3] == 0x80);
TEST_END()

/* ---- entrypoint ---- */

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) { prev_roots(declare); }

static void run_tests(object_t* _, fun_t continuation) {
    struct test_results r = {0, 0, NULL};
    struct test_results* _r = &r;

    printf("=== string tests ===\n");

    /* tagging */
    RUN(str_literal_macro_tagged);
    RUN(str_literal_macro_heap_for_long);
    RUN(str_length_short);
    RUN(str_length_empty);
    RUN(str_length_heap);

    /* string_from_bytes */
    RUN(create_from_bytes_short_tagged);
    RUN(create_from_bytes_short_content);
    RUN(create_from_bytes_long_heap);
    RUN(create_from_bytes_long_content);
    RUN(create_from_bytes_single_char);

    /* append */
    RUN(append_two_short_result);
    RUN(append_short_and_long);
    RUN(append_empty_left);
    RUN(append_empty_right);
    RUN(append_two_long);
    RUN(append_length);

    /* allocate */
    RUN(allocate_gives_heap_object);

    /* slice */
    RUN(slice_full_range);
    RUN(slice_prefix);
    RUN(slice_suffix);
    RUN(slice_empty_result);
    RUN(slice_inverted_clamps_to_empty);
    RUN(slice_clamps_beyond_end);
    RUN(slice_clamps_negative_start);

    /* compare */
    RUN(compare_equal_strings);
    RUN(compare_less_than);
    RUN(compare_greater_than);
    RUN(compare_shorter_less_than_longer);
    RUN(compare_longer_greater_than_shorter);
    RUN(compare_empty_strings);

    /* wchar */
    RUN(wchar_ascii);
    RUN(wchar_two_byte);
    RUN(wchar_three_byte);
    RUN(wchar_four_byte);

    PRINT_RESULTS("string", _r);

    object_t* status = integer_create_from_int32(r.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, status);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
