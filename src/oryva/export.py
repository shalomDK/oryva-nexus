"""Deterministic exports: CSV (+gz for large tables), JSON, SQL seed, ground truth (separate folder),
data dictionary, validation summary, source manifest, manifest with SHA-256 checksums."""
from __future__ import annotations

import gzip
import hashlib
import json
import platform
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from . import schema
from .frames import csv_bytes, write_csv, write_json

GZ_ROWS = 100_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sql_val(v, typ):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return "NULL"
    if typ in ("str", "date"):
        return "'" + str(v).replace("'", "''") + "'"
    if typ == "int":
        return str(int(v))
    return f"{float(v):.4f}"


def write_sql(name: str, df: pd.DataFrame, path: Path, gz: bool) -> Path:
    t = schema.T[name]
    cols = ", ".join(f'"{c}"' for c in t.cols)
    types = [f.typ for f in t.fields]
    lines = []
    for i in range(0, len(df), 500):
        chunk = df.iloc[i: i + 500]
        vals = ",\n".join("(" + ", ".join(_sql_val(v, ty) for v, ty in zip(row, types)) + ")" for row in chunk.itertuples(index=False, name=None))
        lines.append(f'INSERT INTO "{name}" ({cols}) VALUES\n{vals};')
    data = ("\n".join(lines) + "\n").encode("utf-8") if len(df) else b""
    if gz:
        path = Path(str(path) + ".gz")
        with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as g:
            g.write(data)
    else:
        path.write_bytes(data)
    return path


def dictionary_md() -> str:
    out = ["# Data dictionary", "", "Generated from `src/oryva/schema.py` (single source of truth). "
           "Every field lists type, required/optional, allowed values, unit, uniqueness and validation rule.", ""]
    for name in schema.ALL_TABLES:
        t = schema.T[name]
        out += [f"## {name}  _({t.kind})_", "", t.desc, "", f"**Primary key:** `{', '.join(t.pk)}`", "",
                "| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |", "|---|---|---|---|---|---|---|"]
        rows = [r for r in schema.dictionary_rows() if r["table"] == name]
        for r in rows:
            esc = lambda s: str(s).replace("|", "\\|")  # noqa: E731
            out.append(f"| `{r['field']}` | {r['type']} | {r['required']} | {esc(r['allowed_values'])} | {esc(r['unit'])} | {r['uniqueness']} | {esc(r['validation_rule'])} |")
        out.append("")
    out += ["## ground_truth (separate file, never an input)", "",
            "Columns: " + ", ".join(f"`{c}`" for c in schema.GROUND_TRUTH_COLS), ""]
    return "\n".join(out)


def validation_md(rep, ev, dist, meta, P) -> str:
    fr = rep.frame()
    L = ["# Validation summary", "", f"Profile **{P['name']}**, seed **{P['seed']}**, as-of **{P['as_of_date']}**.", ""]
    n_chk = len(fr)
    unexpected = rep.unexpected_failures
    L += [f"* Checks executed: **{n_chk}**", f"* Unexpected failures (all non-labelled checks): **{unexpected}**",
          f"* Labelled checks (fail only on injected ground-truth rows): **{int((fr['kind'] == 'labelled').sum())}**",
          f"* Validator failures == ground-truth anomalies for all 5 edge cases: **{ev['all_validator_reconciled']}**",
          f"* Engine detection precision = recall = 1.0 on all 5 edge cases (boundary cases not flagged): **{ev['all_detection_perfect']}**",
          f"* Expected decisions taken for all 5 edge cases: **{ev['all_decisions_ok']}**", ""]
    L += ["## Results by category", "", "| Category | Checks | Failed checks | Rows failing |", "|---|---|---|---|"]
    for cat, g in fr.groupby("category"):
        L.append(f"| {cat} | {len(g)} | {int(((g['status'] == 'FAIL')).sum())} | {int(g.loc[g['kind'] != 'labelled', 'failed'].sum())} |")
    L += ["", "## Labelled data-quality checks (expected to fail only on injected rows)", "", "| Check | Table | Rows checked | Rows flagged |", "|---|---|---|---|"]
    for r in fr[fr["kind"] == "labelled"].itertuples():
        L.append(f"| {r.check} | {r.table} | {r.checked} | {r.failed} |")
    L += ["", "## Edge-case detection vs. ground truth", "", "| Issue type | Labelled | Boundary | Flagged by engine | TP | FP | FN | Precision | Recall | Validator exact match |", "|---|---|---|---|---|---|---|---|---|---|"]
    vr = {v["issue_type"]: v for v in ev["validator_reconciliation"]}
    for d in ev["detection"]:
        L.append(f"| {d['issue_type']} | {d['labelled']} | {d['boundary_cases']} | {d['engine_flagged']} | {d['true_positive']} | {d['false_positive']} | {d['false_negative']} | {d['precision']} | {d['recall']} | {vr[d['issue_type']]['exact_match']} |")
    L += ["", "## Expected decisions", "", "| Issue type | Decision | Cases | As expected |", "|---|---|---|---|"]
    for d in ev["decisions"]:
        L.append(f"| {d['issue_type']} | {d['decision']} | {d['cases']} | {d['all_as_expected']} |")
    L += ["", "## Planning KPIs", "", "```json", json.dumps(ev["kpis"], indent=2, sort_keys=True, default=str), "```", "",
          "## Data distributions (evaluation area A)", "", "```json", json.dumps(dist, indent=2, sort_keys=True, default=str), "```", "",
          "## Generation metadata", "", "```json", json.dumps(meta, indent=2, sort_keys=True), "```", "",
          "## Every check", "", "| Category | Check | Table | Kind | Checked | Failed | Status |", "|---|---|---|---|---|---|---|"]
    for r in fr.itertuples():
        L.append(f"| {r.category} | {r.check} | {r.table} | {r.kind} | {r.checked} | {r.failed} | {r.status} |")
    return "\n".join(L) + "\n"


