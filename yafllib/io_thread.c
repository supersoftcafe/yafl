#include "yafl.h"
#include "io_internal.h"

#include <pthread.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <spawn.h>
#include <poll.h>
#include <fcntl.h>

extern char** environ;

#define IO_THREAD_COUNT 4


// IO_JOB_VTABLE.  is_mutable=1 keeps the page from being compacted, and
// every GC-pointer field on the job is listed in the mask: tracing
// through next_in_io_queue is redundant with the per-handle in_flight
// rooting in normal operation, but the mask is a contract — every GC
// pointer the struct holds *must* be declared.
HIDDEN struct io_job_vtable IO_JOB_VTABLE = {
    .object_size              = sizeof(io_job_t),
    .array_el_size            = 0,
    .object_pointer_locations = maskof(io_job_t, .task.callback.o)
                              | maskof(io_job_t, .task.next)
                              | maskof(io_job_t, .task.result)
                              | maskof(io_job_t, .next_in_io_queue)
                              | maskof(io_job_t, .io)
                              | maskof(io_job_t, .completion_task)
                              | maskof(io_job_t, .fs_aux)
                              | maskof(io_job_t, .dir),
    .array_el_pointer_locations = 0,
    .functions_mask           = 0,
    .array_len_offset         = 0,
    .is_mutable               = 1,
    .name                     = "io_job",
    .implements_array         = VTABLE_IMPLEMENTS(0),
};


// Plain mutex+condvar MPMC queue.  No GC roots are required here: every
// in-flight job is rooted via io_t.in_flight (or, for OPEN, via the
// task's reachability through the caller's state's my_task → task → io).
static pthread_mutex_t _io_queue_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  _io_queue_cond = PTHREAD_COND_INITIALIZER;
static io_job_t*       _io_queue_head = NULL;
static io_job_t*       _io_queue_tail = NULL;


HIDDEN void _io_enqueue(io_job_t* job) {
    atomic_store(&job->next_in_io_queue, NULL);
    pthread_mutex_lock(&_io_queue_lock);
    if (_io_queue_tail) {
        atomic_store(&_io_queue_tail->next_in_io_queue, job);
        _io_queue_tail = job;
    } else {
        _io_queue_head = job;
        _io_queue_tail = job;
    }
    pthread_cond_signal(&_io_queue_cond);
    pthread_mutex_unlock(&_io_queue_lock);
}


static io_job_t* _io_dequeue(void) {
    pthread_mutex_lock(&_io_queue_lock);
    while (_io_queue_head == NULL) {
        pthread_cond_wait(&_io_queue_cond, &_io_queue_lock);
    }
    io_job_t* job = _io_queue_head;
    io_job_t* next = atomic_load(&job->next_in_io_queue);
    _io_queue_head = next;
    if (next == NULL) _io_queue_tail = NULL;
    atomic_store(&job->next_in_io_queue, NULL);
    pthread_mutex_unlock(&_io_queue_lock);
    return job;
}


// Append `n` bytes to a growable malloc buffer, doubling capacity as needed.
// Non-GC memory, so this is safe to call on the IO thread.
static void _spawn_append(char** buf, int32_t* len, int32_t* cap,
                          const char* data, int32_t n) {
    if (*len + n > *cap) {
        int32_t newcap = *cap ? *cap : 4096;
        while (*len + n > newcap) newcap *= 2;
        *buf = (char*)realloc(*buf, (size_t)newcap);
        *cap = newcap;
    }
    memcpy(*buf + *len, data, (size_t)n);
    *len += n;
}


