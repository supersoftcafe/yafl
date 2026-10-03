"""This process's private temporary folder.

On first use a uniquely named sub-folder of the host temp directory is created,
`<gettempdir()>/yafl-<pid>-XXXXXXXX` (mode 0700), and every later call returns
the same path. Nothing else shares it, so what goes in needs no keying, locking
or invalidation. The folder and everything in it is deleted when the process
exits.

The Python counterpart of the runtime's `yafllib/tempdir.c` (`System::tempDir`
in YAFL): same base-directory lookup, same naming, same lifetime. Like
`libraries.py` it imports nothing from the compiler.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()
_path: Path | None = None
_owner: int | None = None


def process_temp_dir() -> Path:
    """The folder's path, creating it (and registering its deletion) on first call."""
    global _path, _owner
    with _lock:
        if _path is None or _owner != os.getpid():
            # A fork child gets its own folder rather than writing into its
            # parent's, which the parent deletes on its own schedule.
            _path = Path(tempfile.mkdtemp(prefix=f"yafl-{os.getpid()}-"))
            _owner = os.getpid()
            atexit.register(_cleanup, _path, _owner)
        return _path


def _cleanup(path: Path, owner: int) -> None:
    # A fork child inherits the parent's atexit handlers; only the creator deletes.
    if os.getpid() == owner:
        shutil.rmtree(path, ignore_errors=True)


def cleanup() -> None:
    """Delete the folder now (it is recreated if used again). Idempotent."""
    global _path, _owner
    with _lock:
        if _path is not None and _owner == os.getpid():
            shutil.rmtree(_path, ignore_errors=True)
        _path = _owner = None
