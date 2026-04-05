
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

/* ---- short string boundary ---- */

TEST(short_string_max_length)
    /* sizeof(uintptr_t)-1 bytes fits in a tagged pointer;
       sizeof(uintptr_t) bytes must go to the heap. Correct on 32-bit and 64-bit. */
    static const uint8_t data[16] = "abcdefghijklmno";
    int32_t max_short = (int32_t)sizeof(uintptr_t) - 1;
    object_t* s_short = string_from_bytes((uint8_t*)data, max_short);
    object_t* s_heap  = string_from_bytes((uint8_t*)data, max_short + 1);
    ASSERT(PTR_IS_STRING(s_short));
    ASSERT(!PTR_IS_STRING(s_heap));
    ASSERT(PTR_IS_OBJECT(s_heap));
TEST_END()

TEST(short_string_binary_data)
    /* 3 high-bit bytes survive encode/decode through a tagged short string.
       3 < sizeof(uintptr_t) on both 32-bit (ptr=4) and 64-bit (ptr=8). */
    uint8_t src[3] = {0x80, 0xFF, 0x01};
    object_t* s = string_from_bytes(src, 3);
    ASSERT(PTR_IS_STRING(s));
    ASSERT_EQ_I32(string_length(s), 3);
    char buf[8];
    string_copy_cstr(s, buf, (int32_t)sizeof(buf));
    ASSERT((uint8_t)buf[0] == 0x80);
    ASSERT((uint8_t)buf[1] == 0xFF);
    ASSERT((uint8_t)buf[2] == 0x01);
TEST_END()

TEST(append_to_short_boundary)
    /* Two pieces summing to exactly sizeof(uintptr_t)-1 bytes produce a tagged
       short string; one byte more produces a heap string.
       Correct on 32-bit (max_short=3) and 64-bit (max_short=7). */
    static const uint8_t data[16] = "abcdefghijklmno";
    int32_t max_short = (int32_t)sizeof(uintptr_t) - 1;
    int32_t half      = max_short / 2;

    object_t* a = string_from_bytes((uint8_t*)data,        half);
    object_t* b = string_from_bytes((uint8_t*)data + half, max_short - half);
    object_t* c = string_from_bytes((uint8_t*)data,        half + 1);

    object_t* at_boundary   = string_append(a, b);   /* exactly max_short bytes */
    object_t* over_boundary = string_append(c, b);   /* max_short + 1 bytes */

    ASSERT(PTR_IS_STRING(at_boundary));
    ASSERT(!PTR_IS_STRING(over_boundary));
    ASSERT_EQ_I32(string_length(at_boundary),   max_short);
    ASSERT_EQ_I32(string_length(over_boundary), max_short + 1);
TEST_END()

/* ---- slice of short string ---- */

TEST(slice_short_string)
    /* Slice must work when the source is a tagged short string. */
    uint8_t data[3] = {'x', 'y', 'z'};
    object_t* s = string_from_bytes(data, 3);  /* 3 < sizeof(uintptr_t) always */
    ASSERT(PTR_IS_STRING(s));
    object_t* prefix = string_slice(s, I(0), I(2));
    ASSERT_STR_EQ(prefix, "xy");
    object_t* mid = string_slice(s, I(1), I(2));
    ASSERT_STR_EQ(mid, "y");
TEST_END()

/* ---- compare with embedded NUL bytes ---- */

TEST(compare_strings_with_embedded_nul)
    /* string_compare must compare by byte content and length, not stop at NUL.
       4-byte strings: heap on 32-bit (4 >= sizeof(uintptr_t)), tagged on 64-bit.
       Both representations must preserve embedded NUL bytes. */
    uint8_t a_bytes[4] = {0x61, 0x00, 0x62, 0x63};   /* "a\0bc" */
    uint8_t b_bytes[4] = {0x61, 0x00, 0x62, 0x64};   /* "a\0bd" */
    uint8_t c_bytes[4] = {0x61, 0x00, 0x62, 0x63};   /* "a\0bc" */

    object_t* sa = string_from_bytes(a_bytes, 4);
    object_t* sb = string_from_bytes(b_bytes, 4);
    object_t* sc = string_from_bytes(c_bytes, 4);

    ASSERT(string_compare(sa, sc) == 0);
    ASSERT(string_compare(sa, sb) < 0);
    ASSERT(string_compare(sb, sa) > 0);
