"""YAFL libraries, manifests and discovery.

A *library* is a directory (or a `.yl` zip) containing a `yafl.toml` manifest, the
library's `.yafl` source files, and — for libraries with `[foreign]` parts — a
static native library and a C header. Because YAFL compiles whole-program and
monomorphises, a library's YAFL is shipped as *source* and joins the program; only
the foreign/runtime parts are native.

This module is deliberately self-contained (it imports nothing from `compiler`): it
locates libraries on a search path, reads their manifests, and exposes their YAFL
sources and native artifacts. See `docs/build-and-packaging.md` for the design.
"""
from __future__ import annotations

import os
import sys
import zipfile
import tomllib
import hashlib
import tempfile
import re
from pathlib import Path
from dataclasses import dataclass, field
from functools import cached_property


MANIFEST_NAME = "yafl.toml"
LIBRARY_ZIP_SUFFIX = ".yl"


class LibraryError(Exception):
    """A manifest is malformed, or two manifests claim the same namespace."""


@dataclass(frozen=True)
class SourceFile:
    """One YAFL source unit: its display name (for diagnostics) and its text."""
    filename: str
    content: str


@dataclass(frozen=True)
class Manifest:
    """A parsed `yafl.toml`. `headers`/`static_libs` are relative to the manifest."""
    name: str
    namespaces: tuple[str, ...]
    headers: tuple[str, ...] = ()
    static_libs: tuple[str, ...] = ()


def parse_manifest(text: str, origin: str) -> Manifest:
    """Parse manifest TOML text. `origin` names the source for error messages."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as ex:
        raise LibraryError(f"{origin}: invalid manifest TOML: {ex}") from ex

    def as_str_tuple(value, key) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return tuple(value)
        raise LibraryError(f"{origin}: '{key}' must be a string or list of strings")

    namespaces = as_str_tuple(data.get("namespaces"), "namespaces")
    if not namespaces:
        raise LibraryError(f"{origin}: a library manifest must declare at least one namespace")
    return Manifest(
        name=str(data.get("name") or "unnamed"),
        namespaces=namespaces,
        headers=as_str_tuple(data.get("headers"), "headers"),
        static_libs=as_str_tuple(data.get("static_libs"), "static_libs"),
    )


@dataclass
class Library:
    """A discovered library, backed either by a directory or a `.yl` zip.

    `_extra_inputs`/`_extra_*` let the build-tree dev System library be assembled from
    paths that don't live together under one root (stdlib here, yafl.h+libyafl.a in
    yafllib) — see `dev_system_library`."""
    manifest: Manifest
    root: Path                      # directory, or the .yl path
    is_zip: bool = False
    # Dev/synthetic libraries supply their pieces directly rather than via `root`.
    _explicit_sources: tuple[SourceFile, ...] | None = None
    _explicit_includes: tuple[Path, ...] | None = None
    _explicit_static: tuple[Path, ...] | None = None

    @property
    def namespaces(self) -> tuple[str, ...]:
        return self.manifest.namespaces

    def yafl_sources(self) -> list[SourceFile]:
        """The library's `.yafl` units, read into memory."""
        if self._explicit_sources is not None:
            return list(self._explicit_sources)
        if self.is_zip:
            out: list[SourceFile] = []
            with zipfile.ZipFile(self.root) as zf:
                for name in sorted(zf.namelist()):
                    if name.endswith(".yafl"):
                        out.append(SourceFile(Path(name).name, zf.read(name).decode("utf-8")))
            return out
        return [SourceFile(p.name, p.read_text(encoding="utf-8"))
                for p in sorted(self.root.rglob("*.yafl"))]

    def include_dirs(self) -> list[Path]:
        """Directories to put on the C compiler's `-I` path for this library."""
        if self._explicit_includes is not None:
            return list(self._explicit_includes)
        if not self.manifest.headers:
            return []
        base = self._materialised_native_dir()
        # Headers may sit in subdirs; expose each header's directory.
        return sorted({(base / h).parent for h in self.manifest.headers})

    def header_names(self) -> list[str]:
        """Basenames to `#include` into the generated C (resolved via -I dirs)."""
        if self._explicit_includes is not None:
            # Dev System: the header is yafl.h, included by basename.
            return list(self.manifest.headers) or ["yafl.h"]
        return [Path(h).name for h in self.manifest.headers]

    def static_libs(self) -> list[Path]:
        """Absolute paths of static archives to link for this library."""
        if self._explicit_static is not None:
            return list(self._explicit_static)
        if not self.manifest.static_libs:
            return []
        base = self._materialised_native_dir()
        return [base / s for s in self.manifest.static_libs]

    def _materialised_native_dir(self) -> Path:
        """For a directory library this is `root`. For a `.yl`, native artifacts are
        extracted to a content-hash-keyed cache dir so the C compiler can reach them."""
        if not self.is_zip:
            return self.root
        digest = hashlib.sha256(self.root.read_bytes()).hexdigest()[:16]
        cache = Path(tempfile.gettempdir()) / "yafl-lib-cache" / f"{self.manifest.name}-{digest}"
        cache.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.root) as zf:
            for rel in (*self.manifest.headers, *self.manifest.static_libs):
                dest = cache / rel
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(rel))
        return cache


