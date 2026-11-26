import re
import sys
from pathlib import Path


def require_pinned_version(pin: str, actual: tuple[int, ...]) -> None:
    if not re.fullmatch(r"3\.12\.[0-9]+", pin):
        raise ValueError("Invalid Python version pin")
    if actual[:3] != tuple(int(part) for part in pin.split(".")):
        raise ValueError("Python interpreter does not match .python-version")


if __name__ == "__main__":
    require_pinned_version(
        (Path(__file__).resolve().parent.parent / ".python-version").read_text(encoding="ascii").strip(),
        tuple(sys.version_info[:3]),
    )
