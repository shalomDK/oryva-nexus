"""Orchestration: generate clean baseline -> validate -> plan -> inject labelled cases -> plan -> validate ->
evaluate -> export.  Also: validate/evaluate an existing export, and the reproducibility harness."""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

from . import schema
from .config import load_policy, load_profile
from .datagen import generate_baseline
from .evaluate import distribution_report, evaluate
from .export import export_all, sha256
from .frames import read_csv
from .inject import inject, n_reserved
from .planning import run_plan
from .validate import validate


def _log(msg, quiet):
    if not quiet:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def build(profile: str, out_dir: Path | None, overrides=None, command: str = "", quiet=False, compress="auto"):
    P = load_profile(profile, overrides)
    policy = load_policy()
    reserve = n_reserved(P)
    _log(f"generating clean baseline ({P['name']}, seed {P['seed']})", quiet)
    T0, meta = generate_baseline(P, reserve)
    _log("planning on clean baseline + validating it (must be 100% clean)", quiet)
    out0, ctx0 = run_plan(T0, policy, P["seed"], P["name"])
    rep0 = validate({**T0, **out0}, None)
    if rep0.unexpected_failures or any(r["failed"] for r in rep0.rows if r["kind"] == "labelled"):
        bad = [r for r in rep0.rows if r["failed"]]
        raise RuntimeError(f"clean baseline is not clean: {bad[:5]}")
    _log(f"baseline clean: {len(rep0.rows)} checks, {len(out0['Shortage'])} shortages; injecting labelled edge cases", quiet)
    T1, gt = inject(T0, out0, P)
    _log("planning on injected data", quiet)
    out1, ctx1 = run_plan(T1, policy, P["seed"], P["name"])
    _log("validating + evaluating against ground truth", quiet)
    rep = validate({**T1, **out1}, P)
    ev = evaluate(out1 | {"Shortage": out1["Shortage"]}, gt, rep) if False else evaluate({**T1, **out1}, gt, rep)
    dist = distribution_report(T1)
    meta["baseline_checks_clean"] = len(rep0.rows)
    manifest = None
    if out_dir is not None:
        _log(f"exporting to {out_dir}", quiet)
        manifest = export_all(T1, out1, gt, rep, ev, dist, P, meta, out_dir, command, compress)
    return {"P": P, "T": T1, "out": out1, "gt": gt, "report": rep, "eval": ev, "meta": meta, "manifest": manifest, "baseline_report": rep0}


def load_export(data_dir: Path) -> dict:
    data_dir = Path(data_dir)
    T = {}
    for name in schema.ALL_TABLES:
        p = data_dir / "csv" / f"{name}.csv"
        if not p.exists():
            p = data_dir / "csv" / f"{name}.csv.gz"
        T[name] = read_csv(name, p)
    return T


def validate_export(data_dir: Path):
    data_dir = Path(data_dir)
    man = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    T = load_export(data_dir)
    rep = validate(T, man["parameters"])
    gtp = data_dir / "ground_truth" / "ground_truth.csv"
    gt = pd.read_csv(gtp, keep_default_na=False, na_values=[""]) if gtp.exists() else None
    ev = evaluate(T, gt, rep) if gt is not None else None
    return rep, ev, man


def verify_checksums(data_dir: Path) -> list:
    data_dir = Path(data_dir)
    man = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    return [f for f, m in man["files"].items() if not (data_dir / f).exists() or sha256(data_dir / f) != m["sha256"]]


def reproducibility(profile: str, work: Path, overrides=None, quiet=False) -> dict:
    work = Path(work)
    runs = []
    for i in (1, 2):
        d = work / f"run{i}"
        if d.exists():
            shutil.rmtree(d)
        build(profile, d, overrides, command=f"oryva generate --profile {profile}", quiet=quiet)
        runs.append(json.loads((d / "manifest.json").read_text(encoding="utf-8")))
    a, b = runs
    rows = []
    for f in sorted(a["files"]):
        fa, fb = a["files"][f], b["files"].get(f)
        rows.append({"file": f, "rows_run1": fa.get("rows"), "rows_run2": fb.get("rows") if fb else None,
                     "sha256_run1": fa["sha256"], "sha256_run2": fb["sha256"] if fb else None,
                     "match": bool(fb and fa["sha256"] == fb["sha256"] and fa.get("rows") == fb.get("rows"))})
    ok = all(r["match"] for r in rows) and set(a["files"]) == set(b["files"])
    P = a["parameters"]
    md = ["# Reproducibility report", "", f"Profile `{a['profile']}`, seed `{a['seed']}`; generated twice with the same seed and compared "
          "row counts and SHA-256 checksums of every exported file.", "", f"**Result: {'PASS - all files identical' if ok else 'FAIL'}** "
          f"({sum(r['match'] for r in rows)}/{len(rows)} files match)", "",
          "| File | Rows (run1/run2) | SHA-256 (run1) | Match |", "|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['file']} | {r['rows_run1']}/{r['rows_run2']} | `{r['sha256_run1'][:16]}...` | {'yes' if r['match'] else 'NO'} |")
    md += ["", "Row counts per table: " + ", ".join(f"{k}={v}" for k, v in a["table_row_counts"].items())]
    result = {"ok": ok, "files": len(rows), "mismatches": [r["file"] for r in rows if not r["match"]], "report_md": "\n".join(md) + "\n", "parameters": P, "table_row_counts": a["table_row_counts"]}
    return result

