import hashlib
import shutil
import subprocess
from pathlib import Path


def manifest(root: Path) -> dict[str, bytes | None]:
    result: dict[str, bytes | None] = {}
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        if path.is_symlink() or path.is_junction():
            raise ValueError("Unexpected link in frozen build")
        if path.is_dir():
            result[name] = None
        elif path.is_file():
            with path.open("rb") as stream:
                result[name] = hashlib.file_digest(stream, "sha256").digest()
        else:
            raise ValueError("Unexpected entry in frozen build")
    return result


def main() -> None:
    repository = Path(__file__).resolve().parent.parent
    bundle = repository / "dist/PersonalContext"
    before = manifest(bundle)
    if not before or "PersonalContext.exe" not in before:
        raise RuntimeError("Frozen build missing")
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not shell:
        raise RuntimeError("PowerShell is required for reproducibility smoke")
    subprocess.run([shell, "-NoProfile", "-File", str(repository / "scripts/package.ps1")],
                   cwd=repository, capture_output=True, check=True, timeout=240)
    if before != manifest(bundle):
        raise RuntimeError("Frozen build differs after a second packaging run")
    print(f"Frozen build identical across two packaging runs: {len(before)} entries")


if __name__ == "__main__":
    main()
