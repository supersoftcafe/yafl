#ifndef YAFLLIB_IO_INTERNAL_H
#define YAFLLIB_IO_INTERNAL_H

#include "yafl.h"
#include <stdio.h>
#include <dirent.h>
#include <limits.h>

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
    IO_OP_FS_EXISTS,    // access(io->buf, F_OK); result is rc in raw_result
    IO_OP_FS_STAT,      // stat(io->buf, &st); writes fields into fs_aux (fs_file_info_t)
    IO_OP_DIR_OPEN,     // opendir(dir->path_buf); writes dir->dirp
    IO_OP_DIR_NEXT,     // readdir(dir->dirp); writes dir->entry_buf or dir->entry_eof
    IO_OP_DIR_CLOSE,    // closedir(dir->dirp); clears dir->dirp
    IO_OP_SPAWN,        // posix_spawnp(job->spawn->argv); captures out/err + exit
} io_op_t;

// FileInfo struct exposed to YAFL via the [foreign,final] _FileInfo class
// and the fs_fi_* accessors.  Allocated on a worker before STAT dispatch
// so the IO thread can write into the int32 fields without touching the
// GC.  is_mutable=1 keeps the pointer stable across the IO thread call.
typedef struct {
    object_t parent;
    int32_t  size;
    int32_t  mtime;
    int32_t  mode;
    bool     is_dir;
    bool     is_regular;
} fs_file_info_t;

VTABLE_DECLARE_STRUCT(fs_file_info_vtable, 0);
HIDDEN extern struct fs_file_info_vtable FS_FILE_INFO_VTABLE;


// Directory cursor.  Mirror of io_t but for opendir/readdir/closedir.
// is_mutable=1 keeps the page from being compacted so the IO thread can
// hold raw `&dir->path_buf[0]` / `&dir->entry_buf[0]` across syscalls.
//
// `in_flight` is the GC-rooting anchor for the currently-dispatched job
// (one outstanding op per handle by linear-types contract).
typedef struct {
    object_t       parent;
    struct io_job* in_flight;
    DIR*           dirp;
    bool           entry_ready;     // NEXT: an entry name was written to entry_buf
    bool           entry_eof;       // NEXT: end of directory stream
    char           path_buf[PATH_MAX];
    char           entry_buf[NAME_MAX + 2];
} dir_t;

VTABLE_DECLARE_STRUCT(dir_vtable, 0);
HIDDEN extern struct dir_vtable DIR_VTABLE;


// Subprocess scratch.  All non-GC: the IO thread builds argv on the worker
// before dispatch, then captures the child's stdout/stderr into growable
// malloc buffers (malloc, not the GC allocator, is allowed on the IO thread).
// The finisher copies the captured bytes into GC Strings and frees all of
// this.  `packed` owns the argv backing store; the argv entries point into it.
typedef struct spawn_aux {
    char*   packed;     // malloc copy of the NUL-separated argv buffer
    char**  argv;       // malloc, argc+1 entries (NULL-terminated), into `packed`
    int32_t argc;
    int32_t exit_code;  // child exit status, or -signal if signalled
    char*   out;        // growable capture of stdout
    int32_t out_len;
    int32_t out_cap;
    char*   err;        // growable capture of stderr
    int32_t err_len;
    int32_t err_cap;
} spawn_aux_t;


// Result of a finished subprocess, exposed to YAFL via the [foreign,final]
// _SpawnResult class.  Built entirely on a worker in the finisher, so unlike
// the IO-thread-written structs it needs no is_mutable pinning.
typedef struct {
    object_t  parent;
    object_t* out;        // String
    object_t* err;        // String
    int32_t   exit_code;
} spawn_result_t;

VTABLE_DECLARE_STRUCT(spawn_result_vtable, 0);
HIDDEN extern struct spawn_result_vtable SPAWN_RESULT_VTABLE;

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
    io_t*                   io;                // GC: IO target handle (NULL for dir ops)
    task_t*                 completion_task;   // GC: pre-allocated task; callback = per-op finisher
    fs_file_info_t*         fs_aux;            // GC: pre-allocated FileInfo for STAT, NULL otherwise
    dir_t*                  dir;               // GC: dir target handle (NULL for io ops)

    io_op_t                 op;
    void                    (*finisher)(struct io_job*);  // non-GC: runs on worker after IO
    struct spawn_aux*       spawn;             // non-GC: SPAWN scratch, NULL otherwise
    char                    open_mode[4];      // "r", "w", "a"
    int32_t                 caller_length;     // REFILL: caller's requested length
    int32_t                 raw_result;        // bytes moved, 0 for EOF, -errno on failure
    bool                    eof;               // REFILL: 0 bytes + feof()

    // Worker-managed in-flight list links (io.c). NOT GC-traced and never
    // touched by IO threads: these keep every dispatched-but-not-finished job
    // reachable as a GC root so the collector cannot reclaim a job whose only
    // heap anchor (io_t.in_flight) is momentarily unscanned during a moving cycle.
    struct io_job*          root_next;
    struct io_job*          root_prev;
} io_job_t;

VTABLE_DECLARE_STRUCT(io_vtable, 16);
VTABLE_DECLARE_STRUCT(io_job_vtable, 0);

HIDDEN extern struct io_vtable IO_VTABLE;
HIDDEN extern struct io_job_vtable IO_JOB_VTABLE;

// Private threadpool lifecycle and submission.
HIDDEN void _io_threadpool_init(void);
HIDDEN void _io_enqueue(io_job_t* job);

#endif
