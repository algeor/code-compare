"""One-time migration that removes derived bucket fields from tabular research data."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path


DERIVED_FIELDS = {
    "label",
    "suggested_label",
    "expected_percentage_bucket",
    "predicted_label",
    "predicted_percentage_bucket",
}


def migrate_jsonl(path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with path.open(encoding="utf-8") as source, os.fdopen(descriptor, "w", encoding="utf-8") as target:
            for line in source:
                if not line.strip():
                    continue
                row = json.loads(line)
                for field in DERIVED_FIELDS:
                    row.pop(field, None)
                target.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def migrate_csv(path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with path.open(newline="", encoding="utf-8") as source, os.fdopen(
            descriptor, "w", newline="", encoding="utf-8"
        ) as target:
            reader = csv.DictReader(source)
            fieldnames = [field for field in reader.fieldnames or [] if field not in DERIVED_FIELDS]
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                writer.writerow({field: row[field] for field in fieldnames})
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        if path.suffix == ".jsonl":
            migrate_jsonl(path)
        elif path.suffix == ".csv":
            migrate_csv(path)
        else:
            raise ValueError(f"Unsupported file type: {path}")


if __name__ == "__main__":
    main()
