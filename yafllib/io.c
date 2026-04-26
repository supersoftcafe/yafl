
#include "yafl.h"
#include "io_internal.h"
#include <stdio.h>
#include <string.h>


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


static io_job_t* _io_job_alloc(io_op_t op,
                               io_t* io,
                               void (*finisher)(io_job_t*)) {
    // Pre-allocate the completion node so the IO thread can post back
    // without ever calling into the allocator.
    worker_node_t* node = thread_work_prepare((fun_t){
        .f = (void*)finisher,
        .o = NULL,   // filled in below once `job` exists
    });

    io_job_t* job = (io_job_t*)object_create((vtable_t*)&IO_JOB_VTABLE);
    atomic_store(&job->task.parent.state, 0);   // TASK_PENDING
    job->task.result     = NULL;
    job->io              = io;
    job->completion_node = node;
    job->op              = op;
    job->open_mode[0]    = 0;
    job->caller_length   = 0;
    job->raw_result      = 0;
    job->eof             = false;

    node->action.o = (object_t*)job;
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
        result = integer_create_from_int32_noalloc(job->raw_result);
    } else {
        io->buf_head = 0;
        io->buf_tail = job->raw_result;
        int32_t k = job->caller_length < io->buf_tail ? job->caller_length : io->buf_tail;
        result = string_from_bytes(io->buf, k);
        io->buf_head = k;
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    task_complete(&job->task.parent);
}


static void _io_finish_flush_write(io_job_t* job) {
    io_t* io = job->io;
    object_t* result;
    if (job->raw_result < 0) {
        result = integer_create_from_int32_noalloc(job->raw_result);
    } else {
        // Buffer drained.  The task resolves to 0 — the caller loops
        // back to io_write, which now finds an empty buffer.
        io->buf_tail = 0;
        result = integer_create_from_int32_noalloc(0);
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    task_complete(&job->task.parent);
}


static void _io_finish_open(io_job_t* job) {
    io_t* io = job->io;
    object_t* result;
    if (job->raw_result < 0) {
        result = integer_create_from_int32_noalloc(job->raw_result);
    } else {
        // io->file was set by the IO thread; reset the buf state for the
        // first read or write.
        io->buf_head = 0;
        io->buf_tail = 0;
        result = (object_t*)io;
    }
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    task_complete(&job->task.parent);
}


static void _io_finish_close(io_job_t* job) {
    io_t* io = job->io;
    io->file = NULL;          // handle is now closed whether or not there was an error
    io->buf_tail = 0;
    io->buf_head = 0;
    object_t* result = (job->raw_result < 0)
        ? integer_create_from_int32_noalloc(job->raw_result)
        : NULL;
    GC_WRITE_BARRIER(job->task.result, 1);
    job->task.result = result;
    task_complete(&job->task.parent);
}


// --- public IO entry points -----------------------------------------------

EXPORT object_t* io_create    (object_t* self, object_t* path)                 { (void)self; return _io_dispatch_open(path, "w", true);  }
EXPORT object_t* io_open_read (object_t* self, object_t* path)                 { (void)self; return _io_dispatch_open(path, "r", false); }
EXPORT object_t* io_open_write(object_t* self, object_t* path, bool truncate)  { (void)self; return _io_dispatch_open(path, truncate ? "w" : "a", true); }


EXPORT object_t* io_read(object_t* self, object_t* o_length) {
    io_t* io = (io_t*)self;
    if (io == NULL || io->file == NULL) return NULL;

    // Clamp rather than error.  OS read() is allowed to return fewer bytes
    // than requested; we do the same.
    int overflow = 0;
    int32_t length = integer_to_int32_with_overflow(o_length, &overflow);
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
        return integer_create_from_int32_noalloc(n);
    }

    // Buffer is full — flush it.  When the task completes, the buffer
    // is empty and the caller's next io_write call will copy in.
    return _io_dispatch_flush(io);
}


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
