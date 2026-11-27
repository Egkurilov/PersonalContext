import json
from importlib.metadata import distributions
from pathlib import Path


def main():
    records = []
    for distribution in distributions():
        metadata = distribution.metadata
        classifiers = [value for value in metadata.get_all("Classifier", []) if value.startswith("License ::")]
        records.append({
            "name": metadata["Name"],
            "version": metadata["Version"],
            "license_expression": metadata.get("License-Expression"),
            "license": metadata.get("License"),
            "license_classifiers": classifiers,
        })
    records.sort(key=lambda record: record["name"].lower())
    Path("dist/python-licenses.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
