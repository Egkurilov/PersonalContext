from pathlib import Path

UNSHIPPED_LAUNCHER = b"../../Scripts/alembic.exe"


def prune(record: Path) -> None:
    lines = record.read_bytes().splitlines(keepends=True)
    kept = [line for line in lines if line.split(b",", 1)[0] != UNSHIPPED_LAUNCHER]
    if len(lines) - len(kept) != 1:
        raise ValueError("Unexpected Alembic launcher metadata")
    record.write_bytes(b"".join(kept))


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "dist/PersonalContext"
    if (root / "Scripts/alembic.exe").exists():
        raise RuntimeError("Alembic launcher is unexpectedly bundled")
    metadata = list((root / "_internal").glob("alembic-*.dist-info"))
    if len(metadata) != 1:
        raise RuntimeError("Expected exactly one Alembic metadata directory")
    prune(metadata[0] / "RECORD")


if __name__ == "__main__":
    main()
