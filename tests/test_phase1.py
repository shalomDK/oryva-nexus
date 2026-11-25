"""Phase-1 closure tests: double-count variant B, transport-delay variation, independent mitigation audit."""
import json
import subprocess
import sys
from pathlib import Path

from oryva.inject import n_variant_b


def test_double_count_variant_b_received_order_relisted_as_open(tiny):
    gt, T, out = tiny["gt"], tiny["T"], tiny["out"]
    b = gt[(gt["issue_type"] == "INBOUND_DOUBLE_COUNT") & (gt["injected_value"] == "RECEIVED_ORDER_RELISTED_AS_OPEN")]
    assert len(b) == n_variant_b(tiny["P"]) >= 1
    po = T["PurchaseOrder"].set_index("po_id")
    for r in b.itertuples():
        orig, dup = po.loc[r.related_record_ids], po.loc[r.record_id]
        assert orig["status"] == "RECEIVED" and dup["status"] == "PLANNED"
        assert orig["supplier_ref_no"] == dup["supplier_ref_no"] and orig["qty_base"] == dup["qty_base"]
        ev = T["InventoryEvent"]
        assert ((ev["po_id"] == r.related_record_ids) & (ev["event_type"] == "RECEIPT")).any()  # already in on-hand
    f = out["DataQualityFinding"]
    assert set(b["record_id"]) <= set(f.loc[f["issue_type"] == "INBOUND_DOUBLE_COUNT", "record_id"])


def test_transport_delays_exist_and_shift_supply(tiny):
    T, out = tiny["T"], tiny["out"]
    d = T["TransportEvent"]
    d = d[d["event_type"] == "DELAYED"]
    assert len(d) >= 5 and d["delay_days"].between(3, 35).all()
    assert set(d["reason_code"]) <= {"WEATHER", "PORT_CONGESTION", "CUSTOMS", "BREAKDOWN", "DOCUMENTATION"}
    po = T["PurchaseOrder"]
    delayed = po[po["po_id"].isin(d["po_id"])]
    assert (delayed["eta_date"] > delayed["promised_date"]).all()


def test_independent_audit_script_clean_on_tiny_export(tiny_dir, tmp_path):
    out = tmp_path / "ev.json"
    r = subprocess.run([sys.executable, "scripts/audit.py", str(tiny_dir), str(out)], capture_output=True, text=True, cwd=Path.cwd())
    assert r.returncode == 0, r.stderr[-800:]
    e = json.loads(out.read_text())
    assert e["fk_pandas"]["orphans_total"] == 0 and e["sql"]["foreign_key_violations"] == 0 and e["pk_duplicates"]["total_duplicates"] == 0
    assert e["balance_independent_recompute"]["cells_mismatching"] == 0 and e["shortage_independent_recompute"]["identical"]
    assert all(x == 0 for k, x in e["mitigation_all_types_independent"].items() if k != "checked")
    assert all(x == 0 for k, x in e["mitigation_constraints"].items() if k.startswith(("qty_", "lead_days", "supplier_not", "arrival", "recommended_", "missing_", "failed_", "shortages_", "options_")))
    assert all(e["engine_rerun_from_inputs_only_equals_export"].values())
    assert not e["ground_truth"]["input_tables_with_label_columns"] and not e["ground_truth"]["engine_sources_referencing_ground_truth"]
    assert all(d["fp"] == 0 and d["fn"] == 0 and d["boundary_flagged"] == 0 for d in e["edge_case_detection"])
