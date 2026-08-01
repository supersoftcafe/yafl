// yafllib/log.c — structured logging and runtime metrics. See log.h and
// docs/logging-design.md.
//
// Design rules this file must not break:
//   1. No YAFL-heap allocation and no malloc on the emit path. Everything
//      formats into a thread-local stack buffer.
//   2. One write(2) per fully-formatted line, so lines from parallel workers
//      never interleave mid-line.
//   3. The destination is a FILE, opened lazily on first record. Never the
//      async IO path: io_t is single-threaded with one task per handle, and
//      logging has to work from GC workers and __parallel__ tasks.
//   4. Failure is silent-ish and never fatal: on open failure we fall back to
//      stderr and say so once.
#define _GNU_SOURCE
#include "log.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdatomic.h>
#include <pthread.h>

#define LOG_LINE_MAX    4096
#define LOG_CTX_MAX     64      // distinct contexts
#define LOG_CTX_NAME     32
#define LOG_COUNTER_MAX 256
#define LOG_SPAN_MAX    256

static int              _fd            = -1;
static bool             _initialised   = false;
static int32_t          _global_level  = 0;      // 0 = off
static char             _argv0[64]     = "yafl";
static pthread_mutex_t  _lock          = PTHREAD_MUTEX_INITIALIZER;

// ── contexts ────────────────────────────────────────────────────────────────
// A context interns to a small id carrying its effective level, so the
// suppressed path is a compare against a cached int rather than a getenv or a
// string walk.
typedef struct { char name[LOG_CTX_NAME]; int32_t level; } log_ctx_t;
static log_ctx_t _ctxs[LOG_CTX_MAX];
static int32_t   _ctx_count = 0;

typedef struct { int32_t ctx; char name[LOG_CTX_NAME]; int64_t value; } log_counter_t;
static log_counter_t _counters[LOG_COUNTER_MAX];
static int32_t       _counter_count = 0;

typedef struct { int32_t ctx; char name[LOG_CTX_NAME]; struct timespec t0; bool live; } log_span_t;
static log_span_t _spans[LOG_SPAN_MAX];
static int32_t    _span_count = 0;

// ── level names ─────────────────────────────────────────────────────────────
static const char* _level_name(int32_t lvl, char* scratch, size_t n) {
    switch (lvl) {
        case YAFL_LOG_TRACE: return "TRACE";
        case YAFL_LOG_DEBUG: return "DEBUG";
        case YAFL_LOG_INFO:  return "INFO ";
        case YAFL_LOG_WARN:  return "WARN ";
        case YAFL_LOG_ERROR: return "ERROR";
        default: snprintf(scratch, n, "%-5d", (int)lvl); return scratch;
    }
}

static int32_t _parse_level(const char* s) {
    if (s == NULL || *s == '\0') return 0;
    if (!strcasecmp(s, "trace")) return YAFL_LOG_TRACE;
    if (!strcasecmp(s, "debug")) return YAFL_LOG_DEBUG;
    if (!strcasecmp(s, "info"))  return YAFL_LOG_INFO;
    if (!strcasecmp(s, "warn"))  return YAFL_LOG_WARN;
    if (!strcasecmp(s, "error")) return YAFL_LOG_ERROR;
    if (!strcasecmp(s, "off"))   return 0;
    int v = atoi(s);
    return v > 0 ? v : 0;
}

