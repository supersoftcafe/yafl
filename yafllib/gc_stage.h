// The collector's stages: the values of `stage` (object.c), which
// gc_debug_stage() reports. Shared by the collector and the stepped tests,
// which drive the machine one stage at a time and name the stage they wait
// for.
#ifndef GC_STAGE_H
#define GC_STAGE_H

enum gc_stage {
    GC_STAGE_NOT_STARTED,
    GC_STAGE_IDLE,       // Nothing happening, waiting for GC to start
    GC_STAGE_START,      // First setup: opens the cycle, raises the barrier flag
    GC_STAGE_STARTING,   // Waits for every thread to acknowledge the open cycle
    GC_STAGE_SCAN_ROOTS, // Each thread's stack, then the declared roots
    GC_STAGE_MARK_SWEEP, // Walk the graph, mark things as seen and scan as we go
    GC_STAGE_PRUNE
};
// For reports. A switch, so a stage added without a name is a -Wswitch warning.
static inline const char *gc_stage_name(enum gc_stage s) {
    switch (s) {
    case GC_STAGE_NOT_STARTED: return "not-started";
    case GC_STAGE_IDLE:        return "idle";
    case GC_STAGE_START:       return "start";
    case GC_STAGE_STARTING:    return "starting";
    case GC_STAGE_SCAN_ROOTS:  return "scan-roots";
    case GC_STAGE_MARK_SWEEP:  return "mark-sweep";
    case GC_STAGE_PRUNE:       return "prune";
    }
    return "?";
}

#endif