def _read_library_at(path: Path) -> Library | None:
    """Read the library rooted at `path` (a directory with a manifest, or a `.yl`),
    or None if there's no manifest there."""
    if path.is_dir():
        manifest_path = path / MANIFEST_NAME
        if not manifest_path.is_file():
            return None
        manifest = parse_manifest(manifest_path.read_text(encoding="utf-8"), str(manifest_path))
        return Library(manifest=manifest, root=path)
    if path.is_file() and path.name.endswith(LIBRARY_ZIP_SUFFIX):
        with zipfile.ZipFile(path) as zf:
            try:
                text = zf.read(MANIFEST_NAME).decode("utf-8")
            except KeyError:
                raise LibraryError(f"{path}: .yl has no {MANIFEST_NAME}")
        return Library(manifest=parse_manifest(text, f"{path}!{MANIFEST_NAME}"), root=path, is_zip=True)
    return None


def discover_libraries(search_paths: list[Path]) -> list[Library]:
    """Find every library on the search path: immediate sub-directories with a
    manifest, and `*.yl` files. Earlier paths take precedence (first wins) but a
    later path declaring an already-owned namespace is still an error — uniqueness
    is enforced by `namespace_index`."""
    found: list[Library] = []
    seen_roots: set[Path] = set()
    for base in search_paths:
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            resolved = entry.resolve()
            if resolved in seen_roots:
                continue
            lib = _read_library_at(entry)
            if lib is not None:
                seen_roots.add(resolved)
                found.append(lib)
    return found


@dataclass(frozen=True)
class LinkSpec:
    """What the C compiler needs to build against a set of loaded libraries:
    headers to `#include` (by basename, found via `include_dirs`) and static
    archives to link."""
    headers: tuple[str, ...]
    include_dirs: tuple[Path, ...]
    static_libs: tuple[Path, ...]


def link_spec_for(libs: list[Library]) -> LinkSpec:
    """Aggregate the native requirements of `libs`, de-duplicated, order preserved."""
    headers: list[str] = []
    include_dirs: list[Path] = []
    static_libs: list[Path] = []
    for lib in libs:
        for h in lib.header_names():
            if h not in headers:
                headers.append(h)
        for d in lib.include_dirs():
            if d not in include_dirs:
                include_dirs.append(d)
        for s in lib.static_libs():
            if s not in static_libs:
                static_libs.append(s)
    return LinkSpec(tuple(headers), tuple(include_dirs), tuple(static_libs))


def namespace_index(libraries: list[Library]) -> dict[str, Library]:
    """Map each owned namespace to its library; error if two libraries claim one."""
    index: dict[str, Library] = {}
    for lib in libraries:
        for ns in lib.namespaces:
            if ns in index and index[ns] is not lib:
                raise LibraryError(
                    f"namespace '{ns}' is declared by two libraries: "
                    f"'{index[ns].manifest.name}' and '{lib.manifest.name}'")
            index[ns] = lib
    return index


# ── Search path ──────────────────────────────────────────────────────────────

def _env_paths() -> list[Path]:
    raw = os.environ.get("YAFL_PATH", "")
    return [Path(p) for p in raw.split(os.pathsep) if p]


