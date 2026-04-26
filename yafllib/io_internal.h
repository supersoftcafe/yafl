#ifndef YAFLLIB_IO_INTERNAL_H
#define YAFLLIB_IO_INTERNAL_H

#include "yafl.h"
#include <stdio.h>

// Per-handle buffer size.  Sized so that one buffer comfortably holds an
// open path (paths up to PATH_MAX are 4 KiB on Linux) and the bulk of
// typical line-oriented IO without a syscall.  IO threads only ever read
// and write into this buffer — never into any other GC-managed memory —
// because the buffer lives inside an `is_mutable=1` object whose page is
// not eligible for compaction.
#define IO_BUFFER_SIZE  8192

// Upper bound on a single io_read request.  Requests larger than this are
// truncated (we mirror OS read() semantics: returning fewer bytes than
// requested is allowed).
#define IO_READ_MAX     1024

// Forward decl — defined below.
struct io_job;

// The public YAFL io handle.  One task per handle at a time (single-
// threaded use; linear types will enforce that eventually).
//
// `in_flight` is the GC-rooting anchor for any currently-dispatched
// io_job_t belonging to this handle.  Workers update it through the GC
// write barrier *before* enqueuing the job; IO threads do not touch it.
// It is never explicitly cleared — the next dispatch overwrites it, and
// finished jobs become unreachable when the next one replaces them or
// when the handle itself is collected.
typedef struct {
    object_t        parent;          // GC vtable
    struct io_job*  in_flight;       // GC ref: currently-dispatched job, or NULL
    FILE*           file;            // owned libc handle (NULL until OPEN succeeds)
    bool            owned;           // do we fclose on io_close?
    bool            is_write;        // direction fixed at open (no seek)
    int32_t         buf_head;        // read: first unconsumed byte; write: 0
    int32_t         buf_tail;        // read: one past last valid; write: next free slot
    uint8_t         buf[IO_BUFFER_SIZE];
} io_t;

typedef enum {
    IO_OP_REFILL,       // fread into io->buf
    IO_OP_FLUSH_WRITE,  // fwrite io->buf
    IO_OP_OPEN,         // fopen(io->buf as path) + setvbuf
    IO_OP_CLOSE,        // fwrite io->buf (if any) then fclose
} io_op_t;

// IO job.  Embeds task_obj_t as first field so (task_obj_t*)job is the
// task the caller holds.  Allocated on a worker before suspension.
//
// All bytes the IO thread reads or writes flow through `io->buf`, which
// lives on an `is_mutable=1` page that the GC will not compact.  The job
// itself carries no caller-supplied pointers: there is nothing else for
// the IO thread to dereference.  Every GC-managed field is grouped at
// the start of the struct so the vtable's pointer mask stays compact and
// the GC has all reachable references in one cache line.
typedef struct io_job {
    task_obj_t              task;              // GC: callback.o, result
    _Atomic(struct io_job*) next_in_io_queue;  // GC: MPSC linkage in the IO queue
    io_t*                   io;                // GC: target handle (allocated on worker, even for OPEN)
    worker_node_t*          completion_node;   // GC: pre-allocated; action = per-op finisher

    io_op_t                 op;
    char                    open_mode[4];      // "r", "w", "a"
    int32_t                 caller_length;     // REFILL: caller's requested length
    int32_t                 raw_result;        // bytes moved, 0 for EOF, -errno on failure
    bool                    eof;               // REFILL: 0 bytes + feof()
} io_job_t;

VTABLE_DECLARE_STRUCT(io_vtable, 16);
VTABLE_DECLARE_STRUCT(io_job_vtable, 0);

HIDDEN extern struct io_vtable IO_VTABLE;
HIDDEN extern struct io_job_vtable IO_JOB_VTABLE;

// Private threadpool lifecycle and submission.
HIDDEN void _io_threadpool_init(void);
HIDDEN void _io_enqueue(io_job_t* job);

#endif
