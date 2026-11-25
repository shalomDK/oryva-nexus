"""The five mandatory edge cases: injection, labelling, traceability, detection, decisions, blast radius, firewall."""
import ast
import re
from pathlib import Path

import pandas as pd
import pytest

from oryva import schema
from oryva.config import load_policy, load_profile
from oryva.datagen import generate_baseline
from oryva.inject import inject, n_reserved
from oryva.planning import run_plan
from oryva.pipeline import validate_export, verify_checksums

ISSUES = schema.ISSUES


def test_every_issue_type_is_labelled_and_traceable(tiny):
    gt, T = tiny["gt"], tiny["T"]
    k = tiny["P"]["edge_cases"]["per_type"]
    anom = gt[gt["label_class"] == "ANOMALY"]
    for it in ISSUES:
        assert (anom["issue_type"] == it).sum() >= k, it
    assert set(gt.columns) == set(schema.GROUND_TRUTH_COLS) and gt["seed"].eq(tiny["P"]["seed"]).all()
    # traceable to source records
    po = set(T["PurchaseOrder"]["po_id"])
    for it, ent in (("INBOUND_DOUBLE_COUNT", "PurchaseOrder"), ("UOM_MISMATCH", "PurchaseOrder")):
        rows = anom[anom["issue_type"] == it]
        assert rows["record_id"].isin(po).all() and (rows["entity"] == ent).all()
    dups = anom[anom["issue_type"] == "INBOUND_DOUBLE_COUNT"]
    assert dups["related_record_ids"].isin(po).all()
    assert (gt["label_class"] == "BOUNDARY").any()


def test_engine_detects_every_labelled_case_with_precision_and_recall_1(tiny):
    ev = tiny["eval"]
    assert ev["all_detection_perfect"] and ev["all_decisions_ok"] and ev["all_validator_reconciled"]
    for d in ev["detection"]:
        assert d["precision"] == 1.0 and d["recall"] == 1.0 and d["boundary_wrongly_flagged"] == 0, d


def test_blast_radius_only_labelled_rows_change():
    P = load_profile("tiny")
    k = P["edge_cases"]["per_type"]
    T0, _ = generate_baseline(P, n_reserved(P))
    out0, _ = run_plan(T0, load_policy(), P["seed"], "tiny")
    T1, gt = inject(T0, out0, P)
    untouched = [t for t in T0 if t not in ("PurchaseOrder", "PurchaseOrderEvent", "SupplierCapacity", "LeadTime", "SKUSubstitute")]
    for t in untouched:
        assert T0[t].equals(T1[t]), f"{t} changed outside the labelled injections"
    # purchase orders: only UoM-labelled rows differ; the rest are byte-identical; duplicates are additions
    uom_ids = set(gt[(gt["issue_type"] == "UOM_MISMATCH") & (gt["label_class"] == "ANOMALY")]["record_id"])
    a, b = T0["PurchaseOrder"].set_index("po_id"), T1["PurchaseOrder"].set_index("po_id")
    common = a.index
    diff = [i for i in common if not a.loc[i].equals(b.loc[i])]
    assert set(diff) == uom_ids
    assert len(b) - len(a) == n_reserved(P)
    # events of existing POs unchanged
    ea, eb = T0["PurchaseOrderEvent"], T1["PurchaseOrderEvent"]
    assert eb[eb["event_id"].isin(ea["event_id"])].reset_index(drop=True).equals(ea)
    # lead times: only labelled (supplier, sku) removed ; capacity & substitutes: only additions
    lt_removed = T0["LeadTime"][~T0["LeadTime"]["lead_time_id"].isin(T1["LeadTime"]["lead_time_id"])]
    assert len(lt_removed) >= 1
    assert T0["SupplierCapacity"]["capacity_id"].isin(T1["SupplierCapacity"]["capacity_id"]).all()
    assert len(T0["SKUSubstitute"]) < len(T1["SKUSubstitute"])


def test_injected_data_gives_same_shortages_as_clean_for_duplicate_and_uom_targets():
    """Engine neutralises double counting and UoM errors: shortage quantities equal the clean baseline's."""
    P = load_profile("tiny")
    k = P["edge_cases"]["per_type"]
    T0, _ = generate_baseline(P, n_reserved(P))
    pol = load_policy()
    out0, _ = run_plan(T0, pol, P["seed"], "tiny")
    T1, gt = inject(T0, out0, P)
    out1, _ = run_plan(T1, pol, P["seed"], "tiny")
    po = T1["PurchaseOrder"].set_index("po_id")
    ids_ = gt[(gt["label_class"] == "ANOMALY") & gt["issue_type"].isin(["INBOUND_DOUBLE_COUNT", "UOM_MISMATCH"])]["record_id"]
    pairs = {(po.at[i, "sku_id"], po.at[i, "ship_to_location_id"]) for i in ids_}
    pb0 = out0["ProjectedBalance"].set_index(["sku_id", "location_id", "iso_week"])["closing_qty"]
    pb1 = out1["ProjectedBalance"].set_index(["sku_id", "location_id", "iso_week"])["closing_qty"]
    for (s, l) in pairs:
        assert pb0.loc[(s, l)].equals(pb1.loc[(s, l)]), (s, l)