def _default_install_path() -> Path | None:
    """`${prefix}/lib/yafl`, derived from the installed binary at `${prefix}/bin/yafl`.
    Only meaningful for a frozen (PyInstaller) build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent / "lib" / "yafl"
    return None


def search_paths(extra: list[str] | None = None) -> list[Path]:
    """Library search path, highest precedence first: `--lib-path` flags, then
    `YAFL_PATH`, then the default install location."""
    paths: list[Path] = [Path(p) for p in (extra or [])]
    paths += _env_paths()
    default = _default_install_path()
    if default is not None:
        paths.append(default)
    return paths


# ── Dev fallback: the build-tree System library ───────────────────────────────────

_THIS_DIR = Path(__file__).resolve().parent          # .../compiler
_REPO_ROOT = _THIS_DIR.parent                         # repo root
_STDLIB_DIR = _THIS_DIR / "stdlib"
_YAFLLIB_DIR = _REPO_ROOT / "yafllib"


def _find_dev_static_lib() -> Path | None:
    """Locate a built `libyafl.a`. `YAFL_LIBYAFL_A` (set by the CMake test target)
    points at a specific archive; otherwise search the yafllib build tree."""
    env = os.environ.get("YAFL_LIBYAFL_A")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    candidates = sorted(_YAFLLIB_DIR.glob("build/**/libyafl.a"))
    return candidates[0] if candidates else None


def dev_system_library() -> Library | None:
    """When running un-installed (dev/test), synthesise the System library from the
    build-tree stdlib sources plus yafllib's header and built static archive. Returns
    None if the pieces aren't present (e.g. yafllib not built)."""
    if not _STDLIB_DIR.is_dir() or not (_YAFLLIB_DIR / "yafl.h").is_file():
        return None
    static = _find_dev_static_lib()
    if static is None:
        return None
    sources = [SourceFile(p.name, p.read_text(encoding="utf-8"))
               for p in sorted(_STDLIB_DIR.glob("*.yafl"))]
    namespaces = sorted({m.group(1).strip()
                         for src in sources
                         for m in re.finditer(r"(?m)^namespace\s+(.+?)\s*$", src.content)})
    manifest = Manifest(name="system", namespaces=tuple(namespaces) or ("System",),
                        headers=("yafl.h",), static_libs=("libyafl.a",))
    return Library(
        manifest=manifest,
        root=_STDLIB_DIR,
        _explicit_sources=tuple(sources),
        _explicit_includes=(_YAFLLIB_DIR,),
        _explicit_static=(static,),
    )


def _scan_namespaces(yafl_files: list[Path]) -> tuple[str, ...]:
    return tuple(sorted({m.group(1).strip()
                         for f in yafl_files
                         for m in re.finditer(r"(?m)^namespace\s+(.+?)\s*$", f.read_text(encoding="utf-8"))}))


def package_system_library(dest_yl: Path, stdlib_dir: Path, header: Path, static_lib: Path) -> None:
    """Build the self-contained System library as a single `.yl` zip at `dest_yl`:
    a generated `yafl.toml` (namespaces scanned from the sources), the stdlib
    `.yafl` sources, and `yafl.h` + `libyafl.a`. Installed as one file
    (`lib/yafl/system.yl`) and discovered like any other `.yl` library."""
    dest_yl = Path(dest_yl)
    dest_yl.parent.mkdir(parents=True, exist_ok=True)
    sources = sorted(Path(stdlib_dir).glob("*.yafl"))
    namespaces = _scan_namespaces(sources) or ("System",)
    ns_list = ", ".join(f'"{n}"' for n in namespaces)
    manifest = (f'name = "system"\nnamespaces = [{ns_list}]\n'
                f'headers = ["yafl.h"]\nstatic_libs = ["libyafl.a"]\n')
    with zipfile.ZipFile(dest_yl, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST_NAME, manifest)
        for src in sources:
            z.write(src, src.name)
        z.write(header, "yafl.h")
        z.write(static_lib, "libyafl.a")


def available_libraries(extra_paths: list[str] | None = None) -> list[Library]:
    """All discoverable libraries, including the build-tree dev System fallback when
    no installed System library is found on the path."""
    libs = discover_libraries(search_paths(extra_paths))
    owned = {ns for lib in libs for ns in lib.namespaces}
    if "System" not in owned:
        dev = dev_system_library()
        if dev is not None:
            libs.append(dev)
    return libs


def _main(argv: list[str]) -> int:
    """Small CLI used by the build to package the System library:
        python libraries.py package-system DEST.yl STDLIB_DIR HEADER STATIC_LIB"""
    if len(argv) == 6 and argv[1] == "package-system":
        _, _, dest, stdlib_dir, header, static_lib = argv
        package_system_library(Path(dest), Path(stdlib_dir), Path(header), Path(static_lib))
        return 0
    print("usage: libraries.py package-system DEST.yl STDLIB_DIR HEADER STATIC_LIB", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
