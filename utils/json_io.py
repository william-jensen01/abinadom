"""
Stable JSON writing for committed data files.

Every file `fetch` writes goes through write_json(), so running it twice with
nothing changed upstream leaves `git diff` empty, and a real upstream change
shows up as only the lines that changed.
"""

import json
import os
from typing import Dict, Iterable, List


def write_json(path: str, records: Iterable[Dict], key: str = "uri") -> None:
    """Write records sorted by `key`, UTF-8, unescaped, with a trailing newline."""
    records = sorted(records, key=lambda r: r[key])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_json(path: str) -> List[Dict]:
    """Read a JSON list; a missing file reads as empty."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_by_key(existing: Iterable[Dict], new: Iterable[Dict], key: str = "uri") -> List[Dict]:
    """Merge records by `key`: new records are added, existing ones replaced."""
    merged = {r[key]: r for r in existing}
    for r in new:
        merged[r[key]] = r
    return list(merged.values())
