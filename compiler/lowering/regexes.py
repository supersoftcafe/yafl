"""Regex literal interning + compile-time validation.

Every `re"..."` literal is VALIDATED here (pattern syntax errors are build
errors, with the offending position) and rewritten to a reference to a
shared per-pattern global:

    let $regexes::regex@N: System::Regex = Regex("pattern")

One global per DISTINCT pattern — identical literals dedup, and a literal
inside a loop can never reconstruct its Regex: the global's non-trivial
initialiser auto-promotes to `[lazy]`, so each pattern compiles exactly once
per process, on first use. Mirrors lowering/strings.py; must run BEFORE the
convergence loop (the created globals need typing) and therefore before
fix_global_strings (which interns the pattern string the initialiser holds).

The validator accepts exactly the v1 engine grammar (stdlib/regex.yafl):
literals, `.`, escapes (\\d \\w \\s and negations, control escapes, escaped
punctuation), classes `[...]` with ranges and `^` negation, alternation,
groups `(...)` / `(?:...)`, quantifiers `* + ?` with lazy variants, anchors
`^ $`. Backreferences are rejected outright — the engine guarantees linear
time, and backreferences are incompatible with that, permanently.
"""
from __future__ import annotations

from typing import Any

import pyast.statement as s
import pyast.expression as e
import pyast.resolver as g
import pyast.typespec as t
import pyast.rewrite as rw

from pyast.statement import ImportGroup
from parsing.tokenizer import LineRef
from parsing.parselib import Error

_CLASS_ESCAPES = frozenset("dDwWsS")
_CONTROL_ESCAPES = frozenset("nrt0")
_PUNCT_ESCAPES = frozenset("\\.^$|?*+()[]{}-/\"' ")


def _validate(pattern: str) -> str | None:
    """None when `pattern` is valid v1 syntax, else a message (with a 0-based
    byte position) describing the first problem."""
    i, n = 0, len(pattern)
    depth = 0
    # Tracks whether a quantifier has something to repeat.
    prev_quantifiable = False
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            if i + 1 >= n:
                return f"dangling backslash at {i}"
            nxt = pattern[i + 1]
            if nxt.isdigit():
                return (f"backreference \\{nxt} at {i} — not supported: the engine "
                        f"guarantees linear-time matching, which backreferences preclude")
            if nxt not in _CLASS_ESCAPES | _CONTROL_ESCAPES | _PUNCT_ESCAPES:
                return f"unknown escape \\{nxt} at {i}"
            i += 2
            prev_quantifiable = True
            continue
        if ch == "[":
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":  # leading ] is a literal
                j += 1
            while j < n and pattern[j] != "]":
                if pattern[j] == "\\":
                    if j + 1 >= n:
                        return f"dangling backslash at {j}"
                    if pattern[j + 1].isdigit():
                        return f"backreference in class at {j} — not supported"
                    j += 2
                    continue
                j += 1
            if j >= n:
                return f"unclosed character class starting at {i}"
            if j == i + 1 or (pattern[i + 1] == "^" and j == i + 2):
                return f"empty character class at {i}"
            i = j + 1
            prev_quantifiable = True
            continue
        if ch == "(":
            if pattern.startswith("(?:", i):
                i += 3
            elif pattern.startswith("(?", i):
                return f"unsupported group flavour at {i} (only capturing `(` and `(?:` exist)"
            else:
                i += 1
            depth += 1
            prev_quantifiable = False
            continue
        if ch == ")":
            if depth == 0:
                return f"unbalanced ')' at {i}"
            depth -= 1
            i += 1
            prev_quantifiable = True
            continue
        if ch in "*+?":
            if not prev_quantifiable:
                return f"quantifier '{ch}' at {i} has nothing to repeat"
            i += 1
            if i < n and pattern[i] == "?":  # lazy variant
                i += 1
            prev_quantifiable = False
            continue
        if ch == "{":
            return f"counted repetition at {i} is not supported in v1 (expand it, or use * + ?)"
        if ch == "|":
            i += 1
            prev_quantifiable = False
            continue
        if ch in "^$":
            i += 1
            prev_quantifiable = False
            continue
        i += 1
        prev_quantifiable = True
    if depth != 0:
        return "unclosed group"
    return None


def fix_global_regexes(statements: list[s.Statement]) -> tuple[list[s.Statement], list[Error]]:
    # Collect every regex literal (with a line_ref for error reporting).
    found: dict[str, LineRef] = {}

    def collect(resolver: g.Resolver, thing: Any) -> Any:
        if isinstance(thing, e.RegexExpression):
            found.setdefault(thing.pattern, thing.line_ref)
        return rw.UNCHANGED

    for x in statements:
        x.search_and_replace(g.ResolverRoot([]), collect)
    if not found:
        return statements, []

    errors = [Error(lr, f"invalid regex: {msg}")
              for pattern, lr in sorted(found.items())
              if (msg := _validate(pattern)) is not None]
    if errors:
        return statements, errors

    # One shared global per distinct pattern. Sorted before numbering, like
    # $strings — set/dict order must never reach name generation.
    def create_global(index: int, pattern: str) -> s.LetStatement:
        lr = LineRef("$regexes", index + 1, 1)
        init = e.CallExpression(lr,
            e.NamedExpression(lr, "System::Regex"),
            e.TupleExpression(lr, [e.TupleEntryExpression(None, e.StringExpression(lr, pattern))]))
        return s.LetStatement(lr, f"$regexes::regex@{index}", ImportGroup(()), {}, (),
                              init, t.NamedSpec(lr, "System::Regex"))

    global_statements = {pattern: create_global(index, pattern)
                         for index, pattern in enumerate(sorted(found))}
    references = {pattern: e.NamedExpression(stmt.line_ref, stmt.name)
                  for pattern, stmt in global_statements.items()}

    def replace(resolver: g.Resolver, thing: Any) -> Any:
        if isinstance(thing, e.RegexExpression):
            return references[thing.pattern]
        return thing

    statements = [x.search_and_replace(g.ResolverRoot([]), replace) for x in statements]
    return list(global_statements.values()) + statements, []
