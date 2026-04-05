
#include "test_framework.h"
#include <stdio.h>
EXTERN object_t* io_stdin (void* self);
EXTERN object_t* io_stdout(void* self);
EXTERN object_t* io_stderr(void* self);
EXTERN object_t* io_create    (void* self, object_t* path);
EXTERN object_t* io_open_read (void* self, object_t* path);
EXTERN object_t* io_open_write(void* self, object_t* path, bool truncate);
EXTERN object_t* io_read (void* self, int32_t length);
EXTERN object_t* io_write(void* self, object_t* data);
EXTERN object_t* io_close(void* self);

static object_t* TMP_PATH;

#define ASSERT_IS_NEG_INT(v) \
    do { \
        object_t* _v = (v); \
        if (!PTR_IS_INTEGER(_v) || integer_to_int32(_v) >= 0) { \
            printf("FAIL\n    line %d: expected negative integer\n", __LINE__); \
            _r->failed++; \
            return; \
        } \
    } while (0)

/* ---- constructors ---- */

TEST(stdout_returns_object)
    object_t* io = io_stdout(NULL);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
TEST_END()

TEST(stderr_returns_object)
    object_t* io = io_stderr(NULL);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
TEST_END()

TEST(stdin_returns_object)
    object_t* io = io_stdin(NULL);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
TEST_END()

TEST(create_returns_object)
    object_t* io = io_create(NULL, TMP_PATH);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
    io_close(io);
TEST_END()

TEST(create_bad_path_returns_neg_int)
    object_t* r = io_create(NULL, STR("/no/such/directory/file.tmp"));
    ASSERT_IS_NEG_INT(r);
TEST_END()

TEST(open_read_bad_path_returns_neg_int)
    object_t* r = io_open_read(NULL, STR("/no/such/file_yafl_test.tmp"));
    ASSERT_IS_NEG_INT(r);
TEST_END()

TEST(open_read_returns_object)
    object_t* w = io_create(NULL, TMP_PATH);
    io_close(w);
    object_t* io = io_open_read(NULL, TMP_PATH);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
    io_close(io);
TEST_END()

TEST(open_write_truncate_returns_object)
    object_t* io = io_open_write(NULL, TMP_PATH, true);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
    io_close(io);
TEST_END()

TEST(open_write_append_returns_object)
    object_t* io = io_open_write(NULL, TMP_PATH, false);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
    io_close(io);
TEST_END()

/* ---- write ---- */

TEST(write_returns_byte_count)
    object_t* io = io_create(NULL, TMP_PATH);
    object_t* n = io_write(io, STR("hello"));
    ASSERT(PTR_IS_INTEGER(n));
    ASSERT_EQ_I32(integer_to_int32(n), 5);
    io_close(io);
TEST_END()

TEST(write_short_string_byte_count)
    /* "hi" is a short (tagged) string — exercises the tagged-pointer path */
    ASSERT(PTR_IS_STRING(STR("hi")));
    object_t* io = io_create(NULL, TMP_PATH);
    object_t* n = io_write(io, STR("hi"));
    ASSERT_EQ_I32(integer_to_int32(n), 2);
    io_close(io);
TEST_END()

TEST(write_closed_returns_null)
    object_t* io = io_create(NULL, TMP_PATH);
    io_close(io);
    object_t* r = io_write(io, STR("hello"));
    ASSERT(r == NULL);
TEST_END()

/* ---- close ---- */

TEST(close_returns_null)
    object_t* io = io_create(NULL, TMP_PATH);
    object_t* r = io_close(io);
    ASSERT(r == NULL);
TEST_END()

TEST(close_idempotent)
    object_t* io = io_create(NULL, TMP_PATH);
    io_close(io);
    object_t* r = io_close(io);
    ASSERT(r == NULL);
TEST_END()

/* ---- read ---- */

TEST(read_bad_length_zero_returns_neg_int)
    object_t* io = io_create(NULL, TMP_PATH);
    object_t* r = io_read(io, 0);
    ASSERT_IS_NEG_INT(r);
    io_close(io);
TEST_END()

TEST(read_bad_length_negative_returns_neg_int)
    object_t* io = io_create(NULL, TMP_PATH);
    object_t* r = io_read(io, -1);
    ASSERT_IS_NEG_INT(r);
    io_close(io);
TEST_END()

TEST(read_closed_returns_null)
    object_t* io = io_create(NULL, TMP_PATH);
    io_close(io);
    object_t* r = io_read(io, 16);
    ASSERT(r == NULL);
TEST_END()

TEST(read_eof_returns_null)
    object_t* w = io_create(NULL, TMP_PATH);
    io_close(w);
    object_t* io = io_open_read(NULL, TMP_PATH);
    object_t* r = io_read(io, 16);
    ASSERT(r == NULL);
    io_close(io);
TEST_END()

/* ---- round-trips ---- */

TEST(write_read_roundtrip)
    object_t* w = io_create(NULL, TMP_PATH);
    io_write(w, STR("hello world"));
    io_close(w);

    object_t* r = io_open_read(NULL, TMP_PATH);
    object_t* data = io_read(r, 11);
    ASSERT_STR_EQ(data, "hello world");
    io_close(r);
TEST_END()

TEST(read_partial_then_rest)
    object_t* w = io_create(NULL, TMP_PATH);
    io_write(w, STR("hello world"));
    io_close(w);

    object_t* r = io_open_read(NULL, TMP_PATH);
    object_t* part1 = io_read(r, 5);
    ASSERT_STR_EQ(part1, "hello");
    object_t* part2 = io_read(r, 6);
    ASSERT_STR_EQ(part2, " world");
    object_t* eof = io_read(r, 16);
    ASSERT(eof == NULL);
    io_close(r);
