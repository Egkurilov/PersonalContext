from pathlib import Path


def normalize(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise ValueError("Unexpected link in packaged text")
    content = path.read_bytes()
    content.decode("utf-8")
    normalized = content.replace(b"\r\n", b"\n")
    if normalized != content:
        path.write_bytes(normalized)


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "dist/PersonalContext/_internal"
    html = root / "frontend/dist/index.html"
    schemas = list((root / "schemas").rglob("*.json"))
    migrations = list((root / "personalcontext/migrations").rglob("*.py"))
    if not html.is_file() or not schemas or not migrations:
        raise RuntimeError("Packaged text inputs missing")
    for path in [html, *schemas, *migrations]:
        normalize(path)


if __name__ == "__main__":
    main()
