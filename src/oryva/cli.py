"""Command line: generate | validate | repro | load-sql | dictionary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import schema
from .export import dictionary_md, load_sqlite
from .pipeline import build, reproducibility, validate_export, verify_checksums


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="oryva", description="ORYVA NEXUS planning + synthetic data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate, inject labelled edge cases, plan, validate, evaluate, export")
    g.add_argument("--profile", default="starter")
    g.add_argument("--out", default=None, help="output dir (default data/<profile>)")
    g.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a profile value, e.g. assortment_density=0.2")
    g.add_argument("--compress", default="auto", choices=["auto", "always", "never"])
    v = sub.add_parser("validate", help="validate an existing export (+ score against ground truth)")
    v.add_argument("--data-dir", required=True)
    r = sub.add_parser("repro", help="generate twice with the same seed and compare row counts + checksums")
    r.add_argument("--profile", default="starter")
    r.add_argument("--work", default="data/_scratch")
    r.add_argument("--report", default=None, help="write the markdown report here")
    r.add_argument("--set", action="append", default=[])
    s = sub.add_parser("load-sql", help="load the SQL seed into a SQLite database")
    s.add_argument("--data-dir", required=True)
    s.add_argument("--db", default="oryva.sqlite")
    sub.add_parser("dictionary", help="print the data dictionary (markdown)")
    rp = sub.add_parser("report", help="write the role-based decision & exception report for an export")
    rp.add_argument("--data-dir", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "generate":
        out = Path(a.out or f"data/{a.profile}")
        cmd = "python -m oryva generate --profile " + a.profile + "".join(f" --set {x}" for x in a.set) + f" --out {out.as_posix()}"
        res = build(a.profile, out, a.set, command=cmd, compress=a.compress)
        ev, rep = res["eval"], res["report"]
        print(json.dumps({"out": str(out), "tables": res["manifest"]["table_row_counts"], "checks": len(rep.rows),
                          "unexpected_failures": rep.unexpected_failures, "edge_cases_detected_perfectly": ev["all_detection_perfect"],
                          "validator_reconciled": ev["all_validator_reconciled"], "decisions_ok": ev["all_decisions_ok"],
                          "actual_assortment_density": res["meta"]["actual_assortment_density"]}, indent=2))
        return 0 if (rep.unexpected_failures == 0 and ev["all_detection_perfect"] and ev["all_validator_reconciled"] and ev["all_decisions_ok"]) else 1
    if a.cmd == "validate":
        rep, ev, man = validate_export(Path(a.data_dir))
        bad = verify_checksums(Path(a.data_dir))
        print(rep.frame().groupby("status").size().to_string())
        print("unexpected failures:", rep.unexpected_failures, "| checksum mismatches:", bad)
        if ev:
            print("detection perfect:", ev["all_detection_perfect"], "| validator reconciled:", ev["all_validator_reconciled"], "| decisions ok:", ev["all_decisions_ok"])
        return 0 if rep.unexpected_failures == 0 and not bad and (ev is None or (ev["all_detection_perfect"] and ev["all_validator_reconciled"])) else 1
    if a.cmd == "repro":
        res = reproducibility(a.profile, Path(a.work), a.set)
        print(res["report_md"][:600])
        if a.report:
            Path(a.report).parent.mkdir(parents=True, exist_ok=True)
            Path(a.report).write_text(res["report_md"], encoding="utf-8")
        return 0 if res["ok"] else 1
    if a.cmd == "load-sql":
        load_sqlite(Path(a.data_dir), Path(a.db))
        print(f"loaded into {a.db} (foreign_key_check clean)")
        return 0
    if a.cmd == "report":
        from .report import build_report
        p = Path(a.data_dir) / "docs" / "role_report.md"
        p.write_text(build_report(Path(a.data_dir)), encoding="utf-8")
        print(f"wrote {p}")
        return 0
    if a.cmd == "dictionary":
        sys.stdout.write(dictionary_md())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
