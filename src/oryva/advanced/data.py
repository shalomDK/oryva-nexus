"""Dataset access shared by the application, advanced modules and tests (read-only)."""
from __future__ import annotations

import json
from pathlib import Path

from .. import schema
from ..config import load_policy
from ..frames import read_csv


def _path(d: Path, name: str) -> Path:
    p = d / "csv" / f"{name}.csv"
    return p if p.exists() else d / "csv" / f"{name}.csv.gz"


def load_dataset(data_dir) -> dict:
    """Return {'T': input tables, 'out': planning outputs, 'manifest': dict, 'policy': dict, 'dir': Path}."""
    d = Path(data_dir)
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    T = {n: read_csv(n, _path(d, n)) for n in schema.INPUT_TABLES}
    out = {n: read_csv(n, _path(d, n)) for n in schema.OUTPUT_TABLES}
    return {"T": T, "out": out, "manifest": man, "policy": load_policy(), "dir": d, "as_of": str(T["Inventory"]["as_of_date"].iloc[0])}
