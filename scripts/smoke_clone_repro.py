import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from repro_report import build_report
from smoke_frozen_repro import manifest


def run(stage: str, command: list[str], cwd: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=240, check=False)
    if result.returncode:
        raise RuntimeError(f"{stage} failed with exit code {result.returncode}")
    return result.stdout.strip()


def main() -> None:
    repository = Path(__file__).resolve().parent.parent
    compiler = Path(sys.argv[1]).resolve(strict=True)
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    npm = shutil.which("npm")
    if not shell or not npm:
        raise RuntimeError("PowerShell and npm are required")
    environment = os.environ.copy()
    environment.update(UV_OFFLINE="1", NPM_CONFIG_OFFLINE="true", NPM_CONFIG_AUDIT="false")
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "NODE_PATH"):
        environment.pop(name, None)
    run("Python version", [sys.executable, str(repository / "scripts/check_python.py")], repository, environment)
    run("frontend versions", [sys.executable, str(repository / "scripts/check_frontend.py")], repository, environment)
    commit = run("revision", ["git", "rev-parse", "HEAD"], repository, environment)
    with tempfile.TemporaryDirectory(prefix="personalcontext-clone-repro-") as directory:
        root = Path(directory).resolve()
        if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError("Unexpected temporary directory")
        results = []
        for index in (1, 2):
            print(f"Building clone {index} of revision {commit[:12]}", flush=True)
            clone = root / f"clone-{index}"
            run("clone", ["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(repository), str(clone)], root, environment)
            run("checkout", ["git", "checkout", "--quiet", "--detach", commit], clone, environment)
            if run("revision", ["git", "rev-parse", "HEAD"], clone, environment) != commit:
                raise RuntimeError("Clone revision mismatch")
            run("Python setup", [shell, "-NoProfile", "-File", str(clone / "scripts/uv.ps1"), "sync", "--locked"], clone, environment)
            run("frontend install", [npm, "ci", "--prefix", "frontend"], clone, environment)
            run("frontend build", [npm, "run", "build", "--prefix", "frontend"], clone, environment)
            run("package", [shell, "-NoProfile", "-File", str(clone / "scripts/package.ps1")], clone, environment)
            bundle = manifest(clone / "dist/PersonalContext")
            run("installer", [str(compiler), "/Q", str(clone / "installer/PersonalContext.iss")], clone, environment)
            with (clone / "dist/PersonalContext-Setup.exe").open("rb") as stream:
                results.append((bundle, hashlib.file_digest(stream, "sha256").digest()))
        left, right = results
        if left != right:
            changed = sorted(set(left[0]) ^ set(right[0]) | {key for key in left[0].keys() & right[0].keys() if left[0][key] != right[0][key]})
            raise RuntimeError(f"Clone outputs differ; installer_equal={left[1] == right[1]}; entries={changed[:10]}")
        report = build_report(commit, left[0], left[1])
        output = repository / "dist/repro-manifest.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        with output.open("rb") as stream:
            print(f"Reproducibility report SHA-256: {hashlib.file_digest(stream, 'sha256').hexdigest()}")
        print(f"Installer SHA-256: {left[1].hex()}")
        print(f"Separate clones: {len(left[0])} bundle entries and installer bytes identical")


if __name__ == "__main__":
    main()
