# PR #45 review: improvements to make

From the maintainability review of the aarch64-gc branch. Ticked when committed.

## Maintainability

- [x] 1. Store macros that do the store: `GC_STORE_IN(obj, field, value, mask)` and
      `GC_FILL_STORE(obj, field, value, mask)`. Fence, barrier and their order live in one place;
      both compilers emit one line; runtime call sites use the same macros.
- [x] 2. The barrier family in one place, opening with one table: which helper, when, before or
      after the store, what it guarantees. Done as one section of `yafl.h` ("Pointer stores")
      rather than a new header: `yafl.h` ships alone in the System package, and both compilers
      name it, so a second header would need packaging changes for no gain in clarity.
- [x] 3. Merge `GC_ROOT_PUBLISH_IN` into `GC_PUBLISH_IN` (it ignores `obj` now).
- [x] 4. One helper for "does this store need the publication fence" (`gc_local_barrier_in`,
      `GC_FILL_FENCE`, `list_builder_link`).
- [ ] 5. Comments state the invariant; investigation history moves to INVESTIGATION.md.
- [ ] 6. Fold or delete the diagnostic patches (`diag-hooks.patch`, `n2-diag.patch`).

## Tests

- [x] 7. Codegen shape test: every pointer store goes through a store macro.
- [ ] 8. `gc_stress` in CTest (one short run).
- [ ] 9. The soak runs on PRs that touch `yafllib/**`, `compiler/codegen/**`, `bootstrap/ir/**`.
- [ ] 10. Step tests: the lazy double run; `page_needs_scan` after PRUNE; a late write to an
      `old` page before its writer's root scan.

## Tidy-ups

- [ ] 11. `gc_soak.py`: split `main()`, real names; the script writes the CI summary itself.
- [ ] 12. Small duplicates: reference-cache path in `build_bootstrap.py`, the prototype in
      `mmap.c`, stage names in `gc_debug.c`, the dead-slots loop in `object.c`.
- [ ] 13. `parser.py`: merge the three `__to_*` wrappers; a shared constant for `"$pipe@"`.