// YAFL_LOG_<CONTEXT>, upper-cased, non-alphanumerics to '_'.
static int32_t _env_level_for(const char* ctx, int32_t dflt) {
    char var[LOG_CTX_NAME + 16];
    size_t at = 0;
    const char* p = "YAFL_LOG_";
    while (*p && at < sizeof(var) - 1) var[at++] = *p++;
    for (const char* c = ctx; *c && at < sizeof(var) - 1; c++) {
        char ch = *c;
        if (ch >= 'a' && ch <= 'z') ch = (char)(ch - 'a' + 'A');
        else if (!((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9'))) ch = '_';
        var[at++] = ch;
    }
    var[at] = '\0';
    const char* v = getenv(var);
    return v ? _parse_level(v) : dflt;
}

// ── destination ─────────────────────────────────────────────────────────────
// Derived:  ${YAFL_LOG_DIR}/yafl-<program>-<YYYYMMDD-HHMMSS>-<pid>.log
// The timestamp and pid together keep concurrent runs from colliding, which is
// the normal case when measuring. Not the CWD: a compiler must not litter a
// source tree.
static void _open_destination_locked(void) {
    if (_fd >= 0) return;

    char path[512];
    const char* exact = getenv("YAFL_LOG_FILE");
    if (exact && *exact) {
        snprintf(path, sizeof(path), "%s", exact);
    } else {
        const char* dir = getenv("YAFL_LOG_DIR");
        if (!dir || !*dir) dir = getenv("TMPDIR");
        if (!dir || !*dir) dir = "/tmp";
        struct timespec now;
        clock_gettime(CLOCK_REALTIME, &now);
        struct tm tmv;
        gmtime_r(&now.tv_sec, &tmv);
        char stamp[32];
        strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", &tmv);
        snprintf(path, sizeof(path), "%s/yafl-%s-%s-%d.log",
                 dir, _argv0, stamp, (int)getpid());
    }

    _fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
    if (_fd < 0) {
        // Never fatal. Say so once, then carry on down stderr.
        fprintf(stderr, "[yafl] could not open log file '%s'; logging to stderr\n", path);
        _fd = 2;
        return;
    }
    // A default destination you cannot find is a destination that does not
    // exist — so announce it exactly once.
    fprintf(stderr, "[yafl] logging to %s\n", path);
}

// ── context interning ───────────────────────────────────────────────────────
static int32_t _intern_locked(const char* name) {
    for (int32_t i = 0; i < _ctx_count; i++)
        if (!strcmp(_ctxs[i].name, name)) return i;
    if (_ctx_count >= LOG_CTX_MAX) return -1;
    int32_t id = _ctx_count++;
    snprintf(_ctxs[id].name, LOG_CTX_NAME, "%s", name);
    _ctxs[id].level = _env_level_for(name, _global_level);
    return id;
}

static int32_t _intern(const char* name) {
    pthread_mutex_lock(&_lock);
    int32_t id = _intern_locked(name);
    pthread_mutex_unlock(&_lock);
    return id;
}

void yafl_log_init(const char* argv0) {
    if (_initialised) return;
    _initialised = true;
    _global_level = _parse_level(getenv("YAFL_LOG"));
    if (argv0 && *argv0) {
        const char* base = strrchr(argv0, '/');
        snprintf(_argv0, sizeof(_argv0), "%s", base ? base + 1 : argv0);
    }
}

bool yafl_log_enabled_c(int32_t level, const char* context) {
    if (!_initialised) yafl_log_init(NULL);
    int32_t id = _intern(context);
    int32_t threshold = (id >= 0) ? _ctxs[id].level : _global_level;
    return threshold != 0 && level >= threshold;
}

// ── argument rendering (never allocates) ────────────────────────────────────
typedef struct { const char* p; char buf[64]; } log_arg_t;

static void _arg_int(log_arg_t* a, object_t* v) {
    integer_to_cstr(v, a->buf, (int32_t)sizeof(a->buf));
    a->p = a->buf;
}
static void _arg_str(log_arg_t* a, object_t* v) {
    // string_copy_cstr copies into OUR buffer and NUL-terminates, truncating
    // to fit. string_to_cstr's result is not NUL-terminated and may point into
    // the object, so it is the wrong tool here. Nothing is allocated either way.
    if (v == NULL) { a->buf[0] = '\0'; a->p = a->buf; return; }
    string_copy_cstr(v, a->buf, (int32_t)sizeof(a->buf));
    a->p = a->buf;
}

// Copy a YAFL string into a caller buffer, NUL-terminated, with a fallback.
static const char* _cstr(object_t* v, char* buf, int32_t size, const char* dflt) {
    if (v == NULL) return dflt;
    string_copy_cstr(v, buf, size);
    return buf[0] ? buf : dflt;
}

// Expand {1}/{2}/{3}. An index outside the arity renders as "?" (matching
// format.yafl), so a typo degrades visibly instead of aborting.
static int32_t _expand(char* out, int32_t cap, const char* fmt,
                       log_arg_t* args, int32_t argc) {
    int32_t at = 0;
    for (const char* p = fmt; *p && at < cap - 1; p++) {
        if (*p == '{' && p[1] >= '1' && p[1] <= '9' && p[2] == '}') {
            int32_t idx = p[1] - '1';
            const char* v = (idx < argc) ? args[idx].p : "?";
            while (*v && at < cap - 1) out[at++] = *v++;
            p += 2;
        } else {
            out[at++] = *p;
        }
    }
    out[at] = '\0';
    return at;
}

static void _emit(int32_t level, object_t* ctx_o, object_t* fmt_o,
                  log_arg_t* args, int32_t argc) {
    if (!_initialised) yafl_log_init(NULL);

    char ctx_local[LOG_CTX_NAME];
    const char* ctx = _cstr(ctx_o, ctx_local, (int32_t)sizeof(ctx_local), "?");

    int32_t id = _intern(ctx);
    int32_t threshold = (id >= 0) ? _ctxs[id].level : _global_level;
    if (threshold == 0 || level < threshold) return;      // the suppressed path

    char fmt_local[512];
    const char* fmt = _cstr(fmt_o, fmt_local, (int32_t)sizeof(fmt_local), "");

    char msg[LOG_LINE_MAX];
    _expand(msg, (int32_t)sizeof(msg), fmt, args, argc);

    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    struct tm tmv;
    gmtime_r(&now.tv_sec, &tmv);
    char stamp[40];
    strftime(stamp, sizeof(stamp), "%Y-%m-%dT%H:%M:%S", &tmv);

    char lvlbuf[8];
    char line[LOG_LINE_MAX];
    int n = snprintf(line, sizeof(line), "%s.%06ldZ %s t%02d %-16s %s\n",
                     stamp, now.tv_nsec / 1000,
                     _level_name(level, lvlbuf, sizeof(lvlbuf)),
                     (int)thread_current_id(), ctx, msg);
    if (n < 0) return;
    if (n > (int)sizeof(line)) n = (int)sizeof(line);

    pthread_mutex_lock(&_lock);
    _open_destination_locked();
    ssize_t ignored = write(_fd, line, (size_t)n);
    (void)ignored;
    pthread_mutex_unlock(&_lock);
}

// ── the emit matrix ─────────────────────────────────────────────────────────
#define ARG_I(slot, v) _arg_int(&a[slot], (v))
#define ARG_S(slot, v) _arg_str(&a[slot], (v))

EXPORT object_t* yafl_log(object_t* self, int32_t l, object_t* c, object_t* f) {
    (void)self; _emit(l, c, f, NULL, 0); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_i(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x) {
    log_arg_t a[1]; ARG_I(0,x); (void)self; _emit(l,c,f,a,1); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_s(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x) {
    log_arg_t a[1]; ARG_S(0,x); (void)self; _emit(l,c,f,a,1); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_ii(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y) {
    log_arg_t a[2]; ARG_I(0,x); ARG_I(1,y); (void)self; _emit(l,c,f,a,2); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_is(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y) {
    log_arg_t a[2]; ARG_I(0,x); ARG_S(1,y); (void)self; _emit(l,c,f,a,2); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_si(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y) {
    log_arg_t a[2]; ARG_S(0,x); ARG_I(1,y); (void)self; _emit(l,c,f,a,2); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_ss(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y) {
    log_arg_t a[2]; ARG_S(0,x); ARG_S(1,y); (void)self; _emit(l,c,f,a,2); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_iii(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_I(0,x); ARG_I(1,y); ARG_I(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_iis(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_I(0,x); ARG_I(1,y); ARG_S(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_isi(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_I(0,x); ARG_S(1,y); ARG_I(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_iss(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_I(0,x); ARG_S(1,y); ARG_S(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_sii(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_S(0,x); ARG_I(1,y); ARG_I(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_sis(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_S(0,x); ARG_I(1,y); ARG_S(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_ssi(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_S(0,x); ARG_S(1,y); ARG_I(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}
EXPORT object_t* yafl_log_sss(object_t* self, int32_t l, object_t* c, object_t* f, object_t* x, object_t* y, object_t* z) {
    log_arg_t a[3]; ARG_S(0,x); ARG_S(1,y); ARG_S(2,z); (void)self; _emit(l,c,f,a,3); return integer_from_int32_noalloc(0);
}

// ── metrics ─────────────────────────────────────────────────────────────────

EXPORT object_t* yafl_log_span_begin(object_t* self, object_t* ctx_o, object_t* name_o) {
    (void)self;
    if (!_initialised) yafl_log_init(NULL);
    char cb[LOG_CTX_NAME]; const char* ctx = _cstr(ctx_o,  cb, (int32_t)sizeof(cb), "?");
    char nb[LOG_CTX_NAME]; const char* nm  = _cstr(name_o, nb, (int32_t)sizeof(nb), "?");

    pthread_mutex_lock(&_lock);
    int32_t id = _intern_locked(ctx);
    int32_t slot = -1;
    if (_span_count < LOG_SPAN_MAX) slot = _span_count++;
    if (slot >= 0) {
        _spans[slot].ctx = id;
        snprintf(_spans[slot].name, LOG_CTX_NAME, "%s", nm);
        clock_gettime(CLOCK_MONOTONIC, &_spans[slot].t0);
        _spans[slot].live = true;
    }
    pthread_mutex_unlock(&_lock);
    return integer_from_int32_noalloc((int32_t)slot);   // opaque token; NOT a time
}

EXPORT object_t* yafl_log_span_end(object_t* self, object_t* span_o) {
    (void)self;
    int64_t span = int64_from_integer_truncate(span_o);
    if (span < 0 || span >= LOG_SPAN_MAX) return integer_from_int32_noalloc(0);
    struct timespec t1;
    clock_gettime(CLOCK_MONOTONIC, &t1);

    pthread_mutex_lock(&_lock);
    log_span_t* sp = &_spans[span];
    if (!sp->live) { pthread_mutex_unlock(&_lock); return integer_from_int32_noalloc(0); }
    sp->live = false;
    double secs = (double)(t1.tv_sec - sp->t0.tv_sec)
                + (double)(t1.tv_nsec - sp->t0.tv_nsec) / 1e9;
    const char* ctx = (sp->ctx >= 0) ? _ctxs[sp->ctx].name : "?";
    int32_t threshold = (sp->ctx >= 0) ? _ctxs[sp->ctx].level : _global_level;
    bool show = threshold != 0 || getenv("YAFL_LOG_METRICS");
    if (show) {
        struct timespec now; clock_gettime(CLOCK_REALTIME, &now);
        struct tm tmv; gmtime_r(&now.tv_sec, &tmv);
        char stamp[40]; strftime(stamp, sizeof(stamp), "%Y-%m-%dT%H:%M:%S", &tmv);
        char line[LOG_LINE_MAX];
        int n = snprintf(line, sizeof(line), "%s.%06ldZ SPAN  t%02d %-16s %s %.3fs\n",
                         stamp, now.tv_nsec / 1000, (int)thread_current_id(),
                         ctx, sp->name, secs);
        if (n > 0) {
            _open_destination_locked();
            ssize_t ignored = write(_fd, line, (size_t)(n > (int)sizeof(line) ? (int)sizeof(line) : n));
            (void)ignored;
        }
    }
    pthread_mutex_unlock(&_lock);
    return 0;
}

EXPORT object_t* yafl_log_count(object_t* self, object_t* ctx_o, object_t* name_o, object_t* n_o) {
    (void)self;
    if (!_initialised) yafl_log_init(NULL);
    char cb[LOG_CTX_NAME]; const char* ctx = _cstr(ctx_o,  cb, (int32_t)sizeof(cb), "?");
    char nb[LOG_CTX_NAME]; const char* nm  = _cstr(name_o, nb, (int32_t)sizeof(nb), "?");
    int64_t delta = int64_from_integer_truncate(n_o);

    pthread_mutex_lock(&_lock);
    int32_t id = _intern_locked(ctx);
    for (int32_t i = 0; i < _counter_count; i++) {
        if (_counters[i].ctx == id && !strcmp(_counters[i].name, nm)) {
            _counters[i].value += delta;
            pthread_mutex_unlock(&_lock);
            return integer_from_int32_noalloc(0);
        }
    }
    if (_counter_count < LOG_COUNTER_MAX) {
        int32_t i = _counter_count++;
        _counters[i].ctx = id;
        snprintf(_counters[i].name, LOG_CTX_NAME, "%s", nm);
        _counters[i].value = delta;
    }
    pthread_mutex_unlock(&_lock);
    return integer_from_int32_noalloc(0);
}

void yafl_log_shutdown(void) {
    if (!_initialised) return;
    bool want = _global_level != 0 || getenv("YAFL_LOG_METRICS") != NULL;
    if (!want || _counter_count == 0) return;

    pthread_mutex_lock(&_lock);
    _open_destination_locked();
    struct timespec now; clock_gettime(CLOCK_REALTIME, &now);
    struct tm tmv; gmtime_r(&now.tv_sec, &tmv);
    char stamp[40]; strftime(stamp, sizeof(stamp), "%Y-%m-%dT%H:%M:%S", &tmv);
    for (int32_t i = 0; i < _counter_count; i++) {
        char line[LOG_LINE_MAX];
        int n = snprintf(line, sizeof(line), "%s.%06ldZ COUNT t%02d %-16s %s %lld\n",
                         stamp, now.tv_nsec / 1000, (int)thread_current_id(),
                         _ctxs[_counters[i].ctx].name, _counters[i].name,
                         (long long)_counters[i].value);
        if (n > 0) {
            ssize_t ignored = write(_fd, line, (size_t)(n > (int)sizeof(line) ? (int)sizeof(line) : n));
            (void)ignored;
        }
    }
    pthread_mutex_unlock(&_lock);
}