TEST_END()

TEST(write_append_roundtrip)
    object_t* w = io_create(NULL, TMP_PATH);
    io_write(w, STR("hello"));
    io_close(w);

    object_t* a = io_open_write(NULL, TMP_PATH, false);
    io_write(a, STR(" world"));
    io_close(a);

    object_t* r = io_open_read(NULL, TMP_PATH);
    object_t* data = io_read(r, 11);
    ASSERT_STR_EQ(data, "hello world");
    io_close(r);
TEST_END()

TEST(write_truncate_clears_content)
    object_t* w = io_create(NULL, TMP_PATH);
    io_write(w, STR("hello world"));
    io_close(w);

    object_t* t = io_open_write(NULL, TMP_PATH, true);
    io_write(t, STR("hi"));
    io_close(t);

    object_t* r = io_open_read(NULL, TMP_PATH);
    object_t* data = io_read(r, 64);
    ASSERT_STR_EQ(data, "hi");
    io_close(r);
TEST_END()

/* ---- large read (> 32-byte stack buffer) ---- */

TEST(read_large_allocation_path)
    /* io_read with length > 32 takes the heap-allocation + string_truncate path.
       Verify the content round-trips correctly. */
    const char* payload = "0123456789abcdefghij0123456789abcdefghij"; /* 40 bytes */
    object_t* w = io_create(NULL, TMP_PATH);
    io_write(w, string_from_bytes((uint8_t*)payload, 40));
    io_close(w);

    object_t* r = io_open_read(NULL, TMP_PATH);
    object_t* data = io_read(r, 40);
    ASSERT(data != NULL);
    ASSERT_EQ_I32(string_length(data), 40);
    ASSERT_STR_EQ(data, payload);
    io_close(r);
TEST_END()

TEST(read_exact_file_size)
    /* Reading exactly the number of bytes in the file returns the data, and the
       immediately following read returns NULL (clean EOF, no partial read). */
    object_t* w = io_create(NULL, TMP_PATH);
    io_write(w, STR("hello"));
    io_close(w);

    object_t* r = io_open_read(NULL, TMP_PATH);
    object_t* data = io_read(r, 5);
    ASSERT_STR_EQ(data, "hello");
    object_t* eof = io_read(r, 5);
    ASSERT(eof == NULL);
    io_close(r);
TEST_END()

TEST(write_empty_string)
    /* Writing a zero-length string returns 0, not an error. */
    object_t* io = io_create(NULL, TMP_PATH);
    object_t* n = io_write(io, STR(""));
    ASSERT(PTR_IS_INTEGER(n));
    ASSERT_EQ_I32(integer_to_int32(n), 0);
    io_close(io);
TEST_END()

TEST(open_write_append_creates_nonexistent)
    /* io_open_write with truncate=false (append mode) creates the file if it
       does not already exist. */
    const char* new_cstr = "/tmp/yafl_test_io_new.tmp";
    object_t*   new_path = STR("/tmp/yafl_test_io_new.tmp");
    remove(new_cstr);
    object_t* io = io_open_write(NULL, new_path, false);
    ASSERT(io != NULL && PTR_IS_OBJECT(io));
    io_close(io);
    object_t* verify = io_open_read(NULL, new_path);
    ASSERT(verify != NULL && PTR_IS_OBJECT(verify));
    io_close(verify);
    remove(new_cstr);
TEST_END()

TEST(read_closed_returns_null_twice)
    /* Repeated reads on a closed file both return NULL without crashing. */
    object_t* io = io_create(NULL, TMP_PATH);
    io_close(io);
    ASSERT(io_read(io, 16) == NULL);
    ASSERT(io_read(io, 16) == NULL);
TEST_END()

/* ---- entrypoint ---- */

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    declare(&TMP_PATH);
}

static void run_tests(object_t* _, fun_t continuation) {
    struct test_results r = {0, 0, NULL};
    struct test_results* _r = &r;

    TMP_PATH = STR("/tmp/yafl_test_io.tmp");

    printf("=== io tests ===\n");

    /* constructors */
    RUN(stdout_returns_object);
    RUN(stderr_returns_object);
    RUN(stdin_returns_object);
    RUN(create_returns_object);
    RUN(create_bad_path_returns_neg_int);
    RUN(open_read_bad_path_returns_neg_int);
    RUN(open_read_returns_object);
    RUN(open_write_truncate_returns_object);
    RUN(open_write_append_returns_object);

    /* write */
    RUN(write_returns_byte_count);
    RUN(write_short_string_byte_count);
    RUN(write_closed_returns_null);

    /* close */
    RUN(close_returns_null);
    RUN(close_idempotent);

    /* read */
    RUN(read_bad_length_zero_returns_neg_int);
    RUN(read_bad_length_negative_returns_neg_int);
    RUN(read_closed_returns_null);
    RUN(read_eof_returns_null);

    /* round-trips */
    RUN(write_read_roundtrip);
    RUN(read_partial_then_rest);
    RUN(write_append_roundtrip);
    RUN(write_truncate_clears_content);

    /* large read / boundary / edge cases */
    RUN(read_large_allocation_path);
    RUN(read_exact_file_size);
    RUN(write_empty_string);
    RUN(open_write_append_creates_nonexistent);
    RUN(read_closed_returns_null_twice);

    PRINT_RESULTS("io", _r);

    object_t* status = integer_create_from_int32(r.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, status);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
