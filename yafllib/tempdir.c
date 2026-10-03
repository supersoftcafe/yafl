// yafllib/tempdir.c — the per-process temporary folder (see tempdir.h).
#include "yafl.h"
#include "tempdir.h"

#include <dirent.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

static pthread_once_t _tempdir_once = PTHREAD_ONCE_INIT;
static char*          _tempdir_path;      // NULL until created, or on failure
static pid_t          _tempdir_owner;     // the pid that created it
static pthread_mutex_t _tempdir_cleanup_lock = PTHREAD_MUTEX_INITIALIZER;

// tempfile.gettempdir(): TMPDIR, then TEMP, then TMP, then /tmp — the first
// that is set and non-empty. The Python compiler resolves the same way, so
// both put their folders side by side.
static const char* _base_dir(void) {
    static const char* const vars[] = { "TMPDIR", "TEMP", "TMP" };
    for (size_t i = 0; i < sizeof vars / sizeof vars[0]; i++) {
        const char* v = getenv(vars[i]);
        if (v != NULL && *v) return v;
    }
    return "/tmp";
}

static void _tempdir_create(void) {
    const char* base = _base_dir();
    size_t blen = strlen(base);
    while (blen > 1 && base[blen - 1] == '/') blen--;   // "/tmp/" -> "/tmp"

    // "<base>/yafl-<pid>-XXXXXX": the pid makes a stray folder traceable to
    // its process; mkdtemp's suffix makes it unique even across pid reuse.
    size_t size = blen + 64;
    char* path = malloc(size);
    if (path == NULL) return;
    snprintf(path, size, "%.*s/yafl-%ld-XXXXXX", (int)blen, base, (long)getpid());
    if (mkdtemp(path) == NULL) {   // creates with mode 0700
        free(path);
        return;
    }
    _tempdir_owner = getpid();
    _tempdir_path  = path;
    atexit(yafl_tempdir_cleanup);
}

HIDDEN const char* yafl_tempdir(void) {
    pthread_once(&_tempdir_once, _tempdir_create);
    return _tempdir_path;
}

// Remove everything inside the directory open on `dfd`, then close it.
// Entries are lstat'ed (AT_SYMLINK_NOFOLLOW) and a symlink is unlinked as a
// file, so the walk never leaves the folder. Best effort: an entry that cannot
// be removed is skipped and its parent's rmdir then fails harmlessly.
static void _remove_contents(int dfd) {
    DIR* d = fdopendir(dfd);
    if (d == NULL) { close(dfd); return; }
    struct dirent* e;
    while ((e = readdir(d)) != NULL) {
        const char* n = e->d_name;
        if (n[0] == '.' && (n[1] == 0 || (n[1] == '.' && n[2] == 0))) continue;
        struct stat st;
        if (fstatat(dfd, n, &st, AT_SYMLINK_NOFOLLOW) != 0) continue;
        if (S_ISDIR(st.st_mode)) {
            int sub = openat(dfd, n, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
            if (sub >= 0) _remove_contents(sub);
            unlinkat(dfd, n, AT_REMOVEDIR);
        } else {
            unlinkat(dfd, n, 0);
        }
    }
    closedir(d);   // also closes dfd
}

HIDDEN void yafl_tempdir_cleanup(void) {
    pthread_mutex_lock(&_tempdir_cleanup_lock);
    char* path = _tempdir_path;
    if (path != NULL && getpid() == _tempdir_owner) {
        int dfd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
        if (dfd >= 0) _remove_contents(dfd);
        rmdir(path);
        // The string stays allocated: a thread still running during exit may
        // have just been handed it by yafl_tempdir.
    }
    pthread_mutex_unlock(&_tempdir_cleanup_lock);
}

// System::tempDir — `String|None`, None when the folder could not be created.
// Same representation as sys_getenv (object.c): None is word 0.
EXPORT str_t sys_tempdir(object_t* self) {
    (void)self;
    const char* p = yafl_tempdir();
    return p == NULL ? str_word(NULL) : str_from_cstr(p);
}
