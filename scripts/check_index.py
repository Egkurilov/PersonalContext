import subprocess
import sys
from pathlib import Path, PurePosixPath

from detect_secrets.core.scan import scan_diff
from detect_secrets.settings import default_settings


def forbidden_path(name: str) -> bool:
    if "\n" in name or "\r" in name:
        return True
    path = PurePosixPath(name.lower())
    if set(path.parts) & {"exports", "spool", "keys"}:
        return True
    if path.name.startswith(".env") and path.name != ".env.example":
        return True
    return path.name.endswith((".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite-wal", ".sqlite-shm", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".dpapi", ".p12", ".pfx", ".key"))


def contains_secret(name: str, text: str) -> bool:
    lines = text.splitlines()
    patch = f"--- /dev/null\n+++ b/{name}\n@@ -0,0 +1,{len(lines)} @@\n"
    patch += "".join("+" + line + "\n" for line in lines)
    with default_settings() as settings:
        settings.disable_filters(
            "detect_secrets.filters.common.is_invalid_file",
            "detect_secrets.filters.allowlist.is_line_allowlisted",
        )
        if name.lower().endswith((".lock", "package-lock.json")):
            settings.disable_filters("detect_secrets.filters.heuristic.is_lock_file")
            settings.disable_plugins("Base64HighEntropyString", "HexHighEntropyString")
        return next(scan_diff(patch), None) is not None


def check_index(root: Path) -> bool:
    listing = subprocess.run(["git", "ls-files", "--cached", "-z"], cwd=root, check=True, capture_output=True).stdout
    names = [name.decode("utf-8", errors="surrogateescape") for name in listing.split(b"\0") if name]
    if any(forbidden_path(name) for name in names):
        print("Commit rejected: protected data path is staged.", file=sys.stderr)
        return False
    for name in names:
        blob = subprocess.run(["git", "show", ":" + name], cwd=root, check=True, capture_output=True).stdout
        if len(blob) > 8 * 1024 * 1024:
            print("Commit rejected: staged file exceeds scanner size limit.", file=sys.stderr)
            return False
        if b"\0" in blob:
            continue
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if contains_secret(name, text):
            print("Commit rejected: a possible secret was detected in staged content.", file=sys.stderr)
            return False
    return True


def main() -> int:
    root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip())
    return 0 if check_index(root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
