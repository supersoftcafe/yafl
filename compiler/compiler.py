from __future__ import annotations

import sys

# Parser combinators and AST walks recurse with expression depth; a few
# hundred lines of nested expressions clears Python's default 1000 frames
# (found by examples/ylisp.yafl before it ever parsed).
sys.setrecursionlimit(20000)

import lowering.ast_inline
import lowering.block_exits
import lowering.conversions
import lowering.constants
import lowering.integers
import lowering.strings
import lowering.globalfuncs
import lowering.complex_enums
import lowering.lambda_globals
import lowering.lambda_lift
import lowering.lambdas
import lowering.lazy_thunks
import lowering.lower_lazy_lets
import lowering.generics
import lowering.inlining
import lowering.known_tags
import lowering.simple_classes
import lowering.ssa_defs  # analysis library shared by the known-value stages
import lowering.stack_promotion
import lowering.staticinit
import lowering.string_accumulation
import lowering.string_concat
import lowering.struct_folding
import lowering.deadstores
import lowering.discriminator_folding
import lowering.drops
import lowering.unions
import lowering.async_lower
import lowering.branch_threading
import lowering.copy_propagation
import lowering.ssa_validate
import lowering.linearity
import lowering.phi_removal
import lowering.sync_inference
import lowering.sroa
import lowering.tail_loop
import lowering.trim
import lowering.uninit_check
import lowering.vtable_trim

import pyast.statement as s
import pyast.expression as e
import libraries

from codegen.typedecl import DataPointer, FuncPointer, Struct, Int, Void
from codegen.ir import Function
import codegen.param as cg_p
import codegen.ops as cg_o
import codegen.typedecl as cg_t

from codegen.gen import Application
import pyast.resolver as g
import pyast.typespec as t
import pyast.rewrite as rw
from dataclasses import dataclass, fields

from parsing.tokenizer import tokenize, LineRef
from parsing.parselib import Error
from parsing.parser import parse
from pathlib import Path




@dataclass
class Input:
    content: str
    filename: str


def _read_source(path: Path) -> Input:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    return Input(''.join(lines), path.name)


def __create_entry_point(main: s.FunctionStatement) -> Function:
    sv_result    = cg_p.StackVar(DataPointer(), "result")
    sv_discard   = cg_p.StackVar(DataPointer(), "$sv_discard")
    continuation = cg_p.StackVar(FuncPointer(), "$continuation")

    is_task       = cg_p.RuntimeInvoke("PTR_IS_TASK", cg_p.NewStruct((("p", sv_result),)), Int(32))
    unlikely_chk  = cg_p.RuntimeInvoke("UNLIKELY",    cg_p.NewStruct((("x", is_task),)),    Int(32))

    untag       = cg_p.RuntimeInvoke("TASK_UNTAG",      cg_p.NewStruct((("p",    sv_result),)),                         DataPointer())
    on_complete = cg_p.RuntimeInvoke("task_on_complete", cg_p.NewStruct((("task", untag), ("cb", continuation))),        DataPointer())

    return Function(
        name="__entrypoint__",
        params=Struct(fields=(("this", DataPointer()), ("$continuation", FuncPointer()))),
        result=Void(),
        stack_vars=Struct(fields=(("result", DataPointer()), ("$sv_discard", DataPointer()))),
        ops=(
            cg_o.Call(
                function=cg_p.GlobalFunction(main.name),
                parameters=cg_p.NewStruct(()),
                register=sv_result,
            ),
            cg_o.JumpIf("$async_entry", unlikely_chk),
            # Sync path: invoke the completion callback with main's result
            cg_o.Call(
                function=continuation,
                parameters=cg_p.NewStruct((("result", sv_result),)),
            ),
            cg_o.ReturnVoid(),
            # Async path: register the continuation as task callback
            cg_o.Label("$async_entry"),
            cg_o.Move(sv_discard, on_complete, keep=True),
            cg_o.ReturnVoid(),
        )
    )



