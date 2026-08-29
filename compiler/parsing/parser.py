from __future__ import annotations

import dataclasses
from functools import reduce

from typing import Generic, TypeVar

import pyast.expression as e
import pyast.match as m
import pyast.statement as s
import pyast.typespec as t
import parsing.parselib as p
import pyast.utils


def __integer() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.IntegerExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.NUMBER:
                # Assume that head.value is an integer, check for format errors
                # We can assume this, because 'parse_float' comes first, and so only integers remain
                value = head.value
                starts = lambda x: value.startswith(x)
                ends = lambda x: value.endswith(x)
                radix, triml = (2, 2) if starts("0b") else (8, 2) if starts("0o") else (16, 2) if starts("0x") else (10, 0)
                size, trimr = (8, 2) if ends("i8") else (16, 3) if ends("i16") else (32, 3) if ends("i32") else (64, 3) if ends("i64") else (0, 0)
                value = value[ triml : len(value) if not trimr else len(value)-trimr ].replace("_", "")
                try:
                    return p.Result.ok(e.IntegerExpression(head.line_ref, int(value, radix), size), tail, head.line_ref)
                except ValueError as err:
                    return p.Result.error(str(err), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __float() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.FloatExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.NUMBER:
                value = head.value
                # Hex/bin/oct prefixes are integer literals only (a hex literal
                # may legitimately contain 'e'/'E' as a digit).
                if value.startswith(("0x", "0X", "0b", "0B", "0o", "0O")):
                    return p.Result.none(tokens, tokens[0].line_ref)
                # A token is a float if it has a decimal point, an exponent,
                # or an explicit f32/f64 suffix.
                has_dot = "." in value
                has_exp = "e" in value or "E" in value
                ends_f32 = value.endswith("f32")
                ends_f64 = value.endswith("f64")
                if not (has_dot or has_exp or ends_f32 or ends_f64):
                    return p.Result.none(tokens, tokens[0].line_ref)
                # Strip the precision suffix. An unsuffixed literal carries the
                # `0` "unspecified" sentinel (defaults to float64, but may be
                # narrowed to its context by FloatExpression.compile); an
                # explicit suffix is authoritative.
                if ends_f32:
                    precision, num_str = 32, value[:-3]
                elif ends_f64:
                    precision, num_str = 64, value[:-3]
                else:
                    precision, num_str = 0, value
                try:
                    return p.Result.ok(
                        e.FloatExpression(head.line_ref, float(num_str.replace("_", "")), precision),
                        tail, head.line_ref)
                except ValueError as err:
                    return p.Result.error(str(err), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)

_STRING_ESCAPES = {
    'n': '\n', 'r': '\r', 't': '\t', '0': '\0',
    '\\': '\\', '"': '"', "'": "'",
}

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

def _codepoint_char(hexpart: str) -> tuple[str, str | None]:
    """Turn a hex codepoint into its single character, rejecting out-of-range
    and surrogate values so the decoded string is always a valid Unicode scalar
    sequence (and therefore valid UTF-8 once encoded)."""
    cp = int(hexpart, 16)
    if cp > 0x10FFFF:
        return "", f"codepoint U+{cp:X} is out of range (max U+10FFFF)"
    if 0xD800 <= cp <= 0xDFFF:
        return "", f"codepoint U+{cp:X} is a UTF-16 surrogate, not a scalar value"
    return chr(cp), None

def _unescape_string(raw: str) -> tuple[str, str | None]:
    """Decode yafl string escapes. Returns (decoded, error) — error is None on
    success. Beyond the simple escapes in `_STRING_ESCAPES`, three forms denote a
    Unicode codepoint (encoded to UTF-8 downstream): `\\xNN` (exactly two hex
    digits, U+0000–U+00FF), `\\uXXXX` (exactly four hex digits), and `\\u{…}`
    (one to six hex digits, the full scalar range)."""
    out: list[str] = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c != '\\':
            out.append(c)
            i += 1
            continue
        if i + 1 >= len(raw):
            return "", "dangling backslash in string literal"
        nxt = raw[i+1]
        if nxt == 'x':
            hexpart = raw[i+2:i+4]
            if len(hexpart) != 2 or any(ch not in _HEX_DIGITS for ch in hexpart):
                return "", "\\x escape needs exactly two hex digits"
            out.append(chr(int(hexpart, 16)))
            i += 4
            continue
        if nxt == 'u':
            if i + 2 < len(raw) and raw[i+2] == '{':
                close = raw.find('}', i+3)
                if close == -1:
                    return "", "unterminated \\u{…} escape"
                hexpart = raw[i+3:close]
                if not (1 <= len(hexpart) <= 6) or any(ch not in _HEX_DIGITS for ch in hexpart):
                    return "", "\\u{…} escape needs one to six hex digits"
                ch, err = _codepoint_char(hexpart)
                if err is not None:
                    return "", err
                out.append(ch)
                i = close + 1
                continue
            hexpart = raw[i+2:i+6]
            if len(hexpart) != 4 or any(ch not in _HEX_DIGITS for ch in hexpart):
                return "", "\\u escape needs exactly four hex digits (or use \\u{…})"
            ch, err = _codepoint_char(hexpart)
            if err is not None:
                return "", err
            out.append(ch)
            i += 6
            continue
        if nxt not in _STRING_ESCAPES:
            return "", f"unknown string escape: \\{nxt}"
        out.append(_STRING_ESCAPES[nxt])
        i += 2
    return "".join(out), None


def __string() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.StringExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.STRING:
                value = head.value
                if not value.endswith('"'):
                    return p.Result.error("string missing quote", tail, head.line_ref)
                decoded, err = _unescape_string(value[1:len(value)-1])
                if err is not None:
                    return p.Result.error(err, tail, head.line_ref)
                return p.Result.ok(e.StringExpression(head.line_ref, decoded), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __char() -> p.Parser[e.Expression]:
    """A single-quote char literal. Decoded exactly like a string (same
    escapes), then required to be exactly one codepoint; its value is that
    codepoint as an Int32 — there is no `char` type, and every Unicode scalar
    fits in Int32. `'A'` is therefore identical to `65i32`."""
    def _p(tokens: list[p.Token]) -> p.Result[e.IntegerExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.CHAR:
                value = head.value
                if len(value) < 2 or not value.endswith("'"):
                    return p.Result.error("char literal missing closing quote", tail, head.line_ref)
                decoded, err = _unescape_string(value[1:len(value)-1])
                if err is not None:
                    return p.Result.error(err, tail, head.line_ref)
                if len(decoded) != 1:
                    return p.Result.error(
                        "char literal must contain exactly one character", tail, head.line_ref)
                # RULED (2026-07-04, superseding an earlier fluid-literals
                # direction): a char literal IS an Int32 literal — 'a' is
                # 97i32, exactly. No literal converts to anything: 37 is Int,
                # 37i32 is Int32, 12.5 is Float64. Type what you mean.
                return p.Result.ok(e.IntegerExpression(head.line_ref, ord(decoded), 32),
                                   tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __regex() -> p.Parser[e.Expression]:
    r"""`re"pattern"` — a RAW regex literal: the pattern between the quotes is
    handed to the engine byte-for-byte (no yafl escape decoding), so `\d`
    is written with one backslash. Validation and interning happen in
    lowering/regexes.py."""
    def _p(tokens: list[p.Token]) -> p.Result[e.RegexExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.REGEX:
                value = head.value
                if not value.endswith('"') or len(value) < 4:
                    return p.Result.error("regex literal missing closing quote", tail, head.line_ref)
                return p.Result.ok(e.RegexExpression(head.line_ref, value[3:-1]), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __named() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.NamedExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.IDENTIFIER:
                return p.Result.ok(e.NamedExpression(head.line_ref, head.value), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __to_flat_list[_T](value: list[list[_T]]) -> list[_T]:
    return [Y for X in value for Y in X]


def __to_dot_op(result: p.Result[e.Expression], tokens: list[p.Token]) -> p.Result:
    # `.name` -> a transformer wrapping its left operand in a DotExpression. The
    # dot target must be an identifier (this was the former __to_dot_path check).
    name = result.value
    if not isinstance(name, e.NamedExpression):
        return p.Result(None, result.tokens, result.line_ref,
                        result.errors + [e.Error(name.line_ref, "Must be an identifier")])
    return p.Result(lambda left: e.DotExpression(name.line_ref, left, name.name),
                    result.tokens, result.line_ref, result.errors)


def __to_named_fully_qualified(value: tuple[e.NamedExpression, list[e.NamedExpression], list[t.TypeSpec]]) -> e.Expression:
    first, path, type_params = value
    expr = e.NamedExpression(first.line_ref, "::".join(ne.name for ne in ([first] + path)), type_params=tuple(type_params))
    return expr


def __to_builtin_op(result, tokens: list[p.Token]) -> p.Result[e.Expression]:
    type_spec, params_tuple = result.value
    op, *_ = params_tuple.expressions
    if not isinstance(op.value, e.StringExpression):
        return p.Result.error("__builtin_op__ first parameter must be a string", tokens, result.line_ref)
    # A bare builtin name (`<bool>`, `<int64>`) stays a BuiltinSpec — those
    # identifiers are not YAFL-level names and must not resolve as such. Any
    # other spelling is an ordinary type: an op like array_builder_alloc
    # declares a full `Array<T>` result.
    _BUILTINS = {"bigint", "str", "bool", "int8", "int16", "int32", "int64",
                 "float32", "float64"}
    if isinstance(type_spec, t.NamedSpec) and not type_spec.type_params \
            and type_spec.name in _BUILTINS:
        type_spec = t.BuiltinSpec(result.line_ref, type_spec.name)
    expr = e.BuiltinOpExpression(result.line_ref, type_spec, op.value, params_tuple.trim_left(1))
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_call_op(value: e.Expression, line_ref: p.LineRef):
    # `(args)` -> a transformer applying its left operand as the callee.
    args = value
    line = line_ref
    return lambda left: e.CallExpression(line, left, args)


def __to_index_op(value: e.Expression, line_ref: p.LineRef) -> object:
    # `[i]` -> a transformer lowering to the `[]` operator: ``[]``(left, i),
    # exactly as `left + right` lowers to `+`(left, right). Nothing is
    # auto-generated for arrays here; resolution finds whatever ``[]`` is in
    # scope, like any other operator.
    idx = value
    line = line_ref
    def wrap(left: e.Expression) -> e.Expression:
        return e.CallExpression(line,
            e.NamedExpression(line, "`[]`"),
            e.TupleExpression(line, [
                e.TupleEntryExpression(None, left),
                e.TupleEntryExpression(None, idx)]))
    return wrap


def __to_invokes(value: tuple[e.Expression, list]) -> e.Expression:
    # A primary expression followed by a left-associative chain of postfix
    # operators — `.field`, `(...)`, `[...]` — that interleave freely, so
    # `f().g()`, `a().b`, `m()[0].x` all parse. Each op parsed to an Expr->Expr
    # closure (see __to_dot_op/__to_call_op/__to_index_op), so folding is just
    # left-to-right application — no per-op tag or discrimination needed.
    left_expr, ops = value
    expr = reduce(lambda acc, op: op(acc), ops, left_expr)
    return expr


def __placeholder_entries(function: e.Expression) -> list[int]:
    """Indices of top-level `_` placeholder arguments when `function` is a
    call — the `x |> f(a, _)` stage form. Only the stage call's own argument
    list is searched: a `_` nested deeper is not a placeholder."""
    if not (isinstance(function, e.CallExpression)
            and isinstance(function.parameter, e.TupleExpression)):
        return []
    return [i for i, entry in enumerate(function.parameter.expressions)
            if isinstance(entry.value, e.NamedExpression) and entry.value.name == "_"]


def __pipe_stage(last_result: e.Expression, function: e.Expression,
             pipeline_errors: list[p.Error]) -> e.Expression:
    # `l |> f(a, _)`: the `_` placeholder receives the piped value — a
    # point-free stage. Same capture-avoiding shape as the lambda case
    # below: bind `l` to a fresh path-derived name OUTSIDE the call, then
    # substitute that name for the placeholder.
    holes = __placeholder_entries(function)
    if len(holes) > 1:
        pipeline_errors.append(p.Error(function.line_ref,
            "at most one `_` placeholder per pipeline stage"))
        return last_result
    if len(holes) == 1:
        lr = function.line_ref
        tmp = f"$pipe@{lr.hash6()}"
        entries = list(function.parameter.expressions)
        entries[holes[0]] = dataclasses.replace(
            entries[holes[0]], value=e.NamedExpression(lr, tmp))
        call = dataclasses.replace(function,
            parameter=dataclasses.replace(function.parameter, expressions=entries))
        return e.BlockExpression(lr,
            [s.LetStatement(lr, tmp, None, {}, (), last_result, None)], call)
    # `l |> (a, b) => body` is a beta-redex: lower it to BLOCKS binding the
    # lambda's parameters from `l` and running the body inline — not a
    # call. No closure is created, a piped TUPLE value binds its entries
    # positionally through the ordinary destructure (the "let without
    # let"), and a linear value pipes through without tripping the
    # nested-function capture rule.
    #
    # Substitution is CAPTURE-AVOIDING: lambda parameters scope to the
    # lambda's body only, so they must not be visible to `l` (the argument
    # belongs to the enclosing scope — `x |> (x) => …` reads the OUTER x).
    # Hence two blocks: the outer binds `l` to a fresh path-derived
    # intermediate (unique by construction — nothing in `l` can resolve to
    # it), the inner binds the parameters from that intermediate.
    if isinstance(function, e.LambdaExpression):
        lr = function.line_ref
        tmp = f"$pipe@{lr.hash6()}"
        targets = function.parameters.targets
        binder: s.Statement = (
            dataclasses.replace(targets[0], default_value=e.NamedExpression(lr, tmp))
            if len(targets) == 1
            else dataclasses.replace(function.parameters, default_value=e.NamedExpression(lr, tmp)))
        inner = e.BlockExpression(lr, [binder], function.expression)
        return e.BlockExpression(lr,
            [s.LetStatement(lr, tmp, None, {}, (), last_result, None)], inner)
    # Wrap last result in a tuple, just-in-case it isn't a tuple already.
    parameter = last_result if isinstance(last_result, e.TupleExpression)\
        else e.TupleExpression(last_result.line_ref, [e.TupleEntryExpression(None, last_result)])
    call = e.CallExpression(function.line_ref, function, parameter)
    return call


def __invert_operand(expr: e.Expression) -> e.Expression | None:
    """If `expr` is a unary `~x`, return `x`, else None. Used to fold
    `a & ~b` into the single-pass `andNot(a, b)` at parse time."""
    if (isinstance(expr, e.CallExpression)
            and isinstance(expr.function, e.NamedExpression)
            and expr.function.name == "`~`"
            and isinstance(expr.parameter, e.TupleExpression)
            and len(expr.parameter.expressions) == 1):
        return expr.parameter.expressions[0].value
    return None


def __to_call_operators(result: p.Result[tuple[e.Expression, list[tuple[str, e.Expression]]]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    def accumulate(left: e.Expression, entry: tuple[str, e.Expression]):
        op, right = entry
        line = tokens[0].line_ref
        # `a & ~b` is andNot — recognise it here so it lowers to the runtime's
        # single-pass andnot rather than a separate complement then and. AND is
        # commutative, so `~a & b` is andNot(b, a) too; only fold when exactly
        # one side is `~` (both-inverted is NOR, handled by the right side).
        if op == "&":
            def _andnot(x: e.Expression, y: e.Expression) -> e.Expression:
                return e.CallExpression(line,
                    e.NamedExpression(line, "andNot"),
                    e.TupleExpression(line, [
                            e.TupleEntryExpression(None, x),
                            e.TupleEntryExpression(None, y)
                        ]))
            inner_right = __invert_operand(right)
            if inner_right is not None:
                return _andnot(left, inner_right)          # a & ~b -> andNot(a, b)
            inner_left = __invert_operand(left)
            if inner_left is not None:
                return _andnot(right, inner_left)          # ~a & b -> andNot(b, a)
        return e.CallExpression(line,
            e.NamedExpression(line, f"`{op}`"),
            e.TupleExpression(line, [
                    e.TupleEntryExpression(None, left),
                    e.TupleEntryExpression(None, right)
                ]))
    left_expr, right_list = result.value
    expr = reduce(accumulate, right_list, left_expr)
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_bind_or_pipeline(result: p.Result[tuple[e.Expression, list[tuple[str, e.Expression]]]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    """The shared `?>`/`|>` level: fold left, dispatching per operator —
    `?>` is an ordinary operator call, `|>` is the pipeline stage lowering
    (placeholder substitution / lambda beta-redex, __pipe_stage)."""
    pipeline_errors: list[p.Error] = []

    def accumulate(left: e.Expression, entry: tuple[str, e.Expression]) -> e.Expression:
        op, right = entry
        if op == "|>":
            return __pipe_stage(left, right, pipeline_errors)
        line = tokens[0].line_ref
        return e.CallExpression(line,
            e.NamedExpression(line, f"`{op}`"),
            e.TupleExpression(line, [
                    e.TupleEntryExpression(None, left),
                    e.TupleEntryExpression(None, right)]))

    left_expr, right_list = result.value
    expr = reduce(accumulate, right_list, left_expr)
    return p.Result(expr, result.tokens, result.line_ref, result.errors + pipeline_errors)


def __to_negate(result: p.Result[e.Expression], tokens: list[p.Token]) -> p.Result[e.Expression]:
    expr = result.value
    if isinstance(expr, (e.IntegerExpression, e.FloatExpression)):
        folded = dataclasses.replace(expr, value=-expr.value)
        return p.Result(folded, result.tokens, result.line_ref, result.errors)
    line = result.line_ref
    negated = e.CallExpression(line,
        e.NamedExpression(line, "`-`"),
        e.TupleExpression(line, [
            e.TupleEntryExpression(None, expr),
        ]))
    return p.Result(negated, result.tokens, result.line_ref, result.errors)


def __to_not(value: e.Expression, line_ref: p.LineRef) -> e.Expression:
    line = line_ref
    notted = e.CallExpression(line,
        e.NamedExpression(line, "`!`"),
        e.TupleExpression(line, [
            e.TupleEntryExpression(None, value),
        ]))
    return notted


def __to_invert(value: e.Expression, line_ref: p.LineRef) -> e.Expression:
    line = line_ref
    inverted = e.CallExpression(line,
        e.NamedExpression(line, "`~`"),
        e.TupleExpression(line, [
            e.TupleEntryExpression(None, value),
        ]))
    return inverted


def __to_ternery(value: tuple[e.Expression, list[tuple[e.Expression, e.Expression]]]) -> e.Expression:
    def get_right_expr(condition: e.Expression, expressions: list[tuple[e.Expression, e.Expression]]) -> e.Expression:
        if not expressions:
            return condition
        true_expr, false_expr = expressions[0]
        if len(expressions) == 1:
            return e.TernaryExpression(condition.line_ref, condition, true_expr, false_expr)
        else:
            false_expr = get_right_expr(false_expr, expressions[1:])
            return e.TernaryExpression(condition.line_ref, condition, true_expr, false_expr)
    left_expr, right_list = value
    expr = get_right_expr(left_expr, right_list)
    return expr


def __to_coalesce(value: tuple) -> e.Expression:
    # `a ?? b` is the elimination half of the option idiom: a's value when it
    # is not None, else b. Left-associative, so `a ?? b ?? c` tries a, then b,
    # then c. Short-circuit is structural — CoalesceExpression rewrites into a
    # match, and `b` sits in an arm, so it is only evaluated when taken. See
    # pyast/expression/coalesce.py for why this is a node rather than sugar.
    def accumulate(left: e.Expression, right: e.Expression) -> e.Expression:
        return e.CoalesceExpression(left.line_ref, left, right)
    left_expr, right_list = value
    return reduce(accumulate, right_list, left_expr)


def __to_logical_and(value: tuple[e.Expression, list[e.Expression]]) -> e.Expression:
    # `a && b` is short-circuit sugar for `a ? b : false` — guaranteed control
    # flow, not a function call, so the right operand is never evaluated when the
    # left is false. Left-associative; `&` stays the eager both-operands bool op.
    def accumulate(left: e.Expression, right: e.Expression) -> e.Expression:
        return e.TernaryExpression(left.line_ref, left, right, e.BoolExpression(left.line_ref, False))
    left_expr, right_list = value
    expr = reduce(accumulate, right_list, left_expr)
    return expr


def __to_logical_or(value: tuple[e.Expression, list[e.Expression]]) -> e.Expression:
    # `a || b` is short-circuit sugar for `a ? true : b`; mirrors __to_logical_and.
    def accumulate(left: e.Expression, right: e.Expression) -> e.Expression:
        return e.TernaryExpression(left.line_ref, left, e.BoolExpression(left.line_ref, True), right)
    left_expr, right_list = value
    expr = reduce(accumulate, right_list, left_expr)
    return expr


def __to_is(result: p.Result, tokens: list[p.Token]) -> p.Result[e.Expression]:
    # `L is R` / `L !is R` — a type test. R is a TYPE, so this is sugar for the
    # variant match `match(L) (_: R) => true; () => false` (negated for `!is`),
    # reusing the same subset dispatch a hand-written match would. The right
    # operand is a type, so this never chains: at most one `[!] is R` per L.
    left, clause = result.value
    if not clause:
        return p.Result(left, result.tokens, result.line_ref, result.errors)
    bang, _is_kw, rtype = clause[0]
    neg = len(bang) > 0
    lr = left.line_ref
    arms = [
        m.MatchArm(lr, None, rtype, e.BoolExpression(lr, not neg)),  # (_: R) => true / false
        m.MatchArm(lr, None, None, e.BoolExpression(lr, neg)),       # ()     => false / true
    ]
    return p.Result(m.MatchExpression(lr, left, arms), result.tokens, result.line_ref, result.errors)


def __to_expr_tuple_entry(value: tuple[list[str], e.Expression]) -> e.TupleEntryExpression:
    name, value = value
    return e.TupleEntryExpression(p.first_or_none(name), value)


def __to_spread_entry(value: e.Expression) -> e.TupleEntryExpression:
    # `*expr` — splice the tuple value's fields into this tuple, positionally.
    return e.TupleEntryExpression(None, value, spread=True)


def __to_expr_tuple(value: list[e.TupleEntryExpression], line_ref: p.LineRef) -> e.Expression:
    items = value
    return e.TupleExpression(line_ref, items)


def __to_paren_expr(value: e.Expression) -> e.Expression:
    """`( expr )` as a primary expression: a single un-named entry is just a
    parenthesised expression, so collapse the 1-tuple wrap. `()`, `(a, b)` and
    `(name = value)` are left as TupleExpressions."""
    value = value
    if (isinstance(value, e.TupleExpression)
            and len(value.expressions) == 1
            and value.expressions[0].name is None):
        value = value.expressions[0].value
    return value


def __to_parallel_expr(value: e.Expression, line_ref: p.LineRef) -> e.Expression:
    assert isinstance(value, e.TupleExpression)
    exprs = [entry.value for entry in value.expressions]
    return e.ParallelExpression(line_ref, exprs)


def __to_expr_lambda(result: p.Result[tuple[list[s.LetStatement], e.Expression]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    params, expression = result.value
    params2 = s.DestructureStatement(result.line_ref, '_', None, {}, (), None, None, params)
    return p.Result(e.LambdaExpression(tokens[0].line_ref, params2, expression, None), result.tokens, result.line_ref, result.errors)


def __to_ret_statement(value: e.Expression, line_ref: p.LineRef) -> s.ReturnStatement:
    return s.ReturnStatement(line_ref, value)


def __to_action_statement(value: e.Expression, line_ref: p.LineRef) -> s.ReturnStatement:
    return s.ActionStatement(line_ref, value)


def __to_if_statement(value, line_ref: p.LineRef) -> s.IfStatement:
    cond, body = value
    return s.IfStatement(line_ref, cond, body, [])


def __to_else_if_statement(value, line_ref: p.LineRef) -> s.ElseIfStatement:
    cond, body = value
    return s.ElseIfStatement(line_ref, cond, body)


def __to_else_statement(value, line_ref: p.LineRef) -> s.ElseStatement:
    return s.ElseStatement(line_ref, value)


def __to_let_statement(result: p.Result[tuple[dict[str, e.Expression|None], str|list[s.LetStatement], list[t.TypeSpec], list[str], list[e.Expression]]], tokens: list[p.Token]) -> p.Result[s.LetStatement]:
    attributes, target, dtype, array_marker, value = result.value
    errors = result.errors
    declared_type = p.first_or_none(dtype)
    # `name: Elem[lengthField]` — wrap the element type as the trailing array.
    if array_marker:
        if declared_type is None:
            errors = errors + [p.Error(result.line_ref, "an array field needs an element type, e.g. `name: Elem[lengthField]`")]
        else:
            declared_type = t.ArrayFieldSpec(result.line_ref, declared_type, array_marker[0])
    if isinstance(target, str):
        statement = s.LetStatement(tokens[0].line_ref, f"{target}@{result.line_ref.hash6()}", None, attributes or {}, (), p.first_or_none(value), declared_type)
    elif isinstance(target, list):
        statement = s.DestructureStatement(tokens[0].line_ref, '_', None, attributes, (), p.first_or_none(value), declared_type, target)
    else:
        raise ValueError("invalid target type")
    return p.Result(statement, result.tokens, result.line_ref, errors)


def __to_generic_let_statement(result: p.Result, tokens: list[p.Token]) -> p.Result[s.LetStatement]:
    """A single-name `let` that may carry generic params and a `where` clause —
    the form used to declare a GENERIC trait instance, e.g.
    `let [trait] _box_wrap<S,T>: _BoxWrap<S,T> = _BoxWrap() where Box<S,T>`.
    Destructuring `let (a,b) = …` falls through to __to_let_statement."""
    attributes, ident, generics, dtype, array_marker, value, where_traits = result.value
    errors = result.errors
    declared_type = p.first_or_none(dtype)
    if array_marker:
        if declared_type is None:
            errors = errors + [p.Error(result.line_ref, "an array field needs an element type, e.g. `name: Elem[lengthField]`")]
        else:
            declared_type = t.ArrayFieldSpec(result.line_ref, declared_type, array_marker[0])
    statement = s.LetStatement(
        tokens[0].line_ref, f"{ident}@{result.line_ref.hash6()}", None, attributes or {},
        tuple(generics), p.first_or_none(value), declared_type,
        trait_params=tuple(where_traits))
    return p.Result(statement, result.tokens, result.line_ref, errors)


def __to_match_arm(result: p.Result[tuple[list[s.LetStatement], list[e.Expression], e.Expression]], tokens: list[p.Token]) -> p.Result[m.MatchArm]:
    params, guard, body = result.value
    if len(params) == 0:
        return p.Result(m.MatchArm(result.line_ref, None, None, body, guard=p.first_or_none(guard)),
                        result.tokens, result.line_ref, result.errors)
    if len(params) == 1:
        param = params[0]
        raw_name = param.name.split('@')[0]
        name = None if raw_name == '_' else raw_name
        return p.Result(m.MatchArm(result.line_ref, name, param.declared_type, body, guard=p.first_or_none(guard)),
                        result.tokens, result.line_ref, result.errors)
    errors = result.errors + [p.Error(result.line_ref, "match arm must have exactly one parameter")]
    return p.Result(None, result.tokens, result.line_ref, errors)


def __to_match_arm_literal(result: p.Result[tuple[list[e.Expression], list[e.Expression], e.Expression]], tokens: list[p.Token]) -> p.Result[m.MatchArm]:
    literals, guard, body = result.value
    if not literals:
        # `()` is the else arm, not an empty literal list — let the
        # destructure form parse it.
        return p.Result.none(tokens, result.line_ref)
    return p.Result(m.MatchArm(result.line_ref, None, None, body,
                               literals=tuple(literals), guard=p.first_or_none(guard)),
                    result.tokens, result.line_ref, result.errors)


def __to_match_expression(value: tuple[e.Expression, list[m.MatchArm]], line_ref: p.LineRef) -> m.MatchExpression:
    subject, arms = value
    return m.MatchExpression(line_ref, subject, arms)


def __to_import_statement(value: list[str], line_ref: p.LineRef) -> s.ImportStatement:
    return s.ImportStatement(line_ref, '::'.join(value))


def __to_namespace_statement(value: list[str], line_ref: p.LineRef) -> s.NamespaceStatement:
    return s.NamespaceStatement(line_ref, '::'.join(value))


def __to_named_spec(value: tuple[list[str], str, list[t.TypeSpec]], line_ref: p.LineRef) -> t.NamedSpec:
    path, name, generics = value
    ns = t.NamedSpec(line_ref, '::'.join(path + [name]), tuple(generics))
    return ns


def __to_builtin_spec(value: str, line_ref: p.LineRef) -> t.NamedSpec:
    name = value
    return t.BuiltinSpec(line_ref, name)


def __to_named_tuple_entry(value: tuple[str, list[t.TypeSpec], list[e.Expression]]) -> t.TupleEntrySpec:
    name, e_type, default_expr = value
    return t.TupleEntrySpec(name, p.first_or_none(e_type), p.first_or_none(default_expr))


def __to_type_only_tuple_entry(value: t.TypeSpec) -> t.TupleEntrySpec:
    return t.TupleEntrySpec(None, value, None)


def __to_tuple_or_callable_spec(value: tuple[list[t.TupleEntrySpec],list[t.TypeSpec]], line_ref: p.LineRef) -> t.TypeSpec:
    entries, callable_result = value
    result_type = t.TupleSpec(line_ref, entries)
    if callable_result:
        result_type = t.CallableSpec(line_ref, result_type, callable_result[0])
    return result_type


def __to_tagged_spec_or_simple_type(result: p.Result[list[t.TypeSpec]], tokens: list[p.Token]) -> p.Result[t.TypeSpec]:
    entries: list[t.TypeSpec] = result.value
    if len(entries) == 0:
        # No member parsed at all: this is "no type here", not an empty union.
        return p.Result.none(tokens, result.line_ref)
    if len(entries) == 1:
        return p.Result(entries[0], result.tokens, result.line_ref, result.errors)
    return p.Result(t.CombinationSpec(result.line_ref, entries), result.tokens, result.line_ref, result.errors)


def __to_function(value: tuple[dict[str, e.Expression|None], str, list[s.TypeAliasStatement], list[s.LetStatement], list[t.TypeSpec], list[t.TypeSpec], list[s.Statement]], line_ref: p.LineRef) -> s.FunctionStatement:
    attributes, name, generics, params, dtype, where_traits, body_stmts = value
    if body_stmts and isinstance(body_stmts[-1], s.ReturnStatement):
        body = e.BlockExpression(line_ref, list(body_stmts[:-1]), body_stmts[-1].value)
    elif body_stmts:
        body = e.BlockExpression(line_ref, list(body_stmts), e.NothingExpression(line_ref))
    else:
        body = None
    statement = s.FunctionStatement(
        line_ref, f"{name}@{line_ref.hash6()}", None, attributes or {}, generics,
        s.DestructureStatement(line_ref, '_', None, {}, (), None, None, params),
        body, p.first_or_none(dtype), trait_params=where_traits)
    return statement


def __to_function_oneliner(value, line_ref: p.LineRef) -> s.FunctionStatement:
    attributes, name, generics, params, dtype, where_traits, expr = value
    body = e.BlockExpression(line_ref, [], expr)
    statement = s.FunctionStatement(
        line_ref, f"{name}@{line_ref.hash6()}", None, attributes or {}, generics,
        s.DestructureStatement(line_ref, '_', None, {}, (), None, None, params),
        body, p.first_or_none(dtype), trait_params=where_traits)
    return statement


def __flatten_inheritance(implements: list[t.TypeSpec]) -> list[t.TypeSpec]:
    """In an inheritance clause, `: A | B` means "implements BOTH A and B" — a
    list of interfaces that happens to be spelled with `|`, not the union *type*
    A-or-B. Flatten it here so a class's `implements` is a flat list of
    individual interfaces from the moment it is parsed: no later pass has to
    unpack a CombinationSpec that never should have been one, and the trait
    search never meets a union parent."""
    return [member for entry in implements
            for member in (entry.types if isinstance(entry, t.CombinationSpec) else [entry])]


def __to_class(value: tuple[dict[str, e.Expression|None], str, list[s.TypeAliasStatement], list[s.LetStatement], list[t.TypeSpec], list[t.TypeSpec], list[s.Statement]], line_ref: p.LineRef) -> s.ClassStatement:
    attributes, name, generics, params, implements, where_traits, body = value
    statement = s.ClassStatement(
        line_ref, f"{name}@{line_ref.hash6()}", None, attributes or {}, generics,
        s.DestructureStatement(line_ref, '_', None, {}, (), None, None, params),
        body, __flatten_inheritance(implements), False, trait_params=where_traits)
    return statement


def __to_interface(value: tuple[dict[str, e.Expression|None], str, list[s.TypeAliasStatement], list[t.TypeSpec], list[t.TypeSpec], list[s.Statement]], line_ref: p.LineRef) -> s.ClassStatement:
    attributes, name, generics, implements, where_traits, body = value
    statement = s.ClassStatement(
        line_ref, f"{name}@{line_ref.hash6()}", None, attributes or {}, generics,
        s.DestructureStatement(line_ref, '_', None, {}, (), None, None, []),
        body, __flatten_inheritance(implements), True, trait_params=where_traits)
    return statement


def __to_instance(value, line_ref: p.LineRef) -> s.Statement:
    # A first-class TraitInstanceStatement: anonymous at the surface — the
    # synthesized `instance$<tag>` name exists only for statement indexing
    # and never appears in diagnostics. Lowered to witness class + record
    # let AFTER checking, by lowering/instances.py.
    attributes, generics, pattern, where_traits, members = value
    statement = s.TraitInstanceStatement(
        line_ref, f"instance${line_ref.hash6()}", None,
        attributes or {}, tuple(generics),
        trait_params=tuple(where_traits),
        pattern=pattern, ambient='ambient' in (attributes or {}),
        statements=members)
    return statement


def __to_type_alias(value: tuple[dict, str, list[s.TypeAliasStatement], t.TypeSpec], line_ref: p.LineRef) -> s.TypeAliasStatement:
    # A typealias is purely a name for a type: no `where` clause (the old
    # `typealias [where]` conditional-instance channel was replaced by
    # `instance [ambient]`).
    attributes, name, generics, typespec = value
    statement = s.TypeAliasStatement(line_ref, f"{name}@{line_ref.hash6()}", None,
                                     attributes or {}, tuple(generics), typespec)
    return statement

def __to_attributes(value: list[tuple[str, list[e.Expression]]]) -> dict[str, e.Expression|None]:
    d = {key: (value[0] if value else None) for key, value in value[0]} if value else {}
    return d

def __to_generic_placeholder(value: tuple[dict[str, e.Expression|None], str], line_ref: p.LineRef) -> s.TypeAliasStatement:
    attributes, ident = value
    name = f"{ident}@{line_ref.hash6()}"
    is_linear = "linear" in attributes
    statement = s.TypeAliasStatement(line_ref, name, None, attributes, (),
                                     t.GenericPlaceholderSpec(line_ref, name, is_linear))
    return statement

def __to_flat_type_list(result: p.Result[list[t.TypeSpec]], tokens: list[p.Token]) -> p.Result[list[t.TypeSpec]]:
    if len(result.value) == 0:
        return p.Result([], result.tokens, result.line_ref, result.errors)
    xtype = result.value[0]
    if isinstance(xtype, t.CombinationSpec):
        return p.Result(list(xtype.types), result.tokens, result.line_ref, result.errors)
    return p.Result([xtype], result.tokens, result.line_ref, result.errors)

def parse_type(tokens: list[p.Token]) -> p.Result[t.TypeSpec]:
    return __parse_type_any(tokens)
__parse_type = p.Parser(parse_type)


def parse_expression(tokens: list[p.Token]) -> p.Result[e.Expression]:
    return __parse_ternery(tokens) # Real function allows recursion
__parse_expression = p.Parser(parse_expression)


def parse_statement(tokens: list[p.Token]) -> p.Result[s.Statement]:
    return __parse_statement_any(tokens) # Real function allows recursion
__parse_statement = p.Parser(parse_statement)


############
## TypeSpecs

__parse_maybe_colon_type = p.maybe(p.requires(p.sym(":"), __parse_type, "missing type"))
__parse_maybe_equal_expr = p.maybe(p.requires(p.sym("="), __parse_expression, "missing default value"))

__parse_maybe_generic_spec = p.maybe(p.requires(
    p.sym("<"), p.delimited_list(__parse_type, ",") & p.close_angle(),
    "missing generics")).map(__to_flat_list)

__parse_type_builtin = (p.discard_sym("__builtin_type__") & p.discard_sym("<") & p.ident() & p.discard_sym(">")).build(__to_builtin_spec)
__parse_type_named = (p.many(p.ident() & p.discard_sym("::")) & p.ident() & __parse_maybe_generic_spec).build(__to_named_spec)
# A tuple-type entry: the colon PRECEDES the type, always. `name[: Type][=
# default]` is a named field (type optional — inference may fill it), and
# `:Type` is an unnamed typed field. So `(Int, Int)` is two fields NAMED
# `Int` with no type, and `(:Int, :Int)` is the unnamed pair-of-Ints —
# exactly the function-parameter model, applied to every tuple type.
__parse_type_tuple_entry = (
      ((p.ident() & __parse_maybe_colon_type & __parse_maybe_equal_expr).map(__to_named_tuple_entry))
    | ((p.discard_sym(":") & __parse_type).map(__to_type_only_tuple_entry)))
__parse_type_tuple_or_callable = p.requires(
    p.discard_sym("("),
      ((p.delimited_list(__parse_type_tuple_entry, ",") & p.discard_sym(")") & __parse_maybe_colon_type).build(__to_tuple_or_callable_spec)),
    "incomplete structured type")
__parse_type_grouped = p.requires(
    p.discard_sym("("),
    __parse_type & p.discard_sym(")"),
    "incomplete grouped type")
__parse_type_any2 = __parse_type_tuple_or_callable | __parse_type_grouped | __parse_type_builtin | __parse_type_named
__parse_type_any = p.delimited_list(__parse_type_any2, "|") >> __to_tagged_spec_or_simple_type


##############
## Expressions

def __parse_attr_tuple(tokens: list[p.Token]) -> p.Result:
    return __parse_expr_tuple(tokens)

__parse_attr_name = p.ident() | p.sym(["where", "let", "fun", "class", "interface", "ret", "import", "namespace"])
__parse_attr_value = (p.discard_sym("=") & (__string() | __integer())) | p.Parser(__parse_attr_tuple)
__parse_attributes = p.maybe(p.discard_sym("[") & p.delimited_list(
    __parse_attr_name & p.maybe(__parse_attr_value)
    , ",") & p.discard_sym("]")).map(__to_attributes)

def parse_target_type_expr(tokens: list[p.Token]) -> p.Result[s.LetStatement]:
    return __parse_target_type_expr_any(tokens)
__parse_target_type_expr = p.Parser(parse_target_type_expr)

# A field declared `name: Elem[lengthField]` is its class's trailing
# variable-length array — `[lengthField]` names the Int32 length field. Parsed
# here (not in the type grammar) so `[` is only special in a field declaration,
# which keeps the type grammar simple and the errors local. The field may appear
# in any position; ClassStatement.check enforces exactly one (plus [final] and a
# valid length field), and codegen moves it to the end of the object.
__parse_maybe_array_marker = p.maybe(p.discard_sym("[") & p.ident() & p.discard_sym("]"))
__parse_destructure_parts = p.discard_sym('(') & p.delimited_list(__parse_target_type_expr, ',') & p.discard_sym(')')
__parse_maybe_destructure_parts = p.maybe(__parse_destructure_parts).map(__to_flat_list)
__parse_target_type_expr_any = (__parse_attributes & (p.ident()|__parse_destructure_parts) & __parse_maybe_colon_type & __parse_maybe_array_marker & __parse_maybe_equal_expr) >> __to_let_statement

__parse_maybe_type_params = p.maybe(p.requires(
    p.sym("<"), p.delimited_list(__parse_type, ",") & p.close_angle(),
    "missing generics")).map(__to_flat_list)

__parse_expr_tuple_entry = (((p.discard_sym("*") & __parse_expression).map(__to_spread_entry))
                            | ((p.maybe(p.ident() & p.discard_sym("=")) & __parse_expression).map(__to_expr_tuple_entry)))
__parse_expr_tuple = p.requires(p.sym("("), p.delimited_list(__parse_expr_tuple_entry, ",") & p.discard_sym(")"), "invalid tuple").build(__to_expr_tuple)
__parse_lambda = (__parse_destructure_parts & p.discard_sym("=>") & __parse_expression) >> __to_expr_lambda
__parse_builtin_op = p.requires(p.sym("__builtin_op__"), p.discard_sym("<") & __parse_type & p.discard_sym(">") & __parse_expr_tuple, "invalid use of __builtin_op__") >> __to_builtin_op
__parse_named_fully_qualified = (__named() & p.many(p.discard_sym("::") & __named()) & __parse_maybe_type_params).map(__to_named_fully_qualified)

# match arm: "(" literal ("," literal)* ")" |  "(" name ":" type ")"  |  "()"
# — each optionally guarded by `if cond` — then "=>" expr. A literal may be
# an inclusive integer/char/float range `lo .. hi` (floats parse first, as in
# the expression grammar: `1.5` is a NUMBER token __integer would reject).
__parse_signed_integer = ((p.discard_sym("-") & __integer()) >> __to_negate) | __integer()
__parse_signed_float   = ((p.discard_sym("-") & __float())   >> __to_negate) | __float()


def __to_match_range(value: tuple[e.Expression, e.Expression], line_ref: p.LineRef) -> m.MatchRange:
    lo, hi = value
    return m.MatchRange(line_ref, lo, hi)


__parse_match_bound = __parse_signed_float | __parse_signed_integer | __char()
__parse_match_range = (__parse_match_bound & p.discard_sym("..") & __parse_match_bound).build(__to_match_range)
__parse_match_literal   = __parse_match_range | __parse_signed_float | __parse_signed_integer | __char() | __string()
__parse_maybe_arm_guard = p.maybe(p.requires(
    p.discard_sym("if"), __parse_expression, "missing guard expression"))
__parse_match_arm_literal = p.block(
    (p.discard_sym('(') & p.delimited_list(__parse_match_literal, ",") & p.discard_sym(')')
     & __parse_maybe_arm_guard & p.discard_sym("=>") & __parse_expression) >> __to_match_arm_literal)
__parse_match_arm_destructure = p.block((__parse_destructure_parts & __parse_maybe_arm_guard & p.discard_sym("=>") & __parse_expression) >> __to_match_arm)
__parse_match_arm = __parse_match_arm_literal | __parse_match_arm_destructure
__parse_match_subject = p.requires(p.sym("("), __parse_expression & p.discard_sym(")"), "invalid match subject")
__parse_match = p.requires(p.discard_sym("match"), __parse_match_subject & p.many(__parse_match_arm), "invalid match expression").build(__to_match_expression)

__parse_parallel = p.requires(p.sym("__parallel__"), __parse_expr_tuple, "invalid use of __parallel__").build(__to_parallel_expr)

__parse_paren_expr = __parse_expr_tuple.map(__to_paren_expr)
__parse_terminal = __float() | __integer() | __char() | __string() | __regex() | __parse_builtin_op | __parse_match | __parse_parallel | __parse_named_fully_qualified | __parse_lambda | __parse_paren_expr

# Postfix operators form ONE left-associative chain so dot/call/index interleave
# freely: `f().g()`, `a().b`, `m()[0].x`. `.` is only ever member access (floats
# tokenise their own `.`), so consuming it greedily here is unambiguous.
__parse_postfix_dot   = (p.discard_sym(".") & __parse_terminal) >> __to_dot_op
__parse_postfix_call  = __parse_expr_tuple.build(__to_call_op)
__parse_postfix_index = p.requires(p.discard_sym("["), __parse_expression & p.discard_sym("]"), "invalid index expression").build(__to_index_op)
__parse_invoke  = (__parse_terminal & p.many(__parse_postfix_dot | __parse_postfix_call | __parse_postfix_index)).map(__to_invokes)
def __to_with(value, line_ref: p.LineRef):
    # `with subject(name = value, …)` parses as `with` + an ordinary invoke:
    # the invoke is naturally Call(subject, named-tuple), and the builder
    # REINTERPRETS it. Anything else (no call, no replacements) still builds
    # the node — the shape rules are CHECK errors per the ruling, not parse
    # errors.
    expr = value
    if isinstance(expr, e.CallExpression) and isinstance(expr.parameter, e.TupleExpression):
        statement = e.WithExpression(line_ref, expr.function, expr.parameter)
    else:
        statement = e.WithExpression(line_ref, expr,
                                     e.TupleExpression(line_ref, []))
    return statement


__parse_unary   = (((p.discard_sym("with") & __parse_invoke).build(__to_with))
                 | (p.discard_sym("-") & __parse_invoke) >> __to_negate
                 | (p.discard_sym("!") & __parse_invoke).build(__to_not)
                 | (p.discard_sym("~") & __parse_invoke).build(__to_invert)
                 | __parse_invoke)
__parse_divmul  = (__parse_unary    & p.many(p.sym(["%", "/", "*"]) & __parse_unary     )) >> __to_call_operators
__parse_addsub  = (__parse_divmul   & p.many(p.sym(["+", "-"])      & __parse_divmul    )) >> __to_call_operators
# Shifts bind looser than +/- but tighter than the bitwise/comparison ops
# (C order: `a + b << c` is `(a + b) << c`).
__parse_shift   = (__parse_addsub   & p.many(p.sym(["<<", ">>"])    & __parse_addsub    )) >> __to_call_operators
# Bitwise operators bind tighter than comparison (so `a & b == c` is
# `(a & b) == c`, avoiding C's footgun) with the usual & > ^ > | order.
__parse_bitand  = (__parse_shift    & p.many(p.sym("&")             & __parse_shift     )) >> __to_call_operators
__parse_bitxor  = (__parse_bitand   & p.many(p.sym("^")             & __parse_bitand    )) >> __to_call_operators
__parse_bitor   = (__parse_bitxor   & p.many(p.sym("|")             & __parse_bitxor    )) >> __to_call_operators
__parse_compare = (__parse_bitor    & p.many(p.sym(["<", "==", ">", "!=", "<=", ">="]) & __parse_bitor)) >> __to_call_operators
# `is`/`!is` type test: binds looser than the comparison operators, tighter than
# `?>`/`&&`/`||`. The right operand is a TYPE (so `is` is a contextual keyword —
# an identifier in operator position — needing no tokeniser change).
__parse_is      = (__parse_compare  & p.maybe(p.maybe(p.sym("!")) & p.ident("is") & __parse_type)) >> __to_is
# `|>` and `?>` share ONE level so mixed chains fold strictly left-to-right.
# The pipe lives here — LOOSER than the arithmetic/comparison operators (like
# every ML-family pipe), so `n - 1 |> f` pipes `n - 1`, not `1`; it once sat
# between unary and `*`, which silently turned `n - 1 |> (m) => self(m, …)`
# into `n - self(1, …)` — a non-tail self-call.
__parse_bind    = (__parse_is       & p.many(p.sym(["?>", "|>"])     & __parse_is        )) >> __to_bind_or_pipeline
# Short-circuit logical operators: `&&` binds tighter than `||`, both looser than
# the comparison/bind level and tighter than the ternary `?:`. They are parse-time
# sugar for the ternary (see __to_logical_and/__to_logical_or), so short-circuit
# is a guaranteed semantic rather than an optimiser artefact.
__parse_coalesce= (__parse_bind     & p.many(p.discard_sym("??")     & __parse_bind      )).map(__to_coalesce)
__parse_logand  = (__parse_coalesce & p.many(p.discard_sym("&&")     & __parse_coalesce  )).map(__to_logical_and)
__parse_logor   = (__parse_logand   & p.many(p.discard_sym("||")     & __parse_logand    )).map(__to_logical_or)
__parse_ternery = (__parse_logor    & p.many(p.discard_sym("?") & __parse_logor & p.discard_sym(":") & __parse_logor)).map(__to_ternery)


#############
## Statements

__parse_maybe_where_constraints = p.maybe(p.requires(
    p.sym("where"), __parse_type,
    "missing type constraints")) >> __to_flat_type_list

__parse_maybe_generic_statement = p.maybe(p.requires(
    p.sym("<"), p.delimited_list((__parse_attributes & p.ident()).build(__to_generic_placeholder), ",") & p.discard_sym(">"),
    "missing generics")).map(__to_flat_list)

__parse_action = p.block(
    __parse_expression.build(__to_action_statement))

__parse_ret = p.block(p.requires(
    p.discard_sym("ret"),
    __parse_expression.build(__to_ret_statement),
    "missing return value"))

__parse_fun = p.block(p.requires(
    p.discard_sym("fun"),
    (__parse_attributes & p.ident() & __parse_maybe_generic_statement & __parse_destructure_parts & __parse_maybe_colon_type & __parse_maybe_where_constraints & p.discard_sym("=>") & __parse_expression).build(__to_function_oneliner)
    | (__parse_attributes & p.ident() & __parse_maybe_generic_statement & __parse_destructure_parts & __parse_maybe_colon_type & __parse_maybe_where_constraints & p.many(__parse_statement)).build(__to_function),
    "invalid function statement"))

__parse_class = p.block(p.requires(
    p.discard_sym("class"),
    (__parse_attributes & p.ident() & __parse_maybe_generic_statement & __parse_maybe_destructure_parts & __parse_maybe_colon_type & __parse_maybe_where_constraints & p.many(__parse_statement)).build(__to_class),
    "invalid class statement"))

__parse_interface = p.block(p.requires(
    p.discard_sym("interface"),
    (__parse_attributes & p.ident() & __parse_maybe_generic_statement                             & __parse_maybe_colon_type & __parse_maybe_where_constraints & p.many(__parse_statement)).build(__to_interface),
    "invalid interface statement"))

# A single-name let may carry generic params and a trailing `where` (generic
# trait instances); the destructuring form falls through to the plain target
# parser. The generic form is tried first — for a plain `let x = …` it matches
# with empty generics/where and yields the same statement.
__parse_let_generic = (__parse_attributes & p.ident() & __parse_maybe_generic_statement
                       & __parse_maybe_colon_type & __parse_maybe_array_marker & __parse_maybe_equal_expr
                       & __parse_maybe_where_constraints) >> __to_generic_let_statement

__parse_let = p.block(p.requires(
    p.discard_sym("let"),
    __parse_let_generic | __parse_target_type_expr,
    "invalid let statement"))

# Anonymous: attributes, optional generics, ONE interface pattern (a type),
# optional `where`, then the member functions — a TraitInstanceStatement.
__parse_instance = p.block(p.requires(
    p.discard_sym("instance"),
    (__parse_attributes & __parse_maybe_generic_statement & __parse_type
     & __parse_maybe_where_constraints & p.many(__parse_statement)).build(__to_instance),
    "invalid instance statement"))

__parse_type_alias = p.block(p.requires(
    p.discard_sym("typealias"),
    (__parse_attributes & p.ident() & __parse_maybe_generic_statement & p.discard_sym(":")
     & __parse_type).build(__to_type_alias),
    "invalid typealias statement"))

__parse_import = p.block(p.requires(
    p.discard_sym("import"),
    p.delimited_list(p.ident(), "::").build(__to_import_statement),
    "invalid import statement"))

__parse_namespace = p.block(p.requires(
    p.discard_sym("namespace"),
    p.delimited_list(p.ident(), "::").build(__to_namespace_statement),
    "invalid namespace statement"))

# `if`, `else if`, `else` parse as independent sibling statements at the
# same indent. `collapse_else_if` (in pyast/statement.py) folds proper
# sequences into a single right-nested `IfStatement` during compile;
# orphan `else`/`else if` are reported by their `check()`.
__parse_if = p.block(p.requires(
    p.discard_sym("if"),
    (__parse_expression & p.many(__parse_statement)).build(__to_if_statement),
    "invalid if statement"))

__parse_else_if = p.block(p.requires(
    p.discard_sym("else") & p.discard_sym("if"),
    (__parse_expression & p.many(__parse_statement)).build(__to_else_if_statement),
    "invalid else-if statement"))

__parse_else = p.block(p.requires(
    p.discard_sym("else"),
    p.many(__parse_statement).build(__to_else_statement),
    "invalid else statement"))

# Sentinel for "no constructor parameter list was written" (distinct from an
# empty `()`, which is the empty list). Must be non-None so the Result stays
# truthy (Result.__bool__ is `value is not None`) and non-tuple so the `&`
# combinator keeps it as a single sequence element.
__NO_ENUM_PARAMS = object()

def __to_enum_params(value):
    # `p.maybe` yields [] when no parens were written and [fields] when a `(...)`
    # list was (fields possibly empty for `()`). Preserve that distinction
    # rather than flattening both to [] like __parse_maybe_destructure_parts.
    parts = value
    value = __NO_ENUM_PARAMS if not parts else parts[0]
    return value
__parse_enum_params = p.maybe(__parse_destructure_parts).map(__to_enum_params)


def __to_enum(value, line_ref: p.LineRef) -> s.EnumStatement:
    attributes, name, generics, params, variants = value
    type_params = tuple(generics) if generics else ()
    has_param_list = params is not __NO_ENUM_PARAMS
    fields = [] if params is __NO_ENUM_PARAMS else params
    statement = s.EnumStatement(
        line_ref, f"{name}@{line_ref.hash6()}", None, attributes, type_params,
        s.DestructureStatement(line_ref, '_', None, {}, (), None, None, fields),
        variants,
        has_param_list=has_param_list)
    return statement


def parse_enum(tokens: list[p.Token]) -> p.Result[s.EnumStatement]:
    return __parse_enum_any(tokens)
__parse_enum = p.Parser(parse_enum)

# Attributes come BEFORE the name (`enum [hashed] Foo`), exactly as for class.
__parse_enum_any = p.block(p.requires(
    p.discard_sym("enum"),
    (__parse_attributes & p.ident() & __parse_maybe_generic_statement & __parse_enum_params & p.many(__parse_enum)).build(__to_enum),
    "invalid enum statement"))


def _create_enum_leaf_constructors(root: s.EnumStatement, ancestors: list[s.EnumStatement], import_group: s.ImportGroup) -> list[s.Statement]:
    results: list[s.Statement] = []
    all_ancestors = ancestors + [root]
    if not root.variants and not root.has_param_list:
        return results  # uninhabited empty type (e.g. Never): no constructor
    if not root.variants:
        all_params = [let for anc in all_ancestors for let in anc.parameters.flatten()]
        true_root = ancestors[0] if ancestors else root
        root_name = true_root.name
        leaf_name = root.name
        type_params = true_root.type_params
        # A construction builds exactly one variant, so the constructor
        # returns the LEAF type (USER RULING 2026-08-24). Representation is
        # unchanged — a leaf-typed value carries the root's struct — so this
        # is a type-system fact: fresh constructions feed leaf-typed
        # positions, and widening to the root is free. Generic enums carry
        # the type params on the leaf reference exactly as they did on the
        # root's.
        if type_params:
            return_type_params = tuple(tp.type for tp in type_params)
            return_type = t.NamedSpec(root.line_ref, leaf_name, type_params=return_type_params)
        else:
            return_type = t.NamedSpec(root.line_ref, leaf_name)
        field_args = {let.name: e.NamedExpression(let.line_ref, let.name) for let in all_params}
        destr = s.DestructureStatement(root.line_ref, '_', None, {}, (), None, None, all_params)
        new_enum_type_params = tuple(tp.type for tp in type_params) if type_params else ()
        new_enum_expr = e.NewEnumExpression(root.line_ref, root_name, leaf_name, field_args, type_params=new_enum_type_params)
        body = e.BlockExpression(root.line_ref, [], new_enum_expr)
        constructor = s.FunctionStatement(
            root.line_ref, root.name, import_group, {}, type_params, destr, body, return_type)
        results.append(constructor)
    else:
        for v in root.variants:
            results += _create_enum_leaf_constructors(v, all_ancestors, import_group)
    return results


__parse_statement_any = p.block(
    __parse_class | __parse_interface | __parse_instance | __parse_fun | __parse_let
    | __parse_type_alias | __parse_import | __parse_namespace | __parse_ret
    | __parse_action | __parse_enum
    | __parse_if | __parse_else_if | __parse_else)



__parse = p.many(p.block(__parse_statement), skip=p.block(p.imm(None)))
def parse(tokens: list[p.Token]) -> p.Result[list[s.Statement]]:
    result = __parse(tokens)

    # Fix up namespace and import elements
    statements = result.value
    if not statements:
        return result

    # Block-scoped visibility (USER RULING 2026-08-23): a statement sees its
    # own namespace block — the block's self-import (members reference their
    # siblings unqualified) plus the imports written in that block, wherever
    # they sit within it — and nothing else. Declaring a namespace earlier
    # in the file grants NO access to it, and imports do not pool across
    # blocks; anything further afield needs an `import` or a fully
    # qualified name. Blocks are delimited by `namespace` declarations;
    # statements before the first one form the default block (namespace
    # Main, no self-import — unchanged behaviour).
    block_imports: list[list[s.ImportStatement]] = [[]]
    for statement in statements:
        if isinstance(statement, s.NamespaceStatement):
            block_imports.append([s.ImportStatement(statement.line_ref, statement.path)])
        elif isinstance(statement, s.ImportStatement):
            block_imports[-1].append(statement)
    block_groups = [s.ImportGroup(imports=tuple(b)) for b in block_imports]

    errors = result.errors
    new_statements = []
    current_namespace = "Main::"
    block = 0
    import_group = block_groups[0]

    for statement in result.value:
        match statement:
            case s.ImportStatement(): # Discard as it was processed earlier
                pass
            case s.NamespaceStatement(line_ref, path): # Note value and discard
                current_namespace = f"{path}::"
                block += 1
                import_group = block_groups[block]
            case s.FunctionStatement() | s.LetStatement() | s.TypeAliasStatement() | s.ClassStatement() | s.TraitInstanceStatement(): # Rename and add to list
                # A member is a vtable slot: its signature is the interface
                # declaration with the OWNER's type args substituted, so a
                # member function declares neither type params nor a `where`
                # clause (generics/constraints belong on the class/instance).
                if isinstance(statement, (s.ClassStatement, s.TraitInstanceStatement)):
                    for m in statement.statements:
                        if isinstance(m, s.FunctionStatement) and (m.type_params or m.trait_params):
                            errors = errors + [p.Error(m.line_ref,
                                "a member function declares neither type parameters nor a "
                                "`where` clause — generics and constraints belong on the "
                                "class or instance")]
                statement = statement.add_namespace(current_namespace)
                statement = dataclasses.replace(statement, imports=import_group)
                if isinstance(statement, s.ClassStatement) and not statement.is_interface:
                    statement = pyast.utils.create_array_accessor(statement)
                new_statements.append(statement)
                if isinstance(statement, s.ClassStatement) and not statement.is_interface:
                    new_statements.append(pyast.utils.create_constructor(statement))
            case s.EnumStatement():
                statement = statement.add_namespace(current_namespace)
                statement = dataclasses.replace(statement, imports=import_group)
                new_statements.append(statement)
                new_statements += _create_enum_leaf_constructors(statement, [], import_group)

            case _: # Discard and report an error
                errors.append(p.Error(statement.line_ref, f"unexpected statement {type(statement)}"))

    return p.Result(new_statements, result.tokens, result.line_ref, errors)






