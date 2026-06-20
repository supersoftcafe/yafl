
#include "yafl.h"
#include "io_internal.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <pthread.h>


// ─── In-flight job GC roots ───────────────────────────────────────────────────
// A job handed to the IO threads must stay reachable, but its references
// otherwise leave the GC's view: the IO queue and the IO threads' stacks are not
// scanned, and io_t.in_flight is a single heap field a moving cycle can miss if
// its container is marked-but-not-yet-scanned at prune time. So every job is held
// in this doubly-linked list from creation until its completion finisher runs,
// and the list is declared a GC root.
//
// Mutated ONLY by worker threads (dispatch creates the job; the completion
// dispatcher removes it — both run on workers), never by the IO threads, so the
// collector's worker-thread-only invariants hold. The lock serialises concurrent
// workers and the root walk.
static pthread_mutex_t _io_inflight_lock = PTHREAD_MUTEX_INITIALIZER;
static io_job_t*       _io_inflight_head = NULL;

static void _io_inflight_add(io_job_t* job) {
    pthread_mutex_lock(&_io_inflight_lock);
    job->root_prev = NULL;
    job->root_next = _io_inflight_head;
    if (_io_inflight_head) _io_inflight_head->root_prev = job;
    _io_inflight_head = job;
    pthread_mutex_unlock(&_io_inflight_lock);
}

static void _io_inflight_remove(io_job_t* job) {
    pthread_mutex_lock(&_io_inflight_lock);
    if (job->root_prev) job->root_prev->root_next = job->root_next;
    else                _io_inflight_head         = job->root_next;
    if (job->root_next) job->root_next->root_prev = job->root_prev;
    job->root_prev = job->root_next = NULL;
    pthread_mutex_unlock(&_io_inflight_lock);
}

static roots_declaration_func_t _io_prev_roots;
static void _io_declare_roots(void(*declare)(object_t**)) {
    _io_prev_roots(declare);
    // Mark each in-flight job directly (rather than chaining through root_next,
    // which is not GC-traced) so a job removed mid-cycle by another worker stays
    // marked for this cycle and newly added ones are simply caught next cycle.
    pthread_mutex_lock(&_io_inflight_lock);
    for (io_job_t* j = _io_inflight_head; j != NULL; j = j->root_next) {
        io_job_t* t = j;
        declare((object_t**)&t);
    }
    pthread_mutex_unlock(&_io_inflight_lock);
}

HIDDEN void _io_inflight_roots_register(void) {
    _io_prev_roots = add_roots_declaration_func(_io_declare_roots);
}


// io_t vtable.  is_mutable=1 means the page is never compacted, so the
// buffer's address is stable for the lifetime of the handle — that is what
// allows IO threads to hold a raw `&io->buf[0]` across blocking syscalls.
//
// `in_flight` is a GC-traced ref to the currently-dispatched io_job_t.
// Workers update it through the GC write barrier *before* enqueuing the
// job, so the job is reachable from the moment it could be observed by
// any other thread (GC included).  IO threads never write `in_flight`.
HIDDEN struct io_vtable IO_VTABLE = {
    .object_size                = sizeof(io_t),
    .array_el_size              = 0,
    .object_pointer_locations   = maskof(io_t, .in_flight),
    .array_el_pointer_locations = 0,
    .functions_mask             = 0,
    .array_len_offset           = 0,
    .is_mutable                 = 1,
    .name                       = "io",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};


// FileInfo holds only scalar fields and has no pointer slots, so the GC
// mask is empty.  is_mutable=1 keeps the page stable for the brief window
// between worker-side allocation and the IO thread filling in the fields.
HIDDEN struct fs_file_info_vtable FS_FILE_INFO_VTABLE = {
    .object_size                = sizeof(fs_file_info_t),
    .array_el_size              = 0,
    .object_pointer_locations   = 0,
    .array_el_pointer_locations = 0,
    .functions_mask             = 0,
    .array_len_offset           = 0,
    .is_mutable                 = 1,
    .name                       = "_FileInfo",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};


