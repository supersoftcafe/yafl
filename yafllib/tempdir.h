// yafllib/tempdir.h — the per-process temporary folder, runtime-internal side.
//
// On first use the runtime creates ONE uniquely named sub-folder of the host
// temp directory, `<TMPDIR>/yafl-<pid>-XXXXXX` (mode 0700), and that is the
// folder a YAFL program is told about (System::tempDir, via sys_tempdir in
// yafl.h). Everything a program puts there is its own: no other YAFL process
// shares it, so nothing in it needs locking, keying or invalidating. The
// folder and all of its contents are deleted when the process exits.
#pragma once

#include "yafl.h"

// The folder's absolute path, creating it on the first call. Thread-safe;
// every call returns the same string, which lives for the whole process.
// NULL if it could not be created — remembered, not retried.
HIDDEN const char* yafl_tempdir(void);

// Delete the folder and everything under it, without following symlinks.
// Registered with atexit when the folder is created, and also called on the
// abort path (log_error_and_exit), which skips atexit. A no-op if the folder
// was never created, was already removed, or this process is a fork() child
// of its creator — a child must never delete its parent's folder. Idempotent.
HIDDEN void yafl_tempdir_cleanup(void);
