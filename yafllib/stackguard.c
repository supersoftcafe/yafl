// Stack-overflow detection.
//
// A thread that blows its C stack (e.g. unbounded or too-deep recursion — note
// that YAFL's synchronous async-hot-path runs such recursion on the C stack)
// otherwise dies with a bare SIGSEGV. This turns that specific case into a clean
// diagnostic and a defined exit code, while leaving every other fault to behave
// exactly as before (default disposition, core dump).
//
// Mechanism: a SIGSEGV/SIGBUS handler runs on a per-thread *alternate* signal
// stack (sigaltstack) so it still works when the normal stack is exhausted. It
// classifies the fault as an overflow when the faulting address lies just below
// the thread's stack limit; anything else is re-raised on the default handler.
//
// pthread_getattr_np is a GNU extension, so this one file opts into _GNU_SOURCE
// (the rest of the runtime stays strict-POSIX via yafl.h's feature macros).
#define _GNU_SOURCE
#include "yafl.h"
#include <signal.h>
#include <pthread.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>

#define _YAFL_ALTSTACK_SIZE   32768
// How far below the recorded stack limit a fault still counts as an overflow.
// An overflowing recursion faults within roughly one frame below the limit; a
// wild pointer this close to the stack is vanishingly unlikely.
#define _YAFL_OVERFLOW_SLACK  65536

static __thread char  _yafl_altstack[_YAFL_ALTSTACK_SIZE];
static __thread char* _yafl_stack_low = NULL;   // lowest valid stack address (stack grows down)

static void _yafl_fault_handler(int sig, siginfo_t* info, void* ctx) {
    (void)ctx;
    char* addr = (char*)info->si_addr;
    if (_yafl_stack_low != NULL
            && addr <  _yafl_stack_low
            && addr >= _yafl_stack_low - _YAFL_OVERFLOW_SLACK) {
        static const char msg[] =
            "yafl: stack overflow — call depth exceeded the thread stack "
            "(unbounded or too-deep recursion?)\n";
        ssize_t n = write(STDERR_FILENO, msg, sizeof(msg) - 1);
        (void)n;
        _exit(134);   // 128 + SIGABRT: the conventional fatal-signal exit code
    }
    // Not a stack overflow: restore the default disposition and re-raise so the
    // process dies exactly as it would have (core dump, debugger, …).
    signal(sig, SIG_DFL);
    raise(sig);
}

static pthread_once_t _yafl_handler_once = PTHREAD_ONCE_INIT;

static void _yafl_install_handler(void) {
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = _yafl_fault_handler;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
}

// Called once per thread, early (from gc_declare_thread): install the handler
// (process-wide, on first call), register this thread's alternate signal stack,
// and record its stack limit so the handler can recognise an overflow.
EXPORT void yafl_stack_guard_init(void) {
    pthread_once(&_yafl_handler_once, _yafl_install_handler);

    stack_t ss;
    ss.ss_sp = _yafl_altstack;
    ss.ss_size = sizeof _yafl_altstack;
    ss.ss_flags = 0;
    sigaltstack(&ss, NULL);

    pthread_attr_t attr;
    if (pthread_getattr_np(pthread_self(), &attr) == 0) {
        void* base;
        size_t size;
        if (pthread_attr_getstack(&attr, &base, &size) == 0) {
            _yafl_stack_low = (char*)base;
        }
        pthread_attr_destroy(&attr);
    }
}