// Dir cursor vtable.  is_mutable=1 keeps the page stable so the IO thread
// can hold raw pointers into `path_buf` / `entry_buf` across syscalls.
// `in_flight` is the GC-tracing anchor for the currently-dispatched job.
HIDDEN struct dir_vtable DIR_VTABLE = {
    .object_size                = sizeof(dir_t),
    .array_el_size              = 0,
    .object_pointer_locations   = maskof(dir_t, .in_flight),
    .array_el_pointer_locations = 0,
    .functions_mask             = 0,
    .array_len_offset           = 0,
    .is_mutable                 = 1,
    .name                       = "_Dir",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};


// --- construction helpers -------------------------------------------------

static io_t* _io_alloc(FILE* file, bool owned, bool is_write) {
    io_t* io = (io_t*)object_create((vtable_t*)&IO_VTABLE);
    // object_create zero-fills, so in_flight starts as NULL.
    io->file     = file;
    io->owned    = owned;
    io->is_write = is_write;
    io->buf_head = 0;
    io->buf_tail = 0;
    return io;
}


// --- synchronous wrappers for standard streams ----------------------------
//
// stdin/stdout/stderr are already open and don't block on setup.  Their
// buffering is owned by the terminal / libc stdio; we don't disable it
// because the caller didn't open them.

EXPORT object_t* io_stdin (object_t* self) { (void)self; return (object_t*)_io_alloc(stdin,  false, false); }
EXPORT object_t* io_stdout(object_t* self) { (void)self; return (object_t*)_io_alloc(stdout, false, true ); }
EXPORT object_t* io_stderr(object_t* self) { (void)self; return (object_t*)_io_alloc(stderr, false, true ); }


// --- async dispatch -------------------------------------------------------
//
// Every byte the IO thread reads or writes flows through `io->buf`, which
// lives inside an `is_mutable=1` object whose page is not eligible for
// compaction.  The job carries no external-data pointers, so the IO thread
// never dereferences GC memory that could move under it.

static void _io_finish_refill      (io_job_t* job);
static void _io_finish_flush_write (io_job_t* job);
static void _io_finish_open        (io_job_t* job);
static void _io_finish_close       (io_job_t* job);


// Callback registered on the completion_task.  Runs on the worker after the
// IO thread posts the task; invokes the op-specific finisher (which may
// allocate) then drives the state machine forward.
static object_t* _io_finisher_dispatcher(void* job_ptr, object_t* unused) {
    (void)unused;
    io_job_t* job = (io_job_t*)job_ptr;
    job->finisher(job);
    // The job's result has been consumed; drop it from the in-flight roots.
    // Runs on a worker thread (this is a worker-queue callback).
    _io_inflight_remove(job);
    return NULL;
}


static io_job_t* _io_job_alloc(io_op_t op,
                               io_t* io,
                               void (*finisher)(io_job_t*)) {
    io_job_t* job = (io_job_t*)object_create((vtable_t*)&IO_JOB_VTABLE);
    task_init((object_t*)&job->task);              // sets thread_id, next, state=PENDING
    // job is freshly object_create'd (all fields zeroed → NULL), so each store's
    // overwritten value is NULL; the barriers are uniform no-ops here.
    job->task.result     = NULL;
    GC_WRITE_BARRIER(job->io, 1);
    job->io              = io;
    job->fs_aux          = NULL;
    job->dir             = NULL;
    job->finisher        = finisher;
    job->spawn           = NULL;
    job->op              = op;
    job->open_mode[0]    = 0;
    job->caller_length   = 0;
    job->raw_result      = 0;
    job->eof             = false;

    // Pre-allocate the completion task so the IO thread can post back
    // without calling into the allocator.  callback.o = job keeps the job
    // reachable from the completion_task's pointer mask.
    task_t* ct = (task_t*)task_create(NULL);
    task_on_complete((object_t*)ct, (fun_t){.f = (void*)_io_finisher_dispatcher, .o = (object_t*)job});
    GC_WRITE_BARRIER(job->completion_task, 1);
    job->completion_task = ct;

    // Root the job for its whole in-flight lifetime (until the finisher above
    // runs). Done last so the job is fully constructed first. Worker thread.
    _io_inflight_add(job);
    return job;
}


