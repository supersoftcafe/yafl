// test_tempdir — the per-process temporary folder (tempdir.c).
//
// Runs without the YAFL scheduler: yafl_tempdir is plain C and allocates
// nothing on the YAFL heap.
#include "../yafl.h"
#include "../tempdir.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static int failed = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { printf("FAIL line %d: %s\n", __LINE__, msg); failed++; } } while (0)

static bool is_dir(const char* p) {
    struct stat st;
    return lstat(p, &st) == 0 && S_ISDIR(st.st_mode);
}

static bool exists(const char* p) {
    struct stat st;
    return lstat(p, &st) == 0;
}

static void write_file(const char* p, const char* body) {
    FILE* f = fopen(p, "w");
    if (f) { fputs(body, f); fclose(f); }
}

static void join(char* out, size_t n, const char* a, const char* b) {
    snprintf(out, n, "%s/%s", a, b);
}

int main(void) {
    // Point the runtime at a private base so the test cannot see or touch any
    // other process's folder.
    char base[] = "/tmp/yafl-tempdir-test-XXXXXX";
    if (mkdtemp(base) == NULL) { printf("FAIL: mkdtemp\n"); return 1; }
    setenv("TMPDIR", base, 1);

    // A child that uses the folder and exits normally leaves nothing behind.
    fflush(stdout);
    pid_t c = fork();
    if (c == 0) {
        const char* p = yafl_tempdir();
        if (p == NULL) _exit(2);
        char f[4096];
        join(f, sizeof f, p, "x");
        write_file(f, "x");
        exit(0);   // atexit cleanup runs
    }
    int status = 0;
    waitpid(c, &status, 0);
    CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0, "child failed");
    CHECK(rmdir(base) == 0, "child's folder survived its exit");
    CHECK(mkdir(base, 0700) == 0, "recreate base");
    printf("  exit_removes_the_folder                      %s\n", failed ? "" : "OK");

    // Same folder every call, under the base, mode 0700, named yafl-<pid>-*.
    const char* p = yafl_tempdir();
    CHECK(p != NULL, "yafl_tempdir returned NULL");
    if (p == NULL) return 1;
    CHECK(yafl_tempdir() == p, "second call returned a different path");
    CHECK(is_dir(p), "folder does not exist");
    char prefix[256];
    snprintf(prefix, sizeof prefix, "%s/yafl-%ld-", base, (long)getpid());
    CHECK(strncmp(p, prefix, strlen(prefix)) == 0, "folder not named <base>/yafl-<pid>-*");
    struct stat st;
    CHECK(stat(p, &st) == 0 && (st.st_mode & 0777) == 0700, "folder mode is not 0700");
    printf("  one_private_folder_per_process               OK\n");

    // Populate: nested dirs, files, and a symlink to a directory OUTSIDE the
    // folder — cleanup must unlink the link, not walk into its target.
    char outside[4096], keep[4096], a[4096], ab[4096], f1[4096], f2[4096], link[4096];
    join(outside, sizeof outside, base, "outside");
    join(keep, sizeof keep, outside, "keep");
    mkdir(outside, 0700);
    write_file(keep, "keep");
    join(a, sizeof a, p, "a");
    join(ab, sizeof ab, a, "b");
    join(f1, sizeof f1, a, "f1");
    join(f2, sizeof f2, ab, "f2");
    join(link, sizeof link, ab, "link");
    CHECK(mkdir(a, 0700) == 0 && mkdir(ab, 0700) == 0, "mkdir inside folder");
    write_file(f1, "1");
    write_file(f2, "2");
    CHECK(symlink(outside, link) == 0, "symlink");

    // A forked child exiting must not delete its PARENT's folder.
    fflush(stdout);
    c = fork();
    if (c == 0) {
        (void)yafl_tempdir();   // inherited path, not the child's own
        exit(0);
    }
    waitpid(c, &status, 0);
    CHECK(exists(f2), "a fork child's exit deleted the parent's folder");
    printf("  fork_child_leaves_parent_folder              OK\n");

    yafl_tempdir_cleanup();
    CHECK(!exists(p), "cleanup left the folder behind");
    CHECK(exists(keep), "cleanup followed a symlink out of the folder");
    yafl_tempdir_cleanup();   // idempotent
    printf("  cleanup_removes_all_and_stays_inside         OK\n");

    unlink(keep);
    rmdir(outside);
    rmdir(base);
    printf("tempdir: %s\n", failed ? "FAILED" : "all passed");
    return failed ? 1 : 0;
}