def __ensure_lazy_machinery(a: Application) -> None:
    """Find every Lazy$<irmangle> class referenced in `a` — either by a
    NewObject op (local `[lazy]`) or by a Global's `object_name`
    (`[lazy]` global, statically initialised stub instance) — and
    register the stub class + waiter subtype + fetch + finisher + drain
    for the matching IR type."""
    referenced: set[str] = set()
    for fn in a.functions.values():
        for op in fn.ops:
            if isinstance(op, cg_o.NewObject) and op.name.startswith("Lazy$"):
                referenced.add(op.name)
    for gv in a.globals.values():
        if gv.object_name and gv.object_name.startswith("Lazy$"):
            referenced.add(gv.object_name)
    for cls_name in referenced:
        suffix = cls_name[len("Lazy$"):]
        ir_type = lowering.lazy_thunks.ir_mangle_to_type(suffix)
        lowering.lazy_thunks.ensure_lazy_machinery(a, ir_type)


def __create_c_code(statements: list[s.Statement], main: s.FunctionStatement, just_testing = False, optimization_level: int = 0, union_discriminators: dict[str, int] | None = None, headers: tuple[str, ...] = ("yafl.h",)) -> str:
    a = Application(headers=headers)
    resolver = g.ResolverDiscriminators(g.ResolverRoot(statements), union_discriminators or {}, optimization_level=optimization_level)
    for stmt in statements:
        match stmt:
            case s.FunctionStatement() as f:
                resolver2 = g.AddScopeResolution(resolver, f.imports)
                a.functions[f.name] = f.global_codegen(resolver2)
            case s.LetStatement() as l:
                resolver2 = g.AddScopeResolution(resolver, l.imports)
                global_vars, init_funcs = l.global_codegen(resolver2)
                # if not global_var.init:
                #     raise ValueError("Only literal global variables are supported so far. Dynamic initialisation is tbd.")
                for gv in global_vars:
                    a.globals[gv.name] = gv
                for fn in init_funcs:
                    a.functions[fn.name] = fn
            case s.ClassStatement() as c:
                resolver2 = g.AddScopeResolution(resolver, c.imports)
                xclass, functions = c.global_codegen(resolver2)
                a.objects[c.name] = xclass
                for function in functions:
                    a.functions[function.name] = function
            case s.TypeAliasStatement() as t:
                pass
            case s.EnumStatement() as en:
                resolver2 = g.AddScopeResolution(resolver, en.imports)
                for obj in en.global_codegen(resolver2):
                    a.objects[obj.name] = obj
            case _:
                raise ValueError(f"Unexpected type {type(stmt)}")

    a.functions["__entrypoint__"] = __create_entry_point(main)
    a.union_discriminators = union_discriminators or {}

    # Register per-IR-type lazy thunk machinery for every Lazy$<irmangle>
    # class referenced by a NewObject op.  Idempotent and order-independent.
    __ensure_lazy_machinery(a)

    # SSA + control-flow + Phi validation right after AST lowering, before
    # any IR-level transformations. Catches generator bugs at the source.
    lowering.ssa_validate.validate(a)

    a = lowering.trim.removed_unused_stuff(a)
    a = lowering.globalfuncs.discover_global_function_calls(a)

    # Inlining (skipped at -O0/-O1): -O2 inlines small functions only; -O3 also
    # inlines `[inline(always)]` functions regardless of size, recursively (to a
    # fixpoint) so a chain of marked stages fuses fully into its consumer.
    if optimization_level > 0:
        if optimization_level >= 2:
            inline_always = optimization_level >= 3
            prev_shape: tuple | None = None
            for _ in range(16):  # bounded; converges as inlined-away functions are trimmed
                a = lowering.trim.removed_unused_stuff(
                    lowering.inlining.inline_small_functions(a, inline_always))
                shape = tuple((n, len(f.ops)) for n, f in a.functions.items())
                if shape == prev_shape:
                    break
                prev_shape = shape

        # Single-caller fold (-O3): inline any function referenced exactly once
        # into its sole call site regardless of size — no code growth — then
        # trim the now-unreferenced original. Runs after the small/always passes
        # so it mops up the residual one-shot helpers a fused pipeline leaves.
        # Each round first drops vtable entries no virtual call dispatches and
        # re-devirtualises: a devirtualised slot's dead entry is what pins a
        # trait witness's method above refcount 1, and folding that method can
        # in turn kill an object whose removal makes another slot single-
        # implementation — the cascade that fuses a stream pipeline into its
        # drain with no [inline(always)] annotations.
        if optimization_level >= 3:
            prev_shape = None
            for _ in range(16):  # bounded; recount each round as chains collapse
                a = lowering.vtable_trim.trim_unused_vtable_slots(a)
                a = lowering.globalfuncs.discover_global_function_calls(a)
                a = lowering.trim.removed_unused_stuff(
                    lowering.inlining.inline_single_caller_functions(a))
                shape = (tuple((n, len(f.ops)) for n, f in a.functions.items()),
                         tuple(sorted((n, len(o.functions)) for n, o in a.objects.items())))
                if shape == prev_shape:
                    break
                prev_shape = shape

        # Dead store elimination: remove StackVar assignments whose value is never read.
        # After inlining, trait-object `this` variables often become dead; removing them
        # lets trim cascade and eliminate entire vtables and trait implementations.
        a = lowering.trim.removed_unused_stuff(lowering.deadstores.eliminate_dead_stores(a))

        # Static init optimisation: promote NewObject with all-literal fields to static globals,
        # then inline single-use static globals into their lazy-init targets.
        for _ in range(4):
            a = lowering.staticinit.convert_static_objects_pass(a)

        # Dead store elimination again: static-init may expose additional dead stores.
        a = lowering.trim.removed_unused_stuff(lowering.deadstores.eliminate_dead_stores(a))

    # Resolve GlobalVar refs in flat-struct global inits to Integer/String constants so that
    # lowered simple-class globals (e.g. Config(13)) become valid C static initialisers.
    a = lowering.staticinit.resolve_flat_struct_global_inits(a)

    # Global lazy initialisation now flows through the per-IR-type
    # lazy-thunk framework: `lower_lazy_lets` auto-promotes every
    # non-literal global to `[lazy]`, `LetStatement.__global_codegen_lazy`
    # emits the static `Lazy$<T>` stub, and `LazyExpression` rewrites
    # references to go through `lazy_fetch$<T>`.  No more per-function-
    # entry guard — the previous `globalinit` pass and `lazy_global_init`
    # runtime helper are gone.

    a = lowering.sync_inference.infer_sync(a)

    # Branch threading + copy propagation collapse the IR shapes that ternary
    # and match lowerings leave behind (Move-into-shared-slot → Jump → Label
    # → Return). After collapse, each branch ends in `Call(R); Return(R)`,
    # which `__discover_tail_calls` (inside async lowering) recognises as
    # musttail. Returns these passes introduce mid-function are handled
    # uniformly by async lowering's Return-conversion helpers.
    #
    # At -O1+ this grows into a FIXPOINT with the known-value folds: after
    # fusion, a stage boundary is a NewStruct with a constant $tag inspected a
    # few ops later — struct_folding bypasses the pack, known_tags hardens the
    # dispatch (case-of-known-constructor), string_concat flattens append
    # chains into one exact-size allocation, the dead packs fall to
    # deadstores, the straightened flow lets branch threading collapse more —
    # each stage unlocks the next. Running BEFORE async lowering is the point:
    # the state machine snapshots liveness, so every value deleted here is a
    # slot never saved across a suspension.
    if optimization_level >= 1:
        prev_shape = None
        for _ in range(16):
            a = lowering.branch_threading.thread_branches(a)
            a = lowering.copy_propagation.propagate_copies(a)
            a = lowering.struct_folding.fold_struct_reads(a)
            a = lowering.discriminator_folding.resolve_known_discriminators(a)
            a = lowering.known_tags.resolve_known_tags(a)
            a = lowering.string_concat.flatten_string_appends(a)
            a = lowering.string_accumulation.deforest_string_accumulation(a)
            a = lowering.deadstores.eliminate_dead_stores(a)
            shape = tuple((n, len(f.ops)) for n, f in a.functions.items())
            if shape == prev_shape:
                break
            prev_shape = shape
    else:
        a = lowering.copy_propagation.propagate_copies(lowering.branch_threading.thread_branches(a))

    # Scalar-replace projection-only aggregate locals before async lowering, so a
    # tuple held across a suspension only because one field is needed afterwards
    # no longer roots its other (dead) fields. Runs at every -O level — this is a
    # space-correctness fix (see lowering/sroa.py), not an optimisation.
    a = lowering.sroa.split_projected_aggregates(a)

    # Leave SSA here: Phis → edge moves + copy-web coalescing shrinks the
    # local count (each survivor is a state field, boundary traffic and C
    # register pressure). Everything before this line relies on SSA;
    # async lowering and emission do not.
    a = lowering.phi_removal.remove_phis(a)
    # Non-escaping heap objects dissolve into per-field locals — the
    # allocation, its tracing and its initialising write barriers all
    # disappear. Lives on the non-SSA side (conditional construction paths
    # multi-write the field locals).
    if optimization_level >= 1:
        a = lowering.stack_promotion.promote_to_stack(a)
    a = lowering.trim.removed_unused_stuff(lowering.async_lower.lower_async(a))
    lowering.uninit_check.check_application(a)

    # Final SSA validation, just before C emission. The IR is still SSA at
    # this point: async lowering only writes to heap fields (ObjectField),
    # which don't count towards the single-definition invariant — that only
    # constrains StackVar writes. Phi → per-edge Moves and the remaining
    # imperative-style codegen transformations run inside `a.gen()`.
    lowering.ssa_validate.validate(a, ssa=False)

    return a.gen(just_testing=just_testing)


