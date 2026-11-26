import re
from pathlib import PurePosixPath


def build_report(revision: str, bundle: dict[str, bytes | None], installer: bytes) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or len(installer) != 32:
        raise ValueError("Invalid reproducibility report identity")
    entries = {}
    for name, digest in sorted(bundle.items()):
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                or any(ord(character) < 32 or ord(character) == 127 for character in name)):
            raise ValueError("Unsafe reproducibility report path")
        if digest is not None and len(digest) != 32:
            raise ValueError("Invalid reproducibility report digest")
        entries[name] = None if digest is None else digest.hex()
    return {"format_version": 1, "revision": revision, "bundle": entries, "installer_sha256": installer.hex()}
