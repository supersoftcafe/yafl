// The page allocator never hands out a page past the end of the heap.
//
// A heap whose size is not a whole number of 32-page blocks ends part-way
// through its last block, and the density index lists that block like any
// other (it can never count as full). Once every real page is in use, the
// near-OOM fallback searched that block's whole 32 pages, found the bytes past
// the end of the page map reading FREE, and returned a page beyond the heap
// instead of aborting out of memory (#134).
//
// In a child process, a 1000k heap (62 pages: one whole block, one of 30) is
// filled with single pages, every one checked to lie inside the heap, and then
// one more is asked for. The child must die by SIGABRT (out of pages); a page
// handed back, inside the heap or not, is a failure.

#include "../yafl.h"   // first: sets the POSIX feature-test macros (setenv)
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

extern size_t memory_total_pages(void);

enum { CHILD_OUTSIDE = 3, CHILD_SPARE = 4 };

static int child(void) {
    setenv("YAFL_HEAP_SIZE", "1000k", 1);   // before the first allocation sizes the heap
    void* first = memory_pages_alloc(1);
    size_t total = memory_total_pages();
    char* lo = _memory_heap_base;
    char* hi = lo + total * (size_t)GC_PAGE_SIZE;
    if ((char*)first < lo || (char*)first >= hi) return CHILD_OUTSIDE;
    for (size_t i = 1; i < total; ++i) {
        char* p = memory_pages_alloc(1);
        if (p < lo || p >= hi) {
            fprintf(stderr, "page %zu of %zu handed out at index %zu, past the heap's end\n",
                    i, total, (size_t)(p - lo) / GC_PAGE_SIZE);
            return CHILD_OUTSIDE;
        }
    }
    char* extra = memory_pages_alloc(1);   // must abort: the heap is full
    fprintf(stderr, "a full heap of %zu pages handed out one more, at index %zu\n",
            total, (size_t)(extra - lo) / GC_PAGE_SIZE);
    return (extra < lo || extra >= hi) ? CHILD_OUTSIDE : CHILD_SPARE;
}

int main(void) {
    printf("=== mmap heap end test ===\n");
    fflush(stdout);
    pid_t pid = fork();
    if (pid < 0) { perror("fork"); return 1; }
    if (pid == 0) _exit(child());
    int status = 0;
    if (waitpid(pid, &status, 0) != pid) { perror("waitpid"); return 1; }
    if (WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT) {
        printf("  a full heap aborts instead of handing out a page past its end  OK\n");
        return 0;
    }
    if (WIFEXITED(status))
        printf("  FAIL: the child exited %d (%s)\n", WEXITSTATUS(status),
               WEXITSTATUS(status) == CHILD_OUTSIDE ? "a page past the heap's end"
             : WEXITSTATUS(status) == CHILD_SPARE   ? "a page from a full heap" : "?");
    else
        printf("  FAIL: the child died by signal %d\n", WIFSIGNALED(status) ? WTERMSIG(status) : -1);
    return 1;
}
