"""Read and freeze case manifests without importing evaluation executors."""

import json
from pathlib import Path

from file_utils import sha


def read(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("empty or duplicate case IDs")
    return rows


def write_rows(path, rows):
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def manifest(path, output):
    rows = read(path)
    for row in rows:
        image = Path(row["image"])
        image = image if image.is_absolute() else Path(path).parent / image
        if sha(image) != row["sha256"]:
            raise ValueError("image changed: " + row["id"])
        row["image"] = str(image.resolve())
    write_rows(output, rows)
    return rows
