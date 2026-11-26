from pathlib import Path


def verify_migrations(source: Path, bundled: Path) -> None:
    def files(root: Path, pattern: str) -> dict[str, bytes]:
        result = {}
        for path in root.rglob(pattern):
            if path.is_symlink() or path.is_junction():
                raise ValueError("Unexpected link in migration files")
            if path.is_file():
                result[path.relative_to(root).as_posix()] = path.read_bytes()
        return result

    expected = files(source, "*.py")
    actual = files(bundled, "*")
    if not expected or expected != actual:
        raise ValueError("Packaged migration files differ from source")


def verify_system_runtime(root: Path) -> None:
    for path in root.rglob("*"):
        name = path.name.casefold()
        if path.is_file() and (name == "ucrtbase.dll" or name.startswith(("api-ms-win-crt-", "api-ms-win-core-"))):
            raise ValueError("Unexpected application-local Windows system runtime")
