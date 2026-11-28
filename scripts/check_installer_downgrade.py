import winreg
from pathlib import Path

from installer_process import run_installer


def verify_downgrade_guard(command: list[str], uninstall_key: str, install_dir: Path) -> None:
    executable = install_dir / "PersonalContext.exe"
    original = executable.read_bytes()
    def set_version(value: str, value_type: int) -> None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, uninstall_key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayVersion", 0, value_type, value)

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, uninstall_key, 0, winreg.KEY_QUERY_VALUE) as key:
        version, value_type = winreg.QueryValueEx(key, "DisplayVersion")
    try:
        set_version("0.0.1", winreg.REG_SZ)
        run_installer(command, check=True)
        for synthetic_version in ("99.0.0", "invalid"):
            set_version(synthetic_version, winreg.REG_SZ)
            result = run_installer(command, check=False)
            if result.returncode == 0 or executable.read_bytes() != original:
                raise RuntimeError("Installer did not reject unsafe version replacement")
    finally:
        set_version(version, value_type)
    print("Installer accepted an older version and rejected newer or invalid versions")
