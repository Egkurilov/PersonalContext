import os
import tempfile
import zipfile
from pathlib import Path


def normalize(path: Path) -> None:
    temporary: Path | None = None
    try:
        with zipfile.ZipFile(path) as source:
            entries = source.infolist()
            if len({entry.filename for entry in entries}) != len(entries):
                raise ValueError("Base archive contains duplicate names")
            if any(entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits for entry in entries):
                raise ValueError("Unexpected base archive format")
            with tempfile.NamedTemporaryFile(prefix="base-library-", suffix=".zip", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
            with zipfile.ZipFile(temporary, "w") as target:
                target.comment = source.comment
                for entry in sorted(entries, key=lambda item: item.filename):
                    content = source.read(entry)
                    target.writestr(entry, content)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    normalize(Path(__file__).resolve().parent.parent / "dist/PersonalContext/_internal/base_library.zip")