// Run the child to completion, capturing stdout/stderr in full and the exit
// status.  stdin is /dev/null.  poll() drains both pipes concurrently so a
// child that fills one pipe while we are reading the other cannot deadlock.
static void _io_run_spawn(io_job_t* job) {
    spawn_aux_t* sx = job->spawn;
    int out_pipe[2] = { -1, -1 };
    int err_pipe[2] = { -1, -1 };
    if (pipe(out_pipe) != 0 || pipe(err_pipe) != 0) {
        job->raw_result = -errno;
        if (out_pipe[0] >= 0) { close(out_pipe[0]); close(out_pipe[1]); }
        if (err_pipe[0] >= 0) { close(err_pipe[0]); close(err_pipe[1]); }
        return;
    }

    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_addopen(&fa, 0, "/dev/null", O_RDONLY, 0);
    posix_spawn_file_actions_adddup2(&fa, out_pipe[1], 1);
    posix_spawn_file_actions_adddup2(&fa, err_pipe[1], 2);
    posix_spawn_file_actions_addclose(&fa, out_pipe[0]);
    posix_spawn_file_actions_addclose(&fa, out_pipe[1]);
    posix_spawn_file_actions_addclose(&fa, err_pipe[0]);
    posix_spawn_file_actions_addclose(&fa, err_pipe[1]);

    pid_t pid;
    int rc = posix_spawnp(&pid, sx->argv[0], &fa, NULL, sx->argv, environ);
    posix_spawn_file_actions_destroy(&fa);
    close(out_pipe[1]);
    close(err_pipe[1]);
    if (rc != 0) {
        close(out_pipe[0]);
        close(err_pipe[0]);
        job->raw_result = -rc;   // posix_spawnp returns an errno value
        return;
    }

    struct pollfd fds[2];
    fds[0].fd = out_pipe[0]; fds[0].events = POLLIN;
    fds[1].fd = err_pipe[0]; fds[1].events = POLLIN;
    int open_count = 2;
    char tmp[4096];
    while (open_count > 0) {
        if (poll(fds, 2, -1) < 0) {
            if (errno == EINTR) continue;
            break;
        }
        for (int i = 0; i < 2; i++) {
            if (fds[i].fd < 0 || fds[i].revents == 0) continue;
            ssize_t n = read(fds[i].fd, tmp, sizeof tmp);
            if (n > 0) {
                if (i == 0) _spawn_append(&sx->out, &sx->out_len, &sx->out_cap, tmp, (int32_t)n);
                else        _spawn_append(&sx->err, &sx->err_len, &sx->err_cap, tmp, (int32_t)n);
            } else if (n < 0 && errno == EINTR) {
                continue;
            } else {                       // EOF (0) or hard error: this fd is done
                close(fds[i].fd);
                fds[i].fd = -1;
                open_count--;
            }
        }
    }
    if (fds[0].fd >= 0) close(fds[0].fd);
    if (fds[1].fd >= 0) close(fds[1].fd);

    int status = 0;
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) { }
    if (WIFEXITED(status))        sx->exit_code = WEXITSTATUS(status);
    else if (WIFSIGNALED(status)) sx->exit_code = -WTERMSIG(status);
    else                          sx->exit_code = -1;
    job->raw_result = 0;
}


