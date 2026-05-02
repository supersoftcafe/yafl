
#include "test_framework.h"
#include <stdio.h>
#include <string.h>

EXTERN object_t* io_stdin (object_t* self);
EXTERN object_t* io_stdout(object_t* self);
EXTERN object_t* io_stderr(object_t* self);
EXTERN object_t* io_create    (object_t* self, object_t* path);
EXTERN object_t* io_open_read (object_t* self, object_t* path);
EXTERN object_t* io_open_write(object_t* self, object_t* path, bool truncate);
EXTERN object_t* io_read (object_t* self, object_t* length);
EXTERN object_t* io_write(object_t* self, object_t* data);
EXTERN object_t* io_close(object_t* self);

// ---- CPS helper --------------------------------------------------------
//
// `then(result, next)`: if `result` is a task, register a trampoline that
// will call `next(result_value)` when the task completes; if `result` is
// already a plain value, call `next(result)` inline. Uses a single slot
// because tests run sequentially.

static void (*_next_step)(object_t*);
// GC root for the task we're awaiting. Without this, the io_t and its
// in-flight job are unrooted between dispatch and the caller storing the
// result, and a GC cycle in that window collects them. (The library's
// io_t.in_flight rooting only protects the job *given* io_t is itself
// reachable; here the test driver IS the io_t's only root.)
static object_t* _in_flight_task;

static object_t* _trampoline(object_t* self_unused, object_t* task) {
    object_t* value = ((task_obj_t*)task)->result;
    void (*next)(object_t*) = _next_step;
    _next_step = NULL;
    _in_flight_task = NULL;
    next(value);
    return NULL;
}

static void then(object_t* result, void (*next)(object_t*)) {
    if (!((uintptr_t)result & PTR_TAG_TASK)) {
        next(result);
        return;
    }
    _next_step = next;
    task_obj_t* t = (task_obj_t*)TASK_UNTAG(result);
    _in_flight_task = (object_t*)t;
    task_on_complete((object_t*)t, (fun_t){.f=(void*)_trampoline, .o=NULL});
}


// ---- test driver -------------------------------------------------------

static struct test_results _results;
static fun_t               _exit_cont;

// Each test function has signature `void test_fn(void)` and is expected to
// eventually (synchronously or via chained callbacks) call `_next()`. The
// driver invokes tests in order.
typedef void (*test_fn)(void);

static const test_fn* _test_queue;
static int            _test_queue_len;
static int            _test_queue_idx;

static object_t* TMP_PATH;


static void _finish(void) {
    printf("io: %d passed, %d failed\n\n", _results.passed, _results.failed);
    object_t* status = integer_create_from_int32(_results.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, status);
}


static void _next(void) {
    if (_test_queue_idx >= _test_queue_len) {
        _finish();
        return;
    }
    _test_queue[_test_queue_idx++]();
}


static void _pass(const char* name) {
    printf("  %-50s OK\n", name); fflush(stdout);
    _results.passed++;
    _next();
}


static void _fail(const char* name, int line, const char* expr) {
    printf("  %-50s FAIL\n    line %d: %s\n", name, line, expr); fflush(stdout);
    _results.failed++;
    _next();
}