def __stmt_scope_resolver(stmt: s.Statement, glb: g.Resolver) -> g.Resolver:
    if isinstance(stmt, s.NamedStatement):
        import_scopes = set(x.path for x in stmt.imports.imports) if stmt.imports else set()
        own_ns = stmt.name.rpartition('::')[0]  # e.g. "Main" from "Main::main@JnNy0L"
        if own_ns:
            import_scopes.add(own_ns)
        scoped = g.AddScopeResolution(glb, import_scopes)
        # A global let's initialiser resolves like a function body: it needs the
        # trait/interface methods (operators) in scope. FunctionStatement adds
        # this itself; a top-level LetStatement has no such hook, so add it here.
        # Local lets compile via BlockExpression (not this path), so they keep
        # the enclosing function's trait scope unpolluted.
        if isinstance(stmt, s.LetStatement):
            return stmt._initialiser_resolver(scoped)
        return scoped
    return glb


def __compile(stmt: s.Statement, glb: g.Resolver, expected_type: t.TypeSpec | None) -> list[s.Statement]:
    glb = __stmt_scope_resolver(stmt, glb)
    result, extras = stmt.compile(glb, expected_type)
    return [result] + extras


def __is_main_function(stmt: s.FunctionStatement) -> bool:
    if ("::main@" not in stmt.name or
        not isinstance(stmt.return_type, t.BuiltinSpec) or
        not stmt.return_type.type_name == "bigint"):
        return False
    params_type = stmt.parameters.get_type()
    if not isinstance(params_type, t.TupleSpec):
        return False
    return len(params_type.entries) == 0