TEST_END()

/* ---- string_truncate ---- */

TEST(truncate_heap_to_heap)
    /* Truncating a heap string to a length still >= sizeof(uintptr_t) keeps it
       as a heap object, adjusts length in-place, and returns the same pointer. */
    const char* src = "abcdefghijklmnopqrst";   /* 20 bytes, heap on all platforms */
    object_t* s = string_from_bytes((uint8_t*)src, 20);
    ASSERT(PTR_IS_OBJECT(s));
    object_t* r = string_truncate(s, 10);
    ASSERT(PTR_IS_OBJECT(r));
    ASSERT(r == s);
    ASSERT_EQ_I32(string_length(r), 10);
    ASSERT_STR_EQ(r, "abcdefghij");
TEST_END()

TEST(truncate_heap_to_short)
    /* Truncating a heap string to < sizeof(uintptr_t) bytes produces a tagged
       short string. Uses sizeof(uintptr_t)-1 as target so it is correct on
       both 32-bit and 64-bit. */
    const char* src = "abcdefghijklmnopqrst";   /* 20 bytes, heap on all platforms */
    int32_t short_len = (int32_t)sizeof(uintptr_t) - 1;
    object_t* s = string_from_bytes((uint8_t*)src, 20);
    ASSERT(PTR_IS_OBJECT(s));
    object_t* r = string_truncate(s, short_len);
    ASSERT(PTR_IS_STRING(r));
    ASSERT_EQ_I32(string_length(r), short_len);
    object_t* expected = string_from_bytes((uint8_t*)src, short_len);
    ASSERT(string_compare(r, expected) == 0);
TEST_END()

/* ---- string_copy_cstr ---- */

TEST(copy_cstr_fits_in_buffer)
    /* Returns the full length and NUL-terminates, including for tagged strings. */
    object_t* s = STR("hello");
    char buf[64];
    int32_t len = string_copy_cstr(s, buf, (int32_t)sizeof(buf));
    ASSERT_EQ_I32(len, 5);
    ASSERT(buf[0]=='h' && buf[1]=='e' && buf[2]=='l' && buf[3]=='l' && buf[4]=='o');
    ASSERT(buf[5] == 0);
TEST_END()

TEST(copy_cstr_truncates_to_buffer)
    /* When buf_size < string length, copies buf_size-1 bytes and NUL-terminates.
       The return value is still the FULL original length. */
    const char* text = "hello world";   /* 11 bytes */
    object_t* s = string_from_bytes((uint8_t*)text, 11);
    char buf[5];
    int32_t len = string_copy_cstr(s, buf, (int32_t)sizeof(buf));
    ASSERT_EQ_I32(len, 11);
    ASSERT(buf[0]=='h' && buf[1]=='e' && buf[2]=='l' && buf[3]=='l');
    ASSERT(buf[4] == 0);
TEST_END()

/* ---- wchar UTF-8 encoding boundaries ---- */

TEST(wchar_boundary_1byte_max)
    /* U+007F: last codepoint with single-byte encoding (0x7F) */
    object_t* s = wchar_to_string(I(0x7F));
    ASSERT_EQ_I32(string_length(s), 1);
    char data[8]; string_copy_cstr(s, data, (int32_t)sizeof(data));
    ASSERT((uint8_t)data[0] == 0x7F);
TEST_END()

TEST(wchar_boundary_2byte_min)
    /* U+0080: first codepoint requiring 2-byte encoding (0xC2 0x80) */
    object_t* s = wchar_to_string(I(0x80));
    ASSERT_EQ_I32(string_length(s), 2);
    char data[8]; string_copy_cstr(s, data, (int32_t)sizeof(data));
    ASSERT((uint8_t)data[0] == 0xC2);
    ASSERT((uint8_t)data[1] == 0x80);
