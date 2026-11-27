import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

from check_frontend import require_versions

from personalcontext.build_tools.node_archive import extract_verified


def matches(node: str | None, npm: str | None, node_pin: str, npm_pin: str) -> bool:
    if node is None or npm is None:
        return False
    try:
        values = [subprocess.run([tool, "--version"], capture_output=True, text=True, check=True, timeout=15).stdout.strip()
                  for tool in (node, npm)]
        require_versions(node_pin, npm_pin, *values)
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return True


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    node_pin = (root / ".node-version").read_text(encoding="ascii").strip()
    npm_pin = (root / ".npm-version").read_text(encoding="ascii").strip()
    checksum = (root / ".node-sha256").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", node_pin) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Invalid Node distribution pin")
    if matches(shutil.which("node"), shutil.which("npm"), node_pin, npm_pin):
        print("__CURRENT__")
        return
    name = f"node-v{node_pin}-win-x64"
    cache = root / ".tools"
    cache.mkdir(exist_ok=True)
    if not cache.resolve().is_relative_to(root.resolve()):
        raise ValueError("Frontend tool directory leaves the workspace")
    target = cache / name
    if not target.exists():
        print("Preparing the pinned Node.js distribution", file=sys.stderr)
        with tempfile.TemporaryDirectory(prefix="node-download-", dir=cache) as directory:
            temporary = Path(directory)
            archive = temporary / "node.zip"
            with urlopen(f"https://nodejs.org/dist/v{node_pin}/{name}.zip", timeout=30) as response, archive.open("wb") as output:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 160 * 1024 * 1024:
                        raise ValueError("Node archive download is too large")
                    output.write(chunk)
            extract_verified(archive, temporary, name, checksum)
            (temporary / name).rename(target)
    if not target.resolve().is_relative_to(cache.resolve()):
        raise ValueError("Frontend tool directory leaves the cache")
    if not matches(str(target / "node.exe"), str(target / "npm.cmd"), node_pin, npm_pin):
        raise RuntimeError("Cached frontend tools do not match the pinned versions")
    print(target)


if __name__ == "__main__":
    main()
