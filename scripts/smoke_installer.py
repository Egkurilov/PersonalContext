import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path
from urllib.request import urlopen

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{13A96698-E7A8-4BA4-AD40-012D57D437C1}_is1"


def main():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY):
            raise RuntimeError("PersonalContext is already installed for this user; installer smoke skipped")
    except FileNotFoundError:
        pass
    setup = Path("dist/PersonalContext-Setup.exe").resolve()
    with tempfile.TemporaryDirectory(prefix="personalcontext-install-") as directory:
        install_dir = Path(directory) / "app"
        command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS", f"/DIR={install_dir}"]
        try:
            subprocess.run(command, check=True, timeout=120)
            subprocess.run([sys.executable, "scripts/smoke_frozen.py", str(install_dir / "PersonalContext.exe")], check=True, timeout=90)
            env = os.environ.copy()
            env["LOCALAPPDATA"] = str(Path(directory) / "runtime")
            running = subprocess.Popen([str(install_dir / "PersonalContext.exe")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if running.poll() is not None:
                        raise RuntimeError("Installed application exited before readiness")
                    try:
                        with urlopen("http://127.0.0.1:17890/readyz", timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.25)
                else:
                    raise RuntimeError("Installed application did not become ready")
                subprocess.run(command + ["/CLOSEAPPLICATIONS"], env=env, check=True, timeout=120)
                running.wait(timeout=10)
            finally:
                if running.poll() is None:
                    running.terminate()
                    running.wait(timeout=10)
            assert (install_dir / "PersonalContext.exe").is_file()
        finally:
            uninstaller = install_dir / "unins000.exe"
            if uninstaller.exists():
                subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True, timeout=120)
        assert not (install_dir / "PersonalContext.exe").exists()
    print("Per-user install, reinstall and silent uninstall passed")


if __name__ == "__main__":
    main()
