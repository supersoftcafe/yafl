"""Compile the generated C, as one clang or as several in parallel.

The C is one text that clang can also compile as K units (see codegen/gen.py):
K processes, each told its unit by -DYAFL_UNITS=K -DYAFL_UNIT=i, then one link.
Below `_UNIT_BYTES` a unit is not worth its own copy of the shared header, so
small programs stay a single compile; `_MAX_UNITS` bounds the memory of the
clangs running at once (a compiler-sized unit is a few hundred MB). A fixed
rule, not a probe of this machine, so the port makes the same choice.
Processes, never threads.
"""
from __future__ import annotations

import subprocess

from tempdir import process_temp_dir

_UNIT_BYTES = 4 * 1024 * 1024
_MAX_UNITS = 4


def unit_count(c_bytes: int) -> int:
    return max(1, min(_MAX_UNITS, c_bytes // _UNIT_BYTES))


def build(c_code: str, compile_args: list[str], link_args: list[str], output: str,
          timeout: float | None = None) -> str | None:
    """Compile `c_code` with `compile_args` and link it with `link_args` into
    `output`. Returns None on success, else clang's complaint."""
    units = unit_count(len(c_code))
    if units == 1:
        r = subprocess.run(["clang", *compile_args, "-x", "c", "-", *link_args, "-o", output],
                           input=c_code, text=True, capture_output=True, timeout=timeout)
        return None if r.returncode == 0 else r.stderr
    work = process_temp_dir()
    source = work / "program.c"
    source.write_text(c_code, encoding="utf-8")
    objects = [work / f"unit{i}.o" for i in range(units)]
    running = [subprocess.Popen(
                   ["clang", *compile_args, f"-DYAFL_UNITS={units}", f"-DYAFL_UNIT={i}",
                    "-c", str(source), "-o", str(obj)],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
               for i, obj in enumerate(objects)]
    errors = [proc.communicate(timeout=timeout)[1] for proc in running]
    failed = [err for proc, err in zip(running, errors) if proc.returncode != 0]
    if failed:
        return failed[0]
    r = subprocess.run(["clang", *map(str, objects), *link_args, "-o", output],
                       capture_output=True, text=True, timeout=timeout)
    return None if r.returncode == 0 else r.stderr