_MAX_COMPILE_ITERATIONS = 100


def __meet_hint(a, b):
    """Accumulate one parameter's call-site hints. `_CONFLICT` is sticky — once two
    call sites disagree on a parameter, no later agreeing site revives a suggestion
    for it (a disagreement means "do not use them", per the inference model)."""
    if a is t._CONFLICT or b is t._CONFLICT:
        return t._CONFLICT
    return t.meet(a, b)


def __collect_param_suggestions(statements: list[s.Statement]) -> dict[str, t.TupleSpec]:
    """Path 3 of the inference model: gather, for each function, the parameter
    shape implied by its CALL SITES, so an un-annotated parameter can be typed from
    how the function is used. A pure function of the AST, recomputed each pass —
    the resolver carries it down read-only, nothing is mutated mid-compile.

    Each resolved call `f(args)` contributes its argument tuple as a hint for `f`'s
    parameters; hints from multiple sites meet per position (a hole contributes
    nothing, a disagreement cancels that position). `search_and_replace` threads
    function/block scope, so an argument that references a local types correctly."""
    resolver = g.ResolverRoot(statements)
    hints: dict[str, list] = {}
    def visit(res: g.Resolver, thing):
        if isinstance(thing, e.CallExpression):
            name = getattr(thing.function, "name", None)
            ptype = thing.parameter.get_type(res)
            if name and "@" in name and isinstance(ptype, t.TupleSpec):
                arg_types = [en.type for en in ptype.entries]
                existing = hints.get(name)
                if existing is None:
                    hints[name] = arg_types
                elif len(existing) == len(arg_types):
                    hints[name] = [__meet_hint(x, y) for x, y in zip(existing, arg_types)]
        return rw.UNCHANGED
    for stmt in statements:
        stmt.search_and_replace(resolver, visit)
    lr = LineRef("suggestion", 0, 0)
    return {name: t.TupleSpec(lr, [t.TupleEntrySpec(None, None if h is t._CONFLICT else h)
                                   for h in entry_hints])
            for name, entry_hints in hints.items()}