SOURCE_MANIFEST = """# Source manifest (PDF section 9 - lawful use)

| Item | Value |
|---|---|
| External data used | **None** - every record is synthetic, produced by `oryva generate` from a fixed seed |
| Personal / confidential data | None |
| Public reference data | None downloaded. Schema concepts are inspired by generic MRP/APS practice (BOM, lead time, MOQ, capacity, projected available balance). |
| Licence of generated data | MIT (same as the repository) |
| Source URL / dataset / version / retrieval date / transformations / discarded fields | Not applicable (no external dataset) |
"""


def export_all(T_in: dict, out: dict, gt: pd.DataFrame, rep, ev: dict, dist: dict, P: dict, meta: dict, out_dir: Path, command: str, compress: str = "auto") -> dict:
    out_dir = Path(out_dir)
    for d in ("csv", "json", "sql", "ground_truth", "docs"):
        (out_dir / d).mkdir(parents=True, exist_ok=True)
    allt = {**T_in, **out}
    files = {}

    def reg(p: Path, rows=None):
        files[str(p.relative_to(out_dir)).replace("\\", "/")] = {"bytes": p.stat().st_size, "sha256": sha256(p), **({"rows": rows} if rows is not None else {})}

    (out_dir / "sql" / "schema.sql").write_text(schema.ddl(), encoding="utf-8")
    reg(out_dir / "sql" / "schema.sql")
    for name in schema.ALL_TABLES:
        df = allt[name]
        gz = (compress == "always") or (compress == "auto" and len(df) > GZ_ROWS)
        reg(write_csv(name, df, out_dir / "csv" / f"{name}.csv", gz), len(df))
        reg(write_json(name, df, out_dir / "json" / f"{name}.json", gz=len(df) > P.get("json_max_rows", 200000)), len(df))
        reg(write_sql(name, df, out_dir / "sql" / f"seed_{name}.sql", gz), len(df))
    gdir = out_dir / "ground_truth"
    reg(write_csv_gt(gt, gdir / "ground_truth.csv"), len(gt))
    (gdir / "ground_truth.json").write_text(json.dumps(json.loads(gt.to_json(orient="records")), indent=0) + "\n", encoding="utf-8")
    reg(gdir / "ground_truth.json", len(gt))
    docs = out_dir / "docs"
    (docs / "data_dictionary.md").write_text(dictionary_md(), encoding="utf-8")
    pd.DataFrame(schema.dictionary_rows()).to_csv(docs / "data_dictionary.csv", index=False, lineterminator="\n")
    (docs / "validation_summary.md").write_text(validation_md(rep, ev, dist, meta, P), encoding="utf-8")
    rep.frame().to_csv(docs / "validation_checks.csv", index=False, lineterminator="\n")
    (docs / "evaluation.json").write_text(json.dumps(ev, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (out_dir / "SOURCE_MANIFEST.md").write_text(SOURCE_MANIFEST, encoding="utf-8")
    for p in [docs / "data_dictionary.md", docs / "data_dictionary.csv", docs / "validation_summary.md", docs / "validation_checks.csv",
              docs / "evaluation.json", out_dir / "SOURCE_MANIFEST.md"]:
        reg(p)
    manifest = {
        "project": "ORYVA NEXUS", "profile": P["name"], "seed": P["seed"], "as_of_date": P["as_of_date"],
        "generator_command": command, "parameters": {k: v for k, v in P.items()}, "generation_metadata": meta,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "table_row_counts": {n: len(allt[n]) for n in schema.ALL_TABLES}, "ground_truth_rows": len(gt),
        "validation": {"checks": len(rep.rows), "unexpected_failures": rep.unexpected_failures,
                       "edge_cases_detected_perfectly": ev["all_detection_perfect"]},
        "files": files}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return manifest


def write_csv_gt(gt: pd.DataFrame, path: Path) -> Path:
    path.write_bytes(gt.to_csv(index=False, lineterminator="\n", na_rep="").encode("utf-8"))
    return path


def load_sqlite(data_dir: Path, db_path: Path) -> None:
    data_dir = Path(data_dir)
    if Path(db_path).exists():
        Path(db_path).unlink()
    con = sqlite3.connect(db_path)
    con.executescript((data_dir / "sql" / "schema.sql").read_text(encoding="utf-8"))
    for name in schema.ALL_TABLES:
        p = data_dir / "sql" / f"seed_{name}.sql"
        if p.exists():
            sql = p.read_text(encoding="utf-8")
        else:
            with gzip.open(str(p) + ".gz", "rt", encoding="utf-8") as f:
                sql = f.read()
        if sql.strip():
            con.executescript(sql)
    con.commit()
    bad = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    if bad:
        raise RuntimeError(f"foreign key violations after load: {bad[:3]}")
