import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> bytes:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def main() -> None:
    repository = Path(__file__).resolve().parent.parent
    compiler = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="personalcontext-repro-") as directory:
        root = Path(directory)
        (root / "installer").mkdir()
        (root / "dist").mkdir()
        for name in ("PersonalContext.iss", "VersionGuard.iss"):
            shutil.copy2(repository / "installer" / name, root / "installer" / name)
        shutil.copytree(repository / "dist/PersonalContext", root / "dist/PersonalContext")
        hashes = []
        for index in range(2):
            output = root / f"output-{index}"
            output.mkdir()
            subprocess.run([str(compiler), "/Q", f"/O{output}", str(root / "installer/PersonalContext.iss")],
                           capture_output=True, check=True, timeout=180)
            hashes.append(sha256(output / "PersonalContext-Setup.exe"))
            source = root / "dist/PersonalContext/_internal/frontend/dist/index.html"
            stat = source.stat()
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns - 37 * 60 * 1_000_000_000))
            if source.stat().st_mtime_ns == stat.st_mtime_ns:
                raise RuntimeError("Input timestamp did not change")
        if hashes[0] != hashes[1]:
            raise RuntimeError("Installer changed after an input timestamp change")
    print("Installer bytes unchanged by input timestamp change")


if __name__ == "__main__":
    main()
