import subprocess
import tempfile
import unittest
from pathlib import Path


class IndexGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        self.directory.cleanup()

    def guard(self):
        from scripts.check_index import check_index
        return check_index(self.root)

    def test_rejects_synthetic_token_from_staged_content(self):
        path = self.root / "sample.txt"
        path.write_text("api_key = '" + "ghp_" + "Z9x4" * 9 + "'\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "sample.txt"], check=True)
        path.write_text("working copy is clean\n", encoding="utf-8")
        self.assertFalse(self.guard())

    def test_rejects_forced_export_and_accepts_synthetic_source(self):
        path = self.root / "exports" / "events.json"
        path.parent.mkdir()
        path.write_text("synthetic", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "exports/events.json"], check=True)
        self.assertFalse(self.guard())
        subprocess.run(["git", "-C", str(self.root), "rm", "--cached", "-q", "exports/events.json"], check=True)
        (self.root / "source.txt").write_text("synthetic source\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "source.txt"], check=True)
        self.assertTrue(self.guard())

    def test_precommit_blocks_forced_export(self):
        import shlex
        import shutil
        import sys

        hook_dir = self.root / ".githooks"
        hook_dir.mkdir()
        source_root = Path(__file__).resolve().parent.parent
        shutil.copyfile(source_root / ".githooks/pre-commit", hook_dir / "pre-commit")
        (hook_dir / "pre-commit").chmod(0o755)
        script_dir = self.root / "scripts"
        script_dir.mkdir()
        shutil.copyfile(source_root / "scripts/check_index.py", script_dir / "check_index.py")
        interpreter = self.root / ".venv/bin/python"
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text("#!/bin/sh\nexec " + shlex.quote(Path(sys.executable).as_posix()) + ' "$@"\n', encoding="utf-8")
        interpreter.chmod(0o755)
        subprocess.run(["git", "-C", str(self.root), "config", "core.hooksPath", ".githooks"], check=True)
        export = self.root / "exports/fixture.json"
        export.parent.mkdir()
        export.write_text("synthetic", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "exports/fixture.json"], check=True)
        result = subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"],
            capture_output=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"protected data path", result.stderr)



    def test_scans_lock_files_and_rejects_allowlist_marker(self):
        path = self.root / "package-lock.json"
        path.write_text('{"token":"' + "ghp_" + "Z9x4" * 9 + '"} # pragma: allowlist secret\n', encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "package-lock.json"], check=True)
        self.assertFalse(self.guard())

    def test_scans_index_after_lock_file_when_worktree_file_is_absent(self):
        (self.root / "package-lock.json").write_text('{}\n', encoding="utf-8")
        path = self.root / "z.txt"
        path.write_text("api_key='" + "ghp_" + "Z9x4" * 9 + "'\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "package-lock.json", "z.txt"], check=True)
        path.unlink()
        self.assertFalse(self.guard())