def test_missing_lead_time_chains_are_blocked_and_substitutes_never_recommended(tiny):
    gt, o = tiny["gt"], tiny["out"]
    skus = gt[(gt["issue_type"] == "SHORTAGE_MISSING_LEAD_TIME")]["related_record_ids"].unique()
    sh = o["Shortage"][o["Shortage"]["sku_id"].isin(skus)]
    assert len(sh) and (sh["status"] == "NEEDS_REVIEW").all()
    mo = o["MitigationOption"]
    sub = mo[mo["option_type"] == "SUBSTITUTE_SKU"]
    approved = tiny["T"]["SKUSubstitute"]
    approved = set(zip(approved.loc[approved["approval_status"] == "APPROVED", "sku_id"], approved.loc[approved["approval_status"] == "APPROVED", "substitute_sku_id"]))
    s2 = sub.merge(o["Shortage"][["shortage_id", "sku_id"]], on="shortage_id")
    for r in s2.itertuples():
        if r.is_recommendable:
            assert (r.sku_id, r.alt_sku_id) in approved


def test_capacity_exceeded_flagged_and_boundary_is_not(tiny):
    gt, led = tiny["gt"], tiny["out"]["SupplierCapacityLedger"]
    ex = set(f"{a}|{b}|{c}" for a, b, c in zip(led.loc[led["status"] == "EXCEEDED", "supplier_id"], led.loc[led["status"] == "EXCEEDED", "product_family"], led.loc[led["status"] == "EXCEEDED", "week_start_date"]))
    anom = set(gt[(gt["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED") & (gt["label_class"] == "ANOMALY")]["record_id"])
    bnd = set(gt[(gt["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED") & (gt["label_class"] == "BOUNDARY")]["record_id"])
    assert ex == anom and not (ex & bnd) and len(bnd) == 1


def test_baseline_has_no_capacity_exceedance_or_other_anomalies():
    P = load_profile("tiny")
    T0, _ = generate_baseline(P, n_reserved(P))
    out0, _ = run_plan(T0, load_policy(), P["seed"], "tiny")
    assert len(out0["DataQualityFinding"]) == 0
    assert (out0["SupplierCapacityLedger"]["status"] == "OK").all()


# ------------------------------------------------------------------ ground-truth firewall (evaluation area F)
FORBIDDEN_COLS = {"issue_type", "ground_truth", "label", "is_anomaly", "anomaly", "label_class"}


def test_no_input_table_carries_labels(tiny):
    for name in schema.INPUT_TABLES:
        assert not (set(tiny["T"][name].columns) & FORBIDDEN_COLS), name
        assert not (set(schema.T[name].cols) & FORBIDDEN_COLS), name


def test_engine_modules_never_reference_ground_truth():
    src = Path("src/oryva")
    for mod in ("planning.py", "dq.py", "datagen.py", "validate.py", "frames.py"):
        text = (src / mod).read_text(encoding="utf-8")
        assert not re.search(r"ground_truth|GROUND_TRUTH|\bgt\b", text), mod
    # only evaluate.py (and the exporter/injector that WRITE it) may touch labels
    for mod in ("planning.py", "dq.py", "validate.py"):
        tree = ast.parse((src / mod).read_text(encoding="utf-8"))
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert "evaluate" not in imported and "inject" not in imported


def test_export_keeps_ground_truth_in_a_separate_folder_and_validates_from_disk(tiny_dir):
    gt_dir = tiny_dir / "ground_truth"
    assert (gt_dir / "ground_truth.csv").exists() and (gt_dir / "ground_truth.json").exists()
    assert not any("ground_truth" in p.name for p in (tiny_dir / "csv").iterdir())
    assert verify_checksums(tiny_dir) == []
    rep, ev, man = validate_export(tiny_dir)
    assert rep.unexpected_failures == 0 and ev["all_detection_perfect"] and ev["all_validator_reconciled"]
    for f in ("manifest.json", "SOURCE_MANIFEST.md", "docs/data_dictionary.md", "docs/validation_summary.md", "sql/schema.sql"):
        assert (tiny_dir / f).exists(), f
    for t in schema.ALL_TABLES:
        assert (tiny_dir / "csv" / f"{t}.csv").exists() and (tiny_dir / "sql" / f"seed_{t}.sql").exists()


def test_sql_seed_loads_into_sqlite_with_valid_foreign_keys(tiny_dir, tmp_path):
    from oryva.export import load_sqlite
    import sqlite3
    db = tmp_path / "t.sqlite"
    load_sqlite(tiny_dir, db)
    con = sqlite3.connect(db)
    n = con.execute('select count(*) from "SKU"').fetchone()[0]
    assert n == load_profile("tiny")["n_skus"]
    assert con.execute('select count(*) from "PurchaseOrder"').fetchone()[0] == load_profile("tiny")["n_purchase_orders"]
    con.close()

