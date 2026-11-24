// test_exe_path — the executable's real path (exepath.c), found by the OS and,
// failing that, from argv[0] and PATH (#145).
//
// Plain C, no YAFL scheduler. The program runs itself again, by a bare name on
// PATH, through a symlink in another directory: that child asks for its path
// and the parent checks it is this binary's real one, not the link's.
#include "../yafl.h"
#include "../exepath.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static int failed = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { printf("FAIL line %d: %s\n", __LINE__, msg); failed++; } } while (0)

static void write_file(const char* p, const char* body, mode_t mode) {
    FILE* f = fopen(p, "w");
    if (f) { fputs(body, f); fclose(f); }
    chmod(p, mode);
}

int main(int argc, char** argv) {
    // Child: say where the OS and argv[0] put this executable, then stop.
    if (argc > 1 && strcmp(argv[1], "child") == 0) {
        char by_name[PATH_MAX];
        const char* os = yafl_exe_path();
        bool b = yafl_exe_path_from_argv0(argv[0], by_name, sizeof by_name);
        printf("%s\n%s\n", os ? os : "-", b ? by_name : "-");
        return 0;
    }

    char self[PATH_MAX];
    if (realpath(argv[0], self) == NULL) { printf("FAIL: realpath of self\n"); return 1; }

    char base_tmpl[] = "/tmp/yafl-exepath-test-XXXXXX";
    char* base = mkdtemp(base_tmpl);
    if (base == NULL) { printf("FAIL: mkdtemp\n"); return 1; }
    char base_real[PATH_MAX], bin[PATH_MAX + 8], link[PATH_MAX + 64], plain[PATH_MAX + 64], cmd[PATH_MAX + 64];
    realpath(base, base_real);                  // /tmp may itself be a link
    snprintf(bin, sizeof bin, "%s/bin", base_real);
    mkdir(bin, 0700);
    snprintf(link, sizeof link, "%s/yafl-exe-path-link", bin);
    if (symlink(self, link) != 0) { printf("FAIL: symlink\n"); return 1; }
    snprintf(plain, sizeof plain, "%s/not-executable", bin);
    write_file(plain, "x", 0600);

    // (1) By a bare name on PATH, through a link: both routes name the target.
    char path[PATH_MAX * 2];
    snprintf(path, sizeof path, "/nonexistent:%s:/also/missing", bin);
    snprintf(cmd, sizeof cmd, "yafl-exe-path-link");
    int pipefd[2];
    if (pipe(pipefd) != 0) { printf("FAIL: pipe\n"); return 1; }
    pid_t pid = fork();
    if (pid == 0) {
        dup2(pipefd[1], STDOUT_FILENO);
        close(pipefd[0]); close(pipefd[1]);
        setenv("PATH", path, 1);
        execlp(cmd, cmd, "child", (char*)NULL);
        _exit(127);
    }
    close(pipefd[1]);
    char out[PATH_MAX * 2 + 4] = "";
    ssize_t got = read(pipefd[0], out, sizeof out - 1);
    close(pipefd[0]);
    int status = 0;
    waitpid(pid, &status, 0);
    CHECK(got > 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0, "the child ran");
    if (got > 0) out[got] = 0;
    char* nl = strchr(out, '\n');
    CHECK(nl != NULL, "the child printed two lines");
    if (nl != NULL) {
        *nl = 0;
        char* second = nl + 1;
        char* nl2 = strchr(second, '\n');
        if (nl2) *nl2 = 0;
        CHECK(strcmp(out, self) == 0, "the OS route names the real file, not the link");
        CHECK(strcmp(second, self) == 0, "argv[0] on PATH names the real file, not the link");
    }

    // (2) argv[0] with a directory, relative to the working directory.
    char got_path[PATH_MAX];
    CHECK(chdir(bin) == 0, "chdir");
    CHECK(yafl_exe_path_from_argv0("./yafl-exe-path-link", got_path, sizeof got_path)
          && strcmp(got_path, self) == 0, "a relative path is resolved");

    // (3) What a shell would not start: missing, or not executable.
    setenv("PATH", bin, 1);
    CHECK(!yafl_exe_path_from_argv0("no-such-program", got_path, sizeof got_path), "missing name");
    CHECK(!yafl_exe_path_from_argv0("not-executable", got_path, sizeof got_path), "not executable");
    CHECK(!yafl_exe_path_from_argv0("", got_path, sizeof got_path), "empty name");

    // (4) A buffer too small for the answer fails rather than truncating.
    CHECK(!yafl_exe_path_from_argv0(link, got_path, 8), "buffer too small");

    // (5) The OS route, in this process.
    const char* os_path = yafl_exe_path();
    CHECK(os_path != NULL && strcmp(os_path, self) == 0, "yafl_exe_path names this binary");
    CHECK(yafl_exe_path() == os_path, "and keeps it");

    chdir("/");
    unlink(link); unlink(plain); rmdir(bin); rmdir(base);
    if (failed) { printf("test_exe_path: %d FAILED\n", failed); return 1; }
    printf("test_exe_path: OK\n");
    return 0;
}