#define ASSERT_OR_FAIL(name, cond) \
    do { if (!(cond)) { _fail((name), __LINE__, #cond); return; } } while (0)


// ---- tests -------------------------------------------------------------

// stdout/stderr/stdin: all synchronous, no file open needed.

static void test_stdio_returns_objects(void) {
    const char* n = "stdio_returns_objects";
    ASSERT_OR_FAIL(n, io_stdout(NULL) != NULL);
    ASSERT_OR_FAIL(n, io_stderr(NULL) != NULL);
    ASSERT_OR_FAIL(n, io_stdin (NULL) != NULL);
    _pass(n);
}


// create + empty close (fast close path, no flush needed).

static void _create_close_step2(object_t* closed_result) {
    if (closed_result != NULL) { _fail("create_close_roundtrip", __LINE__, "close returned non-null"); return; }
    _pass("create_close_roundtrip");
}
static void _create_close_step1(object_t* io) {
    if (!(io != NULL && PTR_IS_OBJECT(io))) { _fail("create_close_roundtrip", __LINE__, "create not object"); return; }
    then(io_close(io), _create_close_step2);
}
static void test_create_close_roundtrip(void) {
    then(io_create(NULL, TMP_PATH), _create_close_step1);
}


// create with bad path -> negative int error.

static object_t* _bad_path_obj;
static void _bad_path_step1(object_t* result) {
    if (!PTR_IS_INTEGER(result) || integer_to_int32(result) >= 0) {
        _fail("create_bad_path_returns_error", __LINE__, "expected negative int");
        return;
    }
    // Release the path reference so GC can reclaim it between tests.
    _bad_path_obj = NULL;
    _pass("create_bad_path_returns_error");
}
static void test_create_bad_path_returns_error(void) {
    _bad_path_obj = string_from_bytes((uint8_t*)"/no/such/directory/file.tmp", 27);
    then(io_create(NULL, _bad_path_obj), _bad_path_step1);
}


// write + read round-trip: write fits in buffer (fast path), close flushes
// (async), open_read + read (async refill) + close.

static object_t* _rt_io;

static void _rt_step6(object_t* close_rd) {
    // close of read handle with empty buffer is synchronous NULL
    (void)close_rd;
    _pass("write_read_roundtrip");
}
static void _rt_step5(object_t* data) {
    if (data == NULL) { _fail("write_read_roundtrip", __LINE__, "read returned NULL"); return; }
    if (string_length(data) != 11) { _fail("write_read_roundtrip", __LINE__, "wrong length"); return; }
    object_t* exp = STR("hello world");
    if (string_compare(data, exp) != 0) { _fail("write_read_roundtrip", __LINE__, "content mismatch"); return; }
    then(io_close(_rt_io), _rt_step6);
}
static void _rt_step4(object_t* opened) {
    if (!(opened != NULL && PTR_IS_OBJECT(opened))) { _fail("write_read_roundtrip", __LINE__, "open_read failed"); return; }
    _rt_io = opened;
    then(io_read(opened, integer_create_from_int32(11)), _rt_step5);
}
static void _rt_step3(object_t* closed_write) {
    (void)closed_write;
    then(io_open_read(NULL, TMP_PATH), _rt_step4);
}
static void _rt_step2(object_t* written) {
    if (!PTR_IS_INTEGER(written) || integer_to_int32(written) != 11) {
        _fail("write_read_roundtrip", __LINE__, "write count wrong");
        return;
    }
    then(io_close(_rt_io), _rt_step3);
}
static void _rt_step1(object_t* io) {
    if (!(io != NULL && PTR_IS_OBJECT(io))) { _fail("write_read_roundtrip", __LINE__, "create failed"); return; }
    _rt_io = io;
    then(io_write(io, STR("hello world")), _rt_step2);
}
static void test_write_read_roundtrip(void) {
    then(io_create(NULL, TMP_PATH), _rt_step1);
}


// Read past EOF -> NULL.

static object_t* _eof_io;
static void _eof_step3(object_t* closed) {
    (void)closed;
    _pass("read_eof_returns_null");
}
static void _eof_step2(object_t* data) {
    if (data != NULL) { _fail("read_eof_returns_null", __LINE__, "expected NULL"); return; }
    then(io_close(_eof_io), _eof_step3);
}
static void _eof_step1b(object_t* opened) {
    if (!(opened != NULL && PTR_IS_OBJECT(opened))) { _fail("read_eof_returns_null", __LINE__, "open_read failed"); return; }
    _eof_io = opened;
    then(io_read(opened, integer_create_from_int32(16)), _eof_step2);
}
static void _eof_step1a(object_t* closed_write) {
    (void)closed_write;
    then(io_open_read(NULL, TMP_PATH), _eof_step1b);
}
static void _eof_step1(object_t* io) {
    then(io_close(io), _eof_step1a);
}
static void test_read_eof_returns_null(void) {
    then(io_create(NULL, TMP_PATH), _eof_step1);
}


// Oversize read -> clamped to IO_READ_MAX, not an error. File contains 40
// bytes; we ask for 100000 but get back 40 (the actual file size).

static object_t* _over_io;
static uint8_t   _over_payload[40];

static void _over_read_close_done(object_t* closed) { (void)closed; _pass("read_oversize_clamped"); }
static void _over_read_done(object_t* data) {
    if (data == NULL || !PTR_IS_OBJECT(data) || string_length(data) != 40) {
        _fail("read_oversize_clamped", __LINE__, "wrong length or null");
        return;
    }
    then(io_close(_over_io), _over_read_close_done);
}
static void _over_after_reopen(object_t* opened) {
    if (!(opened != NULL && PTR_IS_OBJECT(opened))) { _fail("read_oversize_clamped", __LINE__, "open_read failed"); return; }
    _over_io = opened;
    then(io_read(opened, integer_create_from_int32(100000)), _over_read_done);
}
static void _over_after_close_write(object_t* closed) {
    (void)closed;
    then(io_open_read(NULL, TMP_PATH), _over_after_reopen);
}
static void _over_after_write(object_t* written) {
    if (!PTR_IS_INTEGER(written) || integer_to_int32(written) != 40) {
        _fail("read_oversize_clamped", __LINE__, "write count != 40");
        return;
    }
    then(io_close(_over_io), _over_after_close_write);
}
static void _over_init(object_t* io) {
    if (!(io != NULL && PTR_IS_OBJECT(io))) { _fail("read_oversize_clamped", __LINE__, "create failed"); return; }
    _over_io = io;
    for (int i = 0; i < 40; ++i) _over_payload[i] = (uint8_t)('a' + (i % 26));
    then(io_write(io, string_from_bytes(_over_payload, 40)), _over_after_write);
}
static void test_read_oversize_clamped(void) {
    then(io_create(NULL, TMP_PATH), _over_init);
}


// Small write + big write preserves byte order.

static object_t* _ord_io;
static uint8_t*  _ord_big;   // heap-allocated payload, 10000 bytes
static int32_t   _ord_big_len;
static int32_t   _ord_offset; // bytes of _ord_big accepted so far

static void _ord_step_final(object_t* closed) {
    (void)closed;
    // Read back via stdio to validate bytes.
    FILE* f = fopen("/tmp/yafl_test_io.tmp", "r");
    if (!f) { _fail("small_then_big_write", __LINE__, "fopen readback"); return; }
    char prefix[8] = {0};
    size_t got = fread(prefix, 1, 7, f);
    if (got != 7 || memcmp(prefix, "prefix:", 7) != 0) {
        fclose(f); _fail("small_then_big_write", __LINE__, "prefix mismatch"); return;
    }
    uint8_t* buf = malloc((size_t)_ord_big_len);
    got = fread(buf, 1, (size_t)_ord_big_len, f);
    bool ok = (got == (size_t)_ord_big_len && memcmp(buf, _ord_big, (size_t)_ord_big_len) == 0);
    free(buf); fclose(f);
    free(_ord_big); _ord_big = NULL;
    if (!ok) { _fail("small_then_big_write", __LINE__, "big payload mismatch"); return; }
    _pass("small_then_big_write");
}

// io_write accepts up to one buffer's worth of bytes per call (per the
// io.c contract — the IO thread never touches caller-provided memory,
// only io->buf).  A payload larger than IO_BUFFER_SIZE therefore takes
// more than one call: the caller resubmits the unwritten suffix until
// all bytes have been accepted.  A return of 0 means the buffer was
// full and a flush has just completed; the caller resubmits unchanged
// and the next call accepts bytes into the empty buffer.
static void _ord_step_check(object_t* write_result) {
    if (!PTR_IS_INTEGER(write_result)) {
        _fail("small_then_big_write", __LINE__, "non-integer write result"); return;
    }
    int32_t n = integer_to_int32(write_result);
    if (n < 0) {
        _fail("small_then_big_write", __LINE__, "negative write count"); return;
    }
    _ord_offset += n;
    if (_ord_offset >= _ord_big_len) {
        then(io_close(_ord_io), _ord_step_final);
        return;
    }
    object_t* suffix = string_from_bytes(_ord_big + _ord_offset,
                                          _ord_big_len - _ord_offset);
    then(io_write(_ord_io, suffix), _ord_step_check);
}

static void _ord_step_big(object_t* write1_result) {
    (void)write1_result;
    _ord_offset = 0;
    object_t* big = string_from_bytes(_ord_big, _ord_big_len);
    then(io_write(_ord_io, big), _ord_step_check);
}

static void _ord_step1(object_t* io) {
    if (!(io != NULL && PTR_IS_OBJECT(io))) { _fail("small_then_big_write", __LINE__, "create failed"); return; }
    _ord_io = io;
    _ord_big_len = 10000;
    _ord_big = malloc((size_t)_ord_big_len);
    for (int32_t i = 0; i < _ord_big_len; ++i) _ord_big[i] = (uint8_t)('A' + (i % 26));
    then(io_write(io, STR("prefix:")), _ord_step_big);
}

static void test_small_then_big_write(void) {
    then(io_create(NULL, TMP_PATH), _ord_step1);
}


// ---- driver ------------------------------------------------------------

static const test_fn TESTS[] = {
    test_stdio_returns_objects,
    test_create_close_roundtrip,
    test_create_bad_path_returns_error,
    test_write_read_roundtrip,
    test_read_eof_returns_null,
    test_read_oversize_clamped,
    test_small_then_big_write,
};

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    declare(&TMP_PATH);
    declare(&_rt_io);
    declare(&_eof_io);
    declare(&_over_io);
    declare(&_ord_io);
    declare(&_bad_path_obj);
    declare(&_in_flight_task);
}

static void run_tests(object_t* _, fun_t continuation) {
    // GC-allocated so the path survives test function returns — tests chain
    // asynchronously and the IO threadpool may read the path long after the
    // function that passed it as a literal has popped its stack frame.
    TMP_PATH  = string_from_bytes((uint8_t*)"/tmp/yafl_test_io.tmp", 21);
    _exit_cont = continuation;
    _results.passed = 0;
    _results.failed = 0;
    _test_queue = TESTS;
    _test_queue_len = (int)(sizeof(TESTS)/sizeof(TESTS[0]));
    _test_queue_idx = 0;

    printf("=== io tests ===\n");
    _next();
    // When the last test's callback fires, _finish calls the exit
    // continuation.
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
