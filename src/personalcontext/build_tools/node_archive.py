import hashlib
import zipfile
from pathlib import Path, PurePosixPath


def extract_verified(archive: Path, destination: Path, expected_root: str, checksum: str) -> None:
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
            raise ValueError("Node archive checksum mismatch")
    with zipfile.ZipFile(archive) as zipped:
        total = 0
        for member in zipped.infolist():
            name = member.filename
            parts = PurePosixPath(name).parts
            mode = (member.external_attr >> 16) & 0o170000
            if (not parts or parts[0] != expected_root or ".." in parts or "\\" in name
                    or ":" in name or name.startswith("/") or mode == 0o120000):
                raise ValueError("Unsafe Node archive member")
            total += member.file_size
            if total > 512 * 1024 * 1024:
                raise ValueError("Node archive is too large")
        zipped.extractall(destination)