// Anchor `job` as the in-flight task on its handle.  This must happen
// before the job is enqueued so that, the instant the job is visible to
// any other thread (including the GC), it is rooted via the handle.  Use
// the GC write barrier so old-generation/concurrent collectors see the
// store.  Per design we never explicitly clear `in_flight`; it is simply
// overwritten by the next dispatch (or the handle becomes unreachable).
static void _io_anchor_in_flight(io_t* io, io_job_t* job) {
    GC_WRITE_BARRIER(io->in_flight, 1);
    io->in_flight = job;
}


static object_t* _io_as_task(io_job_t* job) {
    return (object_t*)(((uintptr_t)&job->task) | PTR_TAG_TASK);
}


static object_t* _io_dispatch_refill(io_t* io, int32_t caller_length) {
    io_job_t* job = _io_job_alloc(IO_OP_REFILL, io, _io_finish_refill);
    job->caller_length = caller_length;
    _io_anchor_in_flight(io, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


// Dispatch a buffer flush.  The job carries no caller-supplied data
// pointer: the IO thread only ever touches `io->buf`, which lives on
// an `is_mutable=1` page that the GC will not compact.  The finisher
// resets `buf_tail` and resolves the task to 0 — caller loops back to
// io_write with whatever bytes were not yet accepted.
static object_t* _io_dispatch_flush(io_t* io) {
    io_job_t* job = _io_job_alloc(IO_OP_FLUSH_WRITE, io, _io_finish_flush_write);
    _io_anchor_in_flight(io, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


static object_t* _io_dispatch_open(object_t* path, const char* mode, bool is_write) {
    // Allocate the io_t now (file=NULL until the IO thread fills it in).
    io_t* io = _io_alloc(NULL, true, is_write);

    // Copy the path bytes into io->buf so the IO thread reads from a
    // stable, non-compactable location.  The path string itself is not
    // mutable, so it's eligible for GC compaction — we don't keep a
    // reference to it past this point.
    intptr_t local = 0;
    int32_t  len = 0;
    const char* cstr = string_to_cstr(path, &local, &len);
    if (len < 0) len = 0;
    if (len >= IO_BUFFER_SIZE) len = IO_BUFFER_SIZE - 1;
    if (len > 0) memcpy(io->buf, cstr, (size_t)len);
    io->buf[len] = 0;   // ensure null-termination for fopen

    io_job_t* job = _io_job_alloc(IO_OP_OPEN, io, _io_finish_open);
    job->open_mode[0] = mode[0];
    job->open_mode[1] = mode[1];
    job->open_mode[2] = 0;
    _io_anchor_in_flight(io, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


static object_t* _io_dispatch_close_with_flush(io_t* io) {
    io_job_t* job = _io_job_alloc(IO_OP_CLOSE, io, _io_finish_close);
    _io_anchor_in_flight(io, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


// --- finishers (run on a worker after the IO thread posts) ----------------

static void _io_finish_refill(io_job_t* job) {
    io_t* io = job->io;
    object_t* result;
    if (job->eof) {
        result = NULL;
    } else if (job->raw_result < 0) {
        result = integer_from_int32_noalloc(job->raw_result);
    } else {
        io->buf_head = 0;
        io->buf_tail = job->raw_result;
        int32_t k = job->caller_length < io->buf_tail ? job->caller_length : io->buf_tail;
        result = string_from_bytes(io->buf, k);
        io->buf_head = k;
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


// Like _io_finish_refill, but resolves to the refilled byte count rather than
// consuming bytes into a string: the buffer is left full (buf_head = 0) for a
// following io_take_line. None = EOF (0 bytes); a negative Int = errno.
static void _io_finish_refill_status(io_job_t* job) {
    io_t* io = job->io;
    object_t* result;
    if (job->eof) {
        result = NULL;
    } else if (job->raw_result < 0) {
        result = integer_from_int32_noalloc(job->raw_result);
    } else {
        io->buf_head = 0;
        io->buf_tail = job->raw_result;
        result = integer_from_int32(job->raw_result);
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


static void _io_finish_flush_write(io_job_t* job) {
    io_t* io = job->io;
    object_t* result;
    if (job->raw_result < 0) {
        result = integer_from_int32_noalloc(job->raw_result);
    } else {
        // Buffer drained.  The task resolves to 0 — the caller loops
        // back to io_write, which now finds an empty buffer.
        io->buf_tail = 0;
        result = integer_from_int32_noalloc(0);
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


static void _io_finish_open(io_job_t* job) {
    io_t* io = job->io;
    object_t* result;
    if (job->raw_result < 0) {
        result = integer_from_int32_noalloc(job->raw_result);
    } else {
        // io->file was set by the IO thread; reset the buf state for the
        // first read or write.
        io->buf_head = 0;
        io->buf_tail = 0;
        result = (object_t*)io;
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


static void _io_finish_close(io_job_t* job) {
    io_t* io = job->io;
    io->file = NULL;          // handle is now closed whether or not there was an error
    io->buf_tail = 0;
    io->buf_head = 0;
    object_t* result = (job->raw_result < 0)
        ? integer_from_int32_noalloc(job->raw_result)
        : NULL;
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


// --- public IO entry points -----------------------------------------------

EXPORT object_t* io_create    (object_t* self, object_t* path)                 { (void)self; return _io_dispatch_open(path, "w", true);  }
EXPORT object_t* io_open_read (object_t* self, object_t* path)                 { (void)self; return _io_dispatch_open(path, "r", false); }
EXPORT object_t* io_open_write(object_t* self, object_t* path, int8_t truncate)  { (void)self; return _io_dispatch_open(path, truncate ? "w" : "a", true); }


EXPORT object_t* io_read(object_t* self, object_t* o_length) {
    io_t* io = (io_t*)self;
    if (io == NULL || io->file == NULL) return NULL;

    // Clamp rather than error.  OS read() is allowed to return fewer bytes
    // than requested; we do the same.
    int overflow = 0;
    int32_t length = int32_from_integer_with_overflow(o_length, &overflow);
    if (overflow || length > IO_READ_MAX) length = IO_READ_MAX;
    if (length < 0) length = 0;

    int32_t avail = io->buf_tail - io->buf_head;
    if (avail > 0 || length == 0) {
        int32_t k = length < avail ? length : avail;
        object_t* s = string_from_bytes(io->buf + io->buf_head, k);
        io->buf_head += k;
        return s;
    }

    return _io_dispatch_refill(io, length);
}


// Pull the next line out of the handle's buffer, synchronously (no refill). Scans
// for '\n' within the first min(avail, max) bytes; returns the bytes up to AND
// INCLUDING the '\n' when found, otherwise the whole window (a buffer-end partial
// line, or a max-length cap). Bytes are returned verbatim — the '\n'/'\r' are
// kept — and consumed from the buffer. Returns "" when the buffer is empty (the
// caller then refills via io_refill). The line accumulation across refills, and
// the max-length budget, live in the YAFL `readLine` loop.
EXPORT object_t* io_take_line(object_t* self, object_t* o_max) {
    io_t* io = (io_t*)self;
    if (io == NULL || io->file == NULL) return NULL;

    int overflow = 0;
    int32_t max = int32_from_integer_with_overflow(o_max, &overflow);
    if (overflow || max > IO_READ_MAX) max = IO_READ_MAX;

    int32_t avail = io->buf_tail - io->buf_head;
    if (max <= 0 || avail <= 0) return string_from_bytes(io->buf + io->buf_head, 0);

    int32_t window = max < avail ? max : avail;
    void* nl = memchr(io->buf + io->buf_head, '\n', (size_t)window);
    int32_t take = (nl != NULL)
        ? (int32_t)((char*)nl - (char*)(io->buf + io->buf_head)) + 1   // include the '\n'
        : window;
    object_t* s = string_from_bytes(io->buf + io->buf_head, take);
    io->buf_head += take;
    return s;
}


// Refill the handle's buffer for io_take_line. Returns the new byte count (Int),
// None on EOF, or a negative Int on error. Async (dispatched to the IO thread)
// unless bytes are already buffered, in which case it reports them immediately.
EXPORT object_t* io_refill(object_t* self) {
    io_t* io = (io_t*)self;
    if (io == NULL || io->file == NULL) return NULL;

    int32_t avail = io->buf_tail - io->buf_head;
    if (avail > 0) return integer_from_int32(avail);

    io_job_t* job = _io_job_alloc(IO_OP_REFILL, io, _io_finish_refill_status);
    job->caller_length = 0;
    _io_anchor_in_flight(io, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


// io_write copies as much of `data` as fits into the handle's buffer and
// returns the byte count it accepted (synchronously).  When the buffer
// is already full it dispatches a flush and returns a task that resolves
// to 0 once the flush completes — callers loop, calling io_write again
// with the unwritten suffix until the byte count returned reaches the
// payload length.  The IO thread never touches anything beyond `io->buf`.
EXPORT object_t* io_write(object_t* self, object_t* data) {
    io_t* io = (io_t*)self;
    if (io == NULL || io->file == NULL) return NULL;

    intptr_t local = 0; int32_t len = 0;
    const char* bytes = string_to_cstr(data, &local, &len);
    if (len < 0) len = 0;

    int32_t space = IO_BUFFER_SIZE - io->buf_tail;
    if (space > 0) {
        int32_t n = (len < space) ? len : space;
        if (n > 0) memcpy(io->buf + io->buf_tail, bytes, (size_t)n);
        io->buf_tail += n;
        return integer_from_int32_noalloc(n);
    }

    // Buffer is full — flush it.  When the task completes, the buffer
    // is empty and the caller's next io_write call will copy in.
    return _io_dispatch_flush(io);
}


// --- filesystem metadata ----------------------------------------------------
//
// Both ops dispatch through the IO threadpool.  The scratch io_t is reused
// purely as a stable, non-compactable buffer for the path string — its
// `file`/`is_write`/buffer-state fields are not touched on these paths.

static void _fs_finish_exists(io_job_t* job);
static void _fs_finish_stat   (io_job_t* job);


static object_t* _fs_dispatch_meta(object_t* path, io_op_t op,
                                   void (*finisher)(io_job_t*),
                                   fs_file_info_t* aux) {
    io_t* io = _io_alloc(NULL, false, false);

    intptr_t local = 0;
    int32_t  len   = 0;
    const char* cstr = string_to_cstr(path, &local, &len);
    if (len < 0) len = 0;
    if (len >= IO_BUFFER_SIZE) len = IO_BUFFER_SIZE - 1;
    if (len > 0) memcpy(io->buf, cstr, (size_t)len);
    io->buf[len] = 0;

    io_job_t* job = _io_job_alloc(op, io, finisher);
    if (aux) {
        GC_WRITE_BARRIER(job->fs_aux, 1);
        job->fs_aux = aux;
    }
    _io_anchor_in_flight(io, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


static void _fs_finish_exists(io_job_t* job) {
    // raw_result is 0 or 1 — collapsed in the IO thread; never -errno on
    // this path (exists swallows all errors as `false`).
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = integer_from_int32_noalloc(job->raw_result);
    task_complete((object_t*)&job->task);
}


static void _fs_finish_stat(io_job_t* job) {
    object_t* result = (job->raw_result < 0)
        ? integer_from_int32_noalloc(job->raw_result)
        : (object_t*)job->fs_aux;
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


EXPORT object_t* fs_exists(object_t* self, object_t* path) {
    (void)self;
    return _fs_dispatch_meta(path, IO_OP_FS_EXISTS, _fs_finish_exists, NULL);
}


EXPORT object_t* fs_stat(object_t* self, object_t* path) {
    (void)self;
    // Pre-allocate the FileInfo so the IO thread can write its scalar
    // fields without touching the allocator.  Zero-initialised by
    // object_create; the IO thread fills it on success, leaves the
    // zero-bytes alone on failure (caller will not see the object).
    fs_file_info_t* fi = (fs_file_info_t*)object_create((vtable_t*)&FS_FILE_INFO_VTABLE);
    return _fs_dispatch_meta(path, IO_OP_FS_STAT, _fs_finish_stat, fi);
}


// Sync accessors — called via [foreign, sync] from the public stat()
// wrapper after the task resolves to a successful _FileInfo.

EXPORT object_t* fs_fi_size  (object_t* self) { return integer_from_int32(((fs_file_info_t*)self)->size);  }
EXPORT object_t* fs_fi_mtime (object_t* self) { return integer_from_int32(((fs_file_info_t*)self)->mtime); }
EXPORT object_t* fs_fi_mode  (object_t* self) { return integer_from_int32(((fs_file_info_t*)self)->mode);  }
EXPORT object_t* fs_fi_isdir (object_t* self) { return integer_from_int24(((fs_file_info_t*)self)->is_dir     ? 1 : 0); }
EXPORT object_t* fs_fi_isreg (object_t* self) { return integer_from_int24(((fs_file_info_t*)self)->is_regular ? 1 : 0); }


EXPORT object_t* io_close(object_t* self) {
    io_t* io = (io_t*)self;
    if (io == NULL || io->file == NULL) return NULL;

    if (io->is_write && io->buf_tail > 0) {
        return _io_dispatch_close_with_flush(io);
    }

    if (io->owned) fclose(io->file);
    io->file = NULL;
    io->buf_tail = 0;
    io->buf_head = 0;
    return NULL;
}


// --- directory cursor ------------------------------------------------------

static void _fs_finish_dir_open (io_job_t* job);
static void _fs_finish_dir_next (io_job_t* job);
static void _fs_finish_dir_close(io_job_t* job);


static void _dir_anchor_in_flight(dir_t* dir, io_job_t* job) {
    GC_WRITE_BARRIER(dir->in_flight, 1);
    dir->in_flight = job;
}


EXPORT object_t* fs_open_dir(object_t* self, object_t* path) {
    (void)self;
    dir_t* dir = (dir_t*)object_create((vtable_t*)&DIR_VTABLE);
    // dirp=NULL, in_flight=NULL by object_create zero-fill.

    intptr_t local = 0;
    int32_t  len   = 0;
    const char* cstr = string_to_cstr(path, &local, &len);
    if (len < 0) len = 0;
    if (len >= (int32_t)sizeof(dir->path_buf)) len = (int32_t)sizeof(dir->path_buf) - 1;
    if (len > 0) memcpy(dir->path_buf, cstr, (size_t)len);
    dir->path_buf[len] = 0;

    io_job_t* job = _io_job_alloc(IO_OP_DIR_OPEN, NULL, _fs_finish_dir_open);
    GC_WRITE_BARRIER(job->dir, 1);
    job->dir = dir;
    _dir_anchor_in_flight(dir, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


EXPORT object_t* fs_dir_next(object_t* self) {
    dir_t* dir = (dir_t*)self;
    if (dir == NULL || dir->dirp == NULL) return NULL;

    io_job_t* job = _io_job_alloc(IO_OP_DIR_NEXT, NULL, _fs_finish_dir_next);
    GC_WRITE_BARRIER(job->dir, 1);
    job->dir = dir;
    _dir_anchor_in_flight(dir, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


EXPORT object_t* fs_dir_close(object_t* self) {
    dir_t* dir = (dir_t*)self;
    if (dir == NULL || dir->dirp == NULL) return NULL;

    io_job_t* job = _io_job_alloc(IO_OP_DIR_CLOSE, NULL, _fs_finish_dir_close);
    GC_WRITE_BARRIER(job->dir, 1);
    job->dir = dir;
    _dir_anchor_in_flight(dir, job);
    _io_enqueue(job);
    return _io_as_task(job);
}


static void _fs_finish_dir_open(io_job_t* job) {
    object_t* result = (job->raw_result < 0)
        ? integer_from_int32_noalloc(job->raw_result)
        : (object_t*)job->dir;
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


static void _fs_finish_dir_next(io_job_t* job) {
    dir_t* dir = job->dir;
    object_t* result;
    if (dir->entry_eof) {
        result = NULL;                          // None = end of stream
    } else if (job->raw_result < 0) {
        result = integer_from_int32_noalloc(job->raw_result);
    } else {
        result = string_from_bytes((uint8_t*)dir->entry_buf, job->raw_result);
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


static void _fs_finish_dir_close(io_job_t* job) {
    object_t* result = (job->raw_result < 0)
        ? integer_from_int32_noalloc(job->raw_result)
        : NULL;
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


// --- subprocess (run an external program, capture stdout/stderr/exit) ------

// _SpawnResult holds two String pointers, so the GC mask covers them; the
// exit code is a scalar.  Built on a worker (in the finisher), never touched
// by the IO thread, so it does not need is_mutable pinning.
HIDDEN struct spawn_result_vtable SPAWN_RESULT_VTABLE = {
    .object_size                = sizeof(spawn_result_t),
    .array_el_size              = 0,
    .object_pointer_locations   = maskof(spawn_result_t, .out)
                                | maskof(spawn_result_t, .err),
    .array_el_pointer_locations = 0,
    .functions_mask             = 0,
    .array_len_offset           = 0,
    .is_mutable                 = 0,
    .name                       = "_SpawnResult",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};


// Finisher (worker): wrap the captured bytes into Strings and free the
// non-GC scratch.  The container is rooted via task.result *before* the
// Strings are allocated, so a GC during string_from_bytes cannot collect it.
static void _spawn_finish(io_job_t* job) {
    spawn_aux_t* sx = job->spawn;
    object_t* result;
    if (job->raw_result < 0) {
        result = integer_from_int32_noalloc(job->raw_result);
    } else {
        spawn_result_t* sr = (spawn_result_t*)object_create((vtable_t*)&SPAWN_RESULT_VTABLE);
        sr->exit_code = sx->exit_code;
        GC_WRITE_BARRIER(job->task.result, 1);
        job->task.result = (object_t*)sr;     // root sr before allocating Strings
        object_t* out = string_from_bytes((uint8_t*)(sx->out ? sx->out : (char*)""), sx->out_len);
        GC_WRITE_BARRIER(sr->out, 1);
        sr->out = out;
        GC_MARK_SEEN(out);   // insertion barrier: sr is marked-seen but not necessarily
                             // WALKED this cycle, so its children must publish themselves.
        object_t* err = string_from_bytes((uint8_t*)(sx->err ? sx->err : (char*)""), sx->err_len);
        GC_WRITE_BARRIER(sr->err, 1);
        sr->err = err;
        GC_MARK_SEEN(err);
        result = (object_t*)sr;
    }
    free(sx->packed);
    free(sx->argv);
    free(sx->out);
    free(sx->err);
    free(sx);
    job->spawn = NULL;
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    GC_MARK_SEEN(result);   // insertion barrier: once the finisher returns, task.result
                            // is the only reference to a freshly-allocated result, so an
                            // incremental marker that has already scanned this worker's
                            // roots (or won't walk the birth-protected task) must be told.
    task_complete((object_t*)&job->task);
}


// Worker entry.  `packed` is program + args joined by NUL bytes (the YAFL
// side builds it).  We copy `packed` into a stable malloc buffer and point argv
// entries at it — the NUL separators double as the C-string terminators each
// argv element needs.  argc is derived here as the separator count plus one (a
// NUL never appears inside an element, so the count is exact), sparing the YAFL
// side an O(n) list length.  Returns the async task; spawn/exec failure resolves
// to a negative errno (→ IOError), while a non-zero child exit is a *success*
// carried in the result.
EXPORT object_t* process_run(object_t* self, object_t* packed) {
    (void)self;

    intptr_t local = 0;
    int32_t  len   = 0;
    const char* cstr = string_to_cstr(packed, &local, &len);
    if (len < 0) len = 0;

    int32_t argc = 1;
    for (int32_t i = 0; i < len; i++) if (cstr[i] == 0) argc++;

    spawn_aux_t* sx = (spawn_aux_t*)calloc(1, sizeof(spawn_aux_t));
    sx->packed = (char*)malloc((size_t)len + 1);
    if (len > 0) memcpy(sx->packed, cstr, (size_t)len);
    sx->packed[len] = 0;
    sx->argc = argc;
    sx->argv = (char**)calloc((size_t)argc + 1, sizeof(char*));

    // Split on NUL: argv[0] is the program, each following element starts one
    // byte after the next separator.  Stop once we have argc entries.
    int32_t idx = 0;
    sx->argv[idx++] = sx->packed;
    for (int32_t i = 0; i < len && idx < argc; i++) {
        if (sx->packed[i] == 0) sx->argv[idx++] = &sx->packed[i + 1];
    }
    sx->argv[argc] = NULL;

    io_job_t* job = _io_job_alloc(IO_OP_SPAWN, NULL, _spawn_finish);
    job->spawn = sx;
    _io_enqueue(job);
    return _io_as_task(job);
}


// Sync accessors on a resolved _SpawnResult.
EXPORT object_t* spawn_exit_code(object_t* self) { return integer_from_int32(((spawn_result_t*)self)->exit_code); }
EXPORT object_t* spawn_out      (object_t* self) { return ((spawn_result_t*)self)->out; }
EXPORT object_t* spawn_err      (object_t* self) { return ((spawn_result_t*)self)->err; }
