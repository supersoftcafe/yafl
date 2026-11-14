"""Run one shard of the compiler suite: `I/N` picks the I-th of N disjoint
module sets that together are every module the suite discovers.

    python tests/suite_shard.py 2/3 unittest-parallel -j 0 -s tests -t .
    python tests/suite_shard.py --list 3           # what each shard holds

The command after the shard is the suite command, run with one `-k` per module
of this shard (unittest-parallel and `python -m unittest discover` both take
them). `-k tests.test_io.` matches every test id in `tests.test_io` and in no
other module: the trailing dot stops `test_io` from matching `test_io_readline`.

CI runs the full regression's suite as several shards on separate runners,
because it is most of the wall time and its modules are independent. Modules
are dealt longest first to the lightest shard, by the weights below: about a
module's seconds on a 4-core runner. A module missing from the table gets the
default weight, so a stale table only unbalances the shards — every module
still runs, in exactly one shard.

NOT a test module: the filename does not match `test*.py`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent

# Seconds per module, measured 2026-11-13 (the full suite, cold reference
# cache, four at a time). Modules under 30 s take the default.
_WEIGHTS = {
    "test_bootstrap_c_o0": 1747,
    "test_bootstrap_c_o1": 1744,
    "test_bootstrap_c_o0p": 1742,
    "test_bootstrap_c_o2": 1729,
    "test_bootstrap_cli": 1456,
    "test_bootstrap_c_o2p": 1264,
    "test_bootstrap_c_o3": 1262,
    "test_bootstrap_converge": 1011,
    "test_bootstrap_ast": 628,
    "test_bootstrap_project": 450,
    "test_bootstrap_exits": 402,
    "test_bootstrap_c_order": 319,
    "test_bootstrap_generics": 315,
    "test_bootstrap_c_warnings": 311,
    "test_bootstrap_postmono": 286,
    "test_bootstrap_simple": 267,
    "test_bootstrap_tail": 234,
    "test_bootstrap_literals": 222,
    "test_bootstrap_inline": 213,
    "test_bootstrap_lambdas": 213,
    "test_bootstrap_lazy": 210,
    "test_bootstrap_reject": 176,
    "test_profile": 97,
    "test_linear": 78,
    "test_test_runner": 69,
    "test_bootstrap_format": 61,   # measured 2026-11-14, alone
    "test_inline_attribute": 58,
    "test_param_body_inference": 51,
    "test_sync_calls": 47,
    "test_builder_gc": 44,
    "test_read_all": 41,
    "test_runtime": 39,
    "test_args": 37,
    "test_union_repr": 36,
    "test_bootstrap_instances": 33,
    "test_io": 32,
}
_DEFAULT_WEIGHT = 10


def modules() -> list[str]:
    """Every module the suite's discovery (`-s tests`, `test*.py`) finds."""
    return sorted(p.stem for p in _TESTS.glob("test*.py"))


def shards(count: int) -> list[list[str]]:
    """`count` disjoint module lists covering `modules()`: longest first, each
    to the lightest shard so far (ties to the lowest-numbered)."""
    out: list[list[str]] = [[] for _ in range(count)]
    load = [0] * count
    for mod in sorted(modules(), key=lambda m: (-_WEIGHTS.get(m, _DEFAULT_WEIGHT), m)):
        i = load.index(min(load))
        out[i].append(mod)
        load[i] += _WEIGHTS.get(mod, _DEFAULT_WEIGHT)
    return out


def _parse_shard(text: str) -> tuple[int, int]:
    index, _, count = text.partition("/")
    i, n = int(index), int(count)
    if not 1 <= i <= n:
        raise ValueError(f"shard {text}: want I/N with 1 <= I <= N")
    return i, n


def main(argv: list[str]) -> int:
    if argv[:1] == ["--list"] and len(argv) == 2:
        for i, mods in enumerate(shards(int(argv[1])), 1):
            weight = sum(_WEIGHTS.get(m, _DEFAULT_WEIGHT) for m in mods)
            print(f"shard {i}/{argv[1]}: {len(mods)} modules, weight {weight}")
            for m in mods:
                print(f"    {m}")
        return 0
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    i, n = _parse_shard(argv[0])
    mine = shards(n)[i - 1]
    command = [*argv[1:], *(arg for m in mine for arg in ("-k", f"tests.{m}."))]
    print(f"suite shard {i}/{n}: {len(mine)} modules", flush=True)
    os.execvp(command[0], command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