def __collect_param_suggestion_detail(statements: list[s.Statement]) -> dict[str, list[set[str]]]:
    """Per function, per parameter, the DISTINCT types its call sites supply (as
    readable type ids). Used only to put a clue in the error when a parameter never
    gets a type — `[]` means no call site pins it, more than one entry means the
    call sites disagree (so no suggestion was usable)."""
    resolver = g.ResolverRoot(statements)
    detail: dict[str, list[set[str]]] = {}
    def visit(res: g.Resolver, thing):
        if isinstance(thing, e.CallExpression):
            name = getattr(thing.function, "name", None)
            ptype = thing.parameter.get_type(res)
            if name and "@" in name and isinstance(ptype, t.TupleSpec):
                slots = detail.setdefault(name, [set() for _ in ptype.entries])
                if len(slots) == len(ptype.entries):
                    for slot, en in zip(slots, ptype.entries):
                        uid = en.type.as_unique_id_str() if en.type is not None else None
                        if uid is not None:
                            slot.add(g.simple_name(uid))
        return rw.UNCHANGED
    for stmt in statements:
        stmt.search_and_replace(resolver, visit)
    return detail


def __check_untyped_params(statements: list[s.Statement]) -> list[Error]:
    """After the compile loop converges, a non-generic parameter that still has no
    type cannot be inferred from anywhere. Report it with the call-site suggestions
    as a clue (path 3), since that is exactly the evidence the inference used."""
    errors: list[Error] = []
    detail: dict[str, list[set[str]]] | None = None
    for stmt in statements:
        if not isinstance(stmt, s.FunctionStatement):
            continue
        for idx, tgt in enumerate(stmt.parameters.targets):
            if tgt.get_type() is not None:
                continue
            if detail is None:
                detail = __collect_param_suggestion_detail(statements)
            slots = detail.get(stmt.name, [])
            seen = slots[idx] if idx < len(slots) else set()
            if len(seen) > 1:
                clue = "call sites disagree (" + ", ".join(sorted(seen)) + ")"
            elif seen:
                clue = "call sites only partly determine it (" + next(iter(seen)) + ")"
            else:
                clue = "no call site supplies a type to infer it from"
            errors.append(Error(tgt.line_ref,
                f"Parameter '{g.simple_name(tgt.name)}' of '{g.simple_name(stmt.name)}' "
                f"has no type and could not be inferred — {clue}"))
    return errors


