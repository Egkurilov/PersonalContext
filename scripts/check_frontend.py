import re
import shutil
import subprocess
from pathlib import Path


def require_versions(expected_node: str, expected_npm: str, node: str, npm: str) -> None:
    if not all(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) for value in (expected_node, expected_npm)):
        raise ValueError("Invalid frontend version pin")
    if node != f"v{expected_node}" or npm != expected_npm:
        raise ValueError("Node.js or npm does not match the pinned frontend toolchain")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    versions = []
    for command in ("node", "npm"):
        executable = shutil.which(command)
        if executable is None:
            raise RuntimeError(f"Required frontend tool is missing: {command}")
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True, timeout=15)
        versions.append(result.stdout.strip())
    require_versions((root / ".node-version").read_text().strip(), (root / ".npm-version").read_text().strip(), *versions)


if __name__ == "__main__":
    main()
