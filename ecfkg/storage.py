"""Atomic local snapshots. Engineering data and screen layout are separate files."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def workspace() -> Path:
    return Path(os.environ.get("ECFKG_GRAPH_STORE", ROOT / "data/workspace"))


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value, backup=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        atomic_json(path.with_suffix(path.suffix + ".bak"), read_json(path), backup=False)
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def store_lock(root: Path):
    """OS-released advisory lock; a crashed process cannot leave a stale held lock."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a+b") as f:
        f.seek(0, 2)
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                f.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError("Another editor is saving. Retry shortly.") from None
                time.sleep(.05)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def revision_path(root: Path, version: str) -> Path:
    if not re.fullmatch(r"v\d{6}-[a-f0-9]{12}", version):
        raise ValueError("Invalid revision identifier")
    return root / "revisions" / (version + ".json")


def published(root: Path | None = None):
    root = root or workspace()
    pointer = root / "current.json"
    if not pointer.exists():
        return None
    manifest = read_json(pointer)
    revision = read_json(revision_path(root, manifest["version"]))
    if digest(revision) != manifest["sha256"] or revision["version"] != manifest["version"]:
        raise ValueError("Published graph integrity check failed. Restore a verified revision; no silent fallback ran.")
    return revision
