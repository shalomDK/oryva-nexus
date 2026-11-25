"""DataFrame <-> schema helpers: canonical dtypes, CSV/JSON I/O (deterministic bytes)."""
from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import T


def coerce(name: str, df: pd.DataFrame) -> pd.DataFrame:
    t = T[name]
    missing = [c for c in t.cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")
    out = pd.DataFrame(index=range(len(df)))
    for f in t.fields:
        col = df[f.name].reset_index(drop=True)
        if f.typ in ("str", "date"):
            out[f.name] = pd.Series([None if (v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA) else str(v)
                                     for v in col], dtype=object)
        elif f.typ == "int":
            out[f.name] = pd.to_numeric(col).astype("Int64" if not f.req else "int64")
        else:
            out[f.name] = pd.to_numeric(col).astype("float64")
    return out


def sort_pk(name: str, df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(T[name].pk, kind="mergesort").reset_index(drop=True)


def finalize(name: str, df: pd.DataFrame) -> pd.DataFrame:
    return sort_pk(name, coerce(name, df))


def csv_bytes(name: str, df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, lineterminator="\n", float_format="%.4f", na_rep="").encode("utf-8")


def write_csv(name: str, df: pd.DataFrame, path: Path, gz: bool = False) -> Path:
    data = csv_bytes(name, df)
    if gz:
        path = Path(str(path) + ".gz")
        with open(path, "wb") as fh:
            with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as g:
                g.write(data)
    else:
        path.write_bytes(data)
    return path


def read_csv(name: str, path: Path) -> pd.DataFrame:
    t = T[name]
    dtype = {f.name: ("string" if f.typ in ("str", "date") else None) for f in t.fields}
    dtype = {k: v for k, v in dtype.items() if v}
    df = pd.read_csv(path, dtype=dtype, keep_default_na=False, na_values=[""])
    return coerce(name, df)


def write_json(name: str, df: pd.DataFrame, path: Path, gz: bool = False) -> Path:
    data = df.to_json(orient="records", double_precision=4).encode("utf-8") + b"\n"
    if gz:
        path = Path(str(path) + ".gz")
        with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as g:
            g.write(data)
    else:
        path.write_bytes(data)
    return path