def __converge(statements: list[s.Statement]) -> tuple[list[s.Statement], g.Resolver]:
    """Run the compile fixpoint: rewrite every statement until a whole pass
    changes nothing. Returns the converged statements and the final resolver."""
    for _ in range(1, _MAX_COMPILE_ITERATIONS + 1):
        resolver = g.ResolverRoot(statements, __collect_param_suggestions(statements))
        new_statements = [x for stmt in statements for x in __compile(stmt, resolver, None)]
        if new_statements == statements:
            return new_statements, resolver
        statements = new_statements
    raise RuntimeError(
        f"Compile loop failed to converge after {_MAX_COMPILE_ITERATIONS} iterations. "
        "This is a compiler bug — a compile() pass is not idempotent."
    )


def __iterate_and_compile(statements: list[s.Statement], just_testing = False, optimization_level: int = 0, headers: tuple[str, ...] = ("yafl.h",)) -> tuple[str, list[Error]] | list[Error]:
    """Returns (c_code, warnings) on success, or the diagnostic list on failure
    (which may include warnings alongside the errors — all get printed)."""
    new_statements, resolver = __converge(statements)

    # A global `let` holding a lambda is a function by another name — rewrite
    # it to one now that inference is done (every lambda is fully typed), so
    # it compiles as an ordinary function rather than a lazy fun_t global.
    new_statements = lowering.lambda_globals.lower_lambda_globals(new_statements)

    # Affine drops: a never-referenced `[linear]` binding whose type has a Drop
    # instance is consumed by an inserted scope-exit `drop(x)` (see
    # lowering/drops.py). Needs converged types to decide, and a re-convergence
    # afterwards so the inserted calls resolve like ordinary code.
    new_statements, dropped = lowering.drops.insert_drops(new_statements)
    if dropped:
        new_statements, resolver = __converge(new_statements)

    mains = [stmt for stmt in new_statements if isinstance(stmt, s.FunctionStatement) and __is_main_function(stmt)]

    # A non-generic parameter left untyped after convergence is uninferable —
    # surface it (with call-site clues) before the check phase, where it would
    # otherwise show up as a confusing downstream "Failed to resolve" instead.
    untyped_errors = __check_untyped_params(new_statements)
    if untyped_errors:
        return untyped_errors

    diagnostics = [x for stmt in new_statements for x in stmt.check(__stmt_scope_resolver(stmt, resolver), None)]
    if not mains:
        diagnostics += [Error(LineRef("none", 0, 0), "No main function found")]
    elif len(mains) > 1:
        diagnostics += [Error(LineRef("none", 0, 0), "Too many main functions defined")]

    # Warnings never fail the build: split them out and carry them to the
    # caller. On failure return everything — errors and warnings print together.
    warnings = [x for x in diagnostics if x.severity == "warning"]
    new_errors = [x for x in diagnostics if x.severity != "warning"]
    if new_errors:
        # Nothing more to do, just errors
        return diagnostics

    # Catch any NamedSpec that the compile loop failed to resolve
    named_spec_errors: list[Error] = []
    def _find_named_specs(_, thing):
        if isinstance(thing, t.NamedSpec):
            named_spec_errors.append(Error(thing.line_ref, f"Failed to resolve type '{thing.name}'"))
        return thing
    for stmt in new_statements:
        stmt.search_and_replace(resolver, _find_named_specs)
    if named_spec_errors:
        return named_spec_errors

    # Linear-type check: runs on the converged, type-resolved templates
    # (pre-monomorphisation). Each `<[linear] T>` generic body is checked
    # once here; the instantiation-site kind check lives in generics.py.
    linearity_errors = lowering.linearity.check_linearity(new_statements, resolver)
    if linearity_errors:
        return linearity_errors

    # All ok so let's create some C code
    new_statements = lowering.generics.convert_generic_to_concrete(new_statements)
    new_statements = lowering.complex_enums.mark_complex_enums(new_statements)
    new_statements = lowering.constants.inline_constants(new_statements)
    # Make every implicit representation change an explicit ConvertExpression —
    # generate never coerces (docs/compiler-internals.md §2). Must run after
    # monomorphisation (conversions inside generic templates are undecidable
    # before it) and before tail-loop lowering (a recursive call's boxed
    # arguments carry over to the loop back-edge).
    new_statements = lowering.conversions.insert_conversions(new_statements)
    # `[tail]` self-recursion → loop. Runs before inlining / closure conversion,
    # while every self-call is still a direct, name-resolved call so the
    # recursion is detectable. Nested `[tail]` functions are lowered too; a
    # capturing one is closure-converted afterwards and the LoopExpression rides
    # along (its labels are function-local; it tracks renames). Union widening is
    # no longer an AST pass, so there is no ordering dependency on it — a [tail]
    # body's non-recursive exits are coerced to the return type when the
    # LoopExpression generates its body, and the recursive call (now a
    # RecurExpression) coerces its args to the parameter types at the back-edge.
    # Nested helpers that capture only to be called shed the closure: captures
    # become parameters (must precede tail_loop — self-calls are still calls).
    new_statements = lowering.lambda_lift.lift_captured_calls(new_statements)
    new_statements, tail_errors = lowering.tail_loop.lower_tail_loops(new_statements, resolver)
    if tail_errors:
        return tail_errors
    new_statements = lowering.ast_inline.inline_ast(new_statements, optimization_level)
    new_statements = lowering.strings.fix_global_strings(new_statements)
    new_statements = lowering.integers.fix_global_integers(new_statements)
    # Surface [lazy] forward-references-to-non-lazy as compile errors
    # before lowering — the lowering would otherwise produce code that
    # crashes at force time.  Block-local check.
    lazy_fwd_errors = lowering.lower_lazy_lets.check_lazy_forward_refs(new_statements)
    if lazy_fwd_errors:
        return lazy_fwd_errors
    # [lazy] let lowering: wrap RHS in a lambda and rewrite reference sites
    # to LazyExpression.  Must run before lambdas so the synthesised
    # closure goes through normal closure conversion.
    new_statements = lowering.lower_lazy_lets.lower_lazy_lets(new_statements)
    new_statements = lowering.lambdas.convert_lambdas_to_functions(new_statements)
    new_statements = lowering.simple_classes.lower_simple_classes(new_statements)
    # Stamp every block/return with its exit identifiers, last — after every
    # pass that can create or copy blocks — so each block instance is unique.
    new_statements = lowering.block_exits.assign_block_exits(new_statements)
    union_discriminators = lowering.unions.collect_discriminator_ids(new_statements)
    c_code = __create_c_code(new_statements, mains[0], just_testing=just_testing, optimization_level=optimization_level, union_discriminators=union_discriminators, headers=headers)
    return c_code, warnings


