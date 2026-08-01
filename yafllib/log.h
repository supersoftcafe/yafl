// yafllib/log.h — structured logging and runtime metrics.
//
// See docs/logging-design.md. The contract in one line: YAFL supplies a level,
// a context, a format and up to three values; the RUNTIME supplies the clock,
// the formatting and the destination. YAFL never sees a date, a time, or a
// duration.
//
// Nothing here allocates on the YAFL heap or calls malloc on the hot path, so
// these are safe to call from any thread, from inside a pass being measured,
// and (later) from the collector itself.
#pragma once

#include "yafl.h"

// Standard levels. Any Int32 works; these are the ones with display names.
enum {
    YAFL_LOG_TRACE = 10,
    YAFL_LOG_DEBUG = 20,
    YAFL_LOG_INFO  = 30,
    YAFL_LOG_WARN  = 40,
    YAFL_LOG_ERROR = 50,
};

// Reads the environment and records argv[0] for the derived file name. Called
// once from thread_start; safe to call again (idempotent).
void yafl_log_init(const char* argv0);

// Flushes counters and unfinished spans. Called at exit.
void yafl_log_shutdown(void);

// True when `level` passes the threshold for `context`. Exposed so the runtime
// itself can gate expensive diagnostics; YAFL code does not need it, because
// the check is inside every log call.
bool yafl_log_enabled_c(int32_t level, const char* context);

// ── the emit matrix: level, context, format, then 0-3 Int/String values ──────
// Slots are {1}, {2}, {3} — the same syntax as stdlib/format.yafl.
// The foreign ABI is `object_t* fn(object_t* this, ...)` with a leading
// receiver, Int32 passed UNBOXED and everything else boxed (see the emitted C
// for print_string). The returned value is a tagged literal 0 — the result
// exists only because the convention wants one.
EXPORT object_t* yafl_log(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt);
EXPORT object_t* yafl_log_i(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a);
EXPORT object_t* yafl_log_s(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a);
EXPORT object_t* yafl_log_ii(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b);
EXPORT object_t* yafl_log_is(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b);
EXPORT object_t* yafl_log_si(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b);
EXPORT object_t* yafl_log_ss(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b);
EXPORT object_t* yafl_log_iii(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);
EXPORT object_t* yafl_log_iis(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);
EXPORT object_t* yafl_log_isi(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);
EXPORT object_t* yafl_log_iss(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);
EXPORT object_t* yafl_log_sii(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);
EXPORT object_t* yafl_log_sis(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);
EXPORT object_t* yafl_log_ssi(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);
EXPORT object_t* yafl_log_sss(object_t* self, int32_t lvl, object_t* ctx, object_t* fmt, object_t* a, object_t* b, object_t* c);

// ── metrics ─────────────────────────────────────────────────────────────────
// A span's start is kept by the runtime against the returned token; spanEnd
// prints the elapsed. YAFL never sees the number.
EXPORT object_t* yafl_log_span_begin(object_t* self, object_t* ctx, object_t* name);
EXPORT object_t* yafl_log_span_end(object_t* self, object_t* span);
// Counters aggregate in C and dump once at exit — cheap enough for a hot loop.
EXPORT object_t* yafl_log_count(object_t* self, object_t* ctx, object_t* name, object_t* n);