static void* _io_thread_main(void* arg) {
    (void)arg;

    for (;;) {
        io_job_t* job = _io_dequeue();
        io_t*     io  = job->io;

        switch (job->op) {
        case IO_OP_REFILL: {
            errno = 0;
            size_t n = fread(io->buf, 1, IO_BUFFER_SIZE, io->file);
            if (n > 0) {
                job->raw_result = (int32_t)n;
            } else if (feof(io->file)) {
                job->raw_result = 0;
                job->eof = true;
            } else {
                job->raw_result = -errno;
            }
        } break;

        case IO_OP_FLUSH_WRITE: {
            errno = 0;
            size_t n = fwrite(io->buf, 1, (size_t)io->buf_tail, io->file);
            job->raw_result = (n < (size_t)io->buf_tail) ? -errno : (int32_t)n;
        } break;

        case IO_OP_OPEN: {
            // Path is in io->buf, null-terminated by the worker.
            errno = 0;
            FILE* f = fopen((const char*)io->buf, job->open_mode);
            if (f) setvbuf(f, NULL, _IONBF, 0);   // we buffer in io_t, not stdio
            io->file = f;                          // non-GC field; safe to write
            job->raw_result = f ? 0 : -errno;
        } break;

        case IO_OP_CLOSE: {
            errno = 0;
            int32_t rc = 0;
            if (io->buf_tail > 0) {
                size_t n = fwrite(io->buf, 1, (size_t)io->buf_tail, io->file);
                if (n < (size_t)io->buf_tail) rc = -errno;
            }
            if (io->owned && fclose(io->file) != 0 && rc == 0) {
                rc = -errno;
            }
            job->raw_result = rc;
        } break;

        case IO_OP_FS_EXISTS: {
            // access() with F_OK distinguishes "exists" from "doesn't exist"
            // and from "exists but isn't readable" (the latter still counts
            // as existing).  Any non-zero return collapses to false.
            job->raw_result = (access((const char*)io->buf, F_OK) == 0) ? 1 : 0;
        } break;

        case IO_OP_FS_STAT: {
            // stat() writes a struct stat; we extract just the five fields
            // YAFL cares about into the pre-allocated fs_aux.  No allocation,
            // no GC interaction — fs_aux is on an is_mutable=1 page.
            struct stat st;
            errno = 0;
            if (stat((const char*)io->buf, &st) == 0) {
                fs_file_info_t* fi = job->fs_aux;
                // off_t / time_t can exceed int32; we truncate.  Source files
                // up to 2 GiB and mtime through 2038 fit; extending the
                // integer API to int64 is a separate change.
                fi->size       = (int32_t)st.st_size;
                fi->mtime      = (int32_t)st.st_mtime;
                fi->mode       = (int32_t)st.st_mode;
                fi->is_dir     = S_ISDIR(st.st_mode);
                fi->is_regular = S_ISREG(st.st_mode);
                job->raw_result = 0;
            } else {
                job->raw_result = -errno;
            }
        } break;

        case IO_OP_DIR_OPEN: {
            dir_t* dir = job->dir;
            errno = 0;
            DIR* dp = opendir(dir->path_buf);
            dir->dirp = dp;             // non-GC field; safe to write
            job->raw_result = dp ? 0 : -errno;
        } break;

        case IO_OP_DIR_NEXT: {
            dir_t* dir = job->dir;
            dir->entry_ready = false;
            dir->entry_eof   = false;
            errno = 0;
            struct dirent* de = readdir(dir->dirp);
            if (de != NULL) {
                // Copy name (NAME_MAX is the libc cap; entry_buf is NAME_MAX+2).
                size_t n = strlen(de->d_name);
                if (n > NAME_MAX) n = NAME_MAX;
                memcpy(dir->entry_buf, de->d_name, n);
                dir->entry_buf[n] = 0;
                dir->entry_ready = true;
                job->raw_result = (int32_t)n;
            } else if (errno == 0) {
                dir->entry_eof = true;
                job->raw_result = 0;
            } else {
                job->raw_result = -errno;
            }
        } break;

        case IO_OP_DIR_CLOSE: {
            dir_t* dir = job->dir;
            errno = 0;
            int32_t rc = 0;
            if (dir->dirp != NULL) {
                if (closedir(dir->dirp) != 0) rc = -errno;
                dir->dirp = NULL;
            }
            job->raw_result = rc;
        } break;

        case IO_OP_SPAWN: {
            _io_run_spawn(job);
        } break;
        }

        // Hand the completion task back to its originating worker.  The
        // completion_task is pre-allocated and its callback registered at job
        // creation, so the IO thread does no allocation and no GC writes here.
        thread_work_post((object_t*)job->completion_task);
    }
    return NULL;
}


HIDDEN void _io_threadpool_init(void) {
    for (intptr_t i = 0; i < IO_THREAD_COUNT; ++i) {
        pthread_t t;
        pthread_create(&t, NULL, _io_thread_main, (void*)i);
    }
}
