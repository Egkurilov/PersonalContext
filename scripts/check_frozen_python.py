import hashlib
import sys
from pathlib import Path

from check_python import require_pinned_version


def compare_runtime(bundled: Path, runtime: Path) -> None:
    def digest(path: Path) -> bytes:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").digest()

    if digest(bundled) != digest(runtime):
        raise RuntimeError("Packaged Python DLL differs from the pinned build interpreter")


def verify_frozen_python(executable: Path) -> None:
    pin = (Path(__file__).resolve().parent.parent / ".python-version").read_text(encoding="ascii").strip()
    require_pinned_version(pin, tuple(sys.version_info[:3]))
    compare_runtime(executable.parent / "_internal/python312.dll", Path(sys.base_prefix) / "python312.dll")
