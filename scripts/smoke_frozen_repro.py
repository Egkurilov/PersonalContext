import hashlib
import shutil
import subprocess
import zipfile
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


def zip_entries(path: Path) -> list[tuple[str, int, int, int, tuple[int, ...], int]]:
    with zipfile.ZipFile(path) as archive:
        return [(item.filename, item.CRC, item.file_size, item.compress_type, item.date_time, item.external_attr)
                for item in archive.infolist()]


def zip_diagnostic(before: list[tuple[str, int, int, int, tuple[int, ...], int]],
                   after: list[tuple[str, int, int, int, tuple[int, ...], int]]) -> str:
    return (f"zip_metadata_equal={sorted(before) == sorted(after)}; "
            f"zip_order_equal={[item[0] for item in before] == [item[0] for item in after]}")


def main() -> None:
    repository = Path(__file__).resolve().parent.parent
    bundle = repository / "dist/PersonalContext"
    before = manifest(bundle)
    if not before or "PersonalContext.exe" not in before:
        raise RuntimeError("Frozen build missing")
    original_zip = zip_entries(bundle / "_internal/base_library.zip")
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not shell:
        raise RuntimeError("PowerShell is required for reproducibility smoke")
    subprocess.run([shell, "-NoProfile", "-File", str(repository / "scripts/package.ps1")],
                   cwd=repository, capture_output=True, check=True, timeout=240)
    after = manifest(bundle)
    if before != after:
        changed = sorted(set(before) ^ set(after) | {key for key in before.keys() & after.keys() if before[key] != after[key]})
        detail = ""
        if "_internal/base_library.zip" in changed:
            detail = "; " + zip_diagnostic(original_zip, zip_entries(bundle / "_internal/base_library.zip"))
        raise RuntimeError("Frozen build differs after a second packaging run: " + ", ".join(changed[:10]) + detail)
    print(f"Frozen build identical across two packaging runs: {len(before)} entries")


if __name__ == "__main__":
    main()