TEST_END()

TEST(wchar_boundary_2byte_max)
    /* U+07FF: last codepoint in the 2-byte range (0xDF 0xBF) */
    object_t* s = wchar_to_string(I(0x7FF));
    ASSERT_EQ_I32(string_length(s), 2);
    char data[8]; string_copy_cstr(s, data, (int32_t)sizeof(data));
    ASSERT((uint8_t)data[0] == 0xDF);
    ASSERT((uint8_t)data[1] == 0xBF);
TEST_END()

TEST(wchar_boundary_3byte_min)
    /* U+0800: first codepoint requiring 3-byte encoding (0xE0 0xA0 0x80) */
    object_t* s = wchar_to_string(I(0x800));
    ASSERT_EQ_I32(string_length(s), 3);
    char data[8]; string_copy_cstr(s, data, (int32_t)sizeof(data));
    ASSERT((uint8_t)data[0] == 0xE0);
    ASSERT((uint8_t)data[1] == 0xA0);
    ASSERT((uint8_t)data[2] == 0x80);
TEST_END()

TEST(wchar_boundary_3byte_max)
    /* U+FFFF: last codepoint in the 3-byte range (0xEF 0xBF 0xBF) */
    object_t* s = wchar_to_string(I(0xFFFF));
    ASSERT_EQ_I32(string_length(s), 3);
    char data[8]; string_copy_cstr(s, data, (int32_t)sizeof(data));
    ASSERT((uint8_t)data[0] == 0xEF);
    ASSERT((uint8_t)data[1] == 0xBF);
    ASSERT((uint8_t)data[2] == 0xBF);
TEST_END()

TEST(wchar_boundary_4byte_min)
    /* U+10000: first codepoint requiring 4-byte encoding (0xF0 0x90 0x80 0x80) */
    object_t* s = wchar_to_string(I(0x10000));
    ASSERT_EQ_I32(string_length(s), 4);
    char data[8]; string_copy_cstr(s, data, (int32_t)sizeof(data));
    ASSERT((uint8_t)data[0] == 0xF0);
    ASSERT((uint8_t)data[1] == 0x90);
    ASSERT((uint8_t)data[2] == 0x80);
    ASSERT((uint8_t)data[3] == 0x80);
TEST_END()

TEST(wchar_boundary_4byte_max)
    /* U+10FFFF: last valid Unicode codepoint (0xF4 0x8F 0xBF 0xBF) */
    object_t* s = wchar_to_string(I(0x10FFFF));
    ASSERT_EQ_I32(string_length(s), 4);
    char data[8]; string_copy_cstr(s, data, (int32_t)sizeof(data));
    ASSERT((uint8_t)data[0] == 0xF4);
    ASSERT((uint8_t)data[1] == 0x8F);
    ASSERT((uint8_t)data[2] == 0xBF);
    ASSERT((uint8_t)data[3] == 0xBF);
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

    /* short string boundary */
    RUN(short_string_max_length);
    RUN(short_string_binary_data);
    RUN(append_to_short_boundary);

    /* slice short */
    RUN(slice_short_string);

    /* compare with NUL */
    RUN(compare_strings_with_embedded_nul);

    /* truncate */
    RUN(truncate_heap_to_heap);
    RUN(truncate_heap_to_short);

    /* copy_cstr */
    RUN(copy_cstr_fits_in_buffer);
    RUN(copy_cstr_truncates_to_buffer);

    /* wchar boundaries */
    RUN(wchar_boundary_1byte_max);
    RUN(wchar_boundary_2byte_min);
    RUN(wchar_boundary_2byte_max);
    RUN(wchar_boundary_3byte_min);
    RUN(wchar_boundary_3byte_max);
    RUN(wchar_boundary_4byte_min);
    RUN(wchar_boundary_4byte_max);

    PRINT_RESULTS("string", _r);

    object_t* status = integer_create_from_int32(r.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, status);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