def __tokenize_and_parse(source: list[Input]) -> tuple[list[s.Statement], list[Error]]:
    errors = []
    statements = []

    # Tokenize and parse input files
    for input in source:
        tokens = tokenize(input.content, input.filename)
        result = parse(tokens)

        if result.errors:
            errors += result.errors
        if result.value:
            statements += result.value

    return statements, errors


def __print_errors(errors: list[Error]) -> str:
    for error in sorted(set(errors)):
        print(error)
    return ""


def _candidate_namespaces(statements: list[s.Statement]) -> set[str]:
    """Namespaces a set of parsed statements might reference, as an
    over-approximation used to decide which libraries to load.

    `import` is not mandatory, so we look at both the declared imports and every
    namespace-qualified (`::`) reference in the AST, take every prefix of each, and
    also compose each qualified reference under each import (a `A::B` reference may
    be top-level or relative to an import `P`, giving `P::A::B`). Misses are
    harmless — they simply match no library. See `docs/build-and-packaging.md`.
    """
    imports: set[str] = set()
    quals: set[str] = set()

    def collect(resolver, thing):
        name = getattr(thing, "name", None)
        if isinstance(name, str) and "::" in name and isinstance(thing, (e.NamedExpression, t.NamedSpec)):
            quals.add(name)
        return rw.UNCHANGED

    for st in statements:
        group = getattr(st, "imports", None)
        if group is not None:
            for imp in group.imports:
                imports.add(imp.path)
        st.search_and_replace(g.ResolverRoot([]), collect)

    def prefixes(qualified: str) -> set[str]:
        parts = [p.split("@")[0] for p in qualified.split("::")]
        return {"::".join(parts[:i]) for i in range(1, len(parts) + 1)}

    candidates: set[str] = set()
    for p in imports:
        candidates |= prefixes(p)
    for q in quals:
        candidates |= prefixes(q)
    for p in imports:
        for q in quals:
            candidates |= prefixes(f"{p}::{q}")
    return candidates


def _gather_libraries(use_stdlib: bool, lib_paths: list[str] | None):
    """All libraries reachable on the search path (plus the build-tree dev System
    fallback when `use_stdlib` and no installed System is present)."""
    if use_stdlib:
        return libraries.available_libraries(lib_paths)
    return libraries.discover_libraries(libraries.search_paths(lib_paths))


def compile_project(source: list[Input], use_stdlib = False, just_testing = False,
                    optimization_level: int = 0,
                    lib_paths: list[str] | None = None) -> tuple[str, libraries.LinkSpec | None, list[Error]]:
    """Compile `source` together with every library it (transitively) references,
    discovered on the search path. Returns the generated C, the `LinkSpec`
    describing the headers/static libraries the loaded libraries need at link
    time, and any warnings (non-fatal diagnostics — the caller decides how to
    surface them). On error returns ("", None, []) after printing diagnostics."""
    user_statements, errors = __tokenize_and_parse(source)
    if errors:
        return __print_errors(errors), None, []

    index = libraries.namespace_index(_gather_libraries(use_stdlib, lib_paths))

    # Permissive worklist: load every referenced library to a fixpoint, following
    # the references of each newly-loaded library. Libraries are loaded as source
    # and join the whole-program set; `trim` later drops anything unused.
    lib_statements: list[s.Statement] = []
    loaded_ids: set[int] = set()
    frontier = list(user_statements)
    while frontier:
        next_frontier: list[s.Statement] = []
        for ns in sorted(_candidate_namespaces(frontier)):
            lib = index.get(ns)
            if lib is None or id(lib) in loaded_ids:
                continue
            loaded_ids.add(id(lib))
            stmts, lib_errors = __tokenize_and_parse(
                [Input(src.content, src.filename) for src in lib.yafl_sources()])
            if lib_errors:
                return __print_errors(lib_errors), None, []
            lib_statements += stmts
            next_frontier += stmts
        frontier = next_frontier

    statements = lib_statements + list(user_statements)
    seen: set[int] = set()
    loaded_libs = [lib for lib in index.values()
                   if id(lib) in loaded_ids and not (id(lib) in seen or seen.add(id(lib)))]
    link_spec = libraries.link_spec_for(loaded_libs)

    # yafl.h is the runtime ABI baseline (the entrypoint references it), so it is
    # always included; loaded libraries append their own headers.
    headers = ("yafl.h",) + tuple(h for h in link_spec.headers if h != "yafl.h")

    compiled_result = __iterate_and_compile(statements, just_testing=just_testing,
        optimization_level=optimization_level, headers=headers)
    if isinstance(compiled_result, list):
        return __print_errors(compiled_result), None, []

    c_code, warnings = compiled_result
    return c_code, link_spec, warnings


def compile(source: list[Input], use_stdlib = False, just_testing = False, optimization_level: int = 0, lib_paths: list[str] | None = None) -> str:
    c_code, _, warnings = compile_project(source, use_stdlib=use_stdlib, just_testing=just_testing,
        optimization_level=optimization_level, lib_paths=lib_paths)
    for w in sorted(set(warnings)):
        print(w, file=sys.stderr)
    return c_code



