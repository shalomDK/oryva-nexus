"""Decision Room: options are verified by re-running the planning engine on copies; the baseline never changes;
the optional movement hook leaves mandatory outputs untouched; the UI flow is permissioned and audited."""
import hashlib
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from oryva import weeks as W
from oryva.advanced import decision as D
from oryva.config import load_policy
from oryva.planning import run_plan
from oryva.app.state import State


@pytest.fixture(scope="module")
def ds(tiny):
    return tiny["T"], tiny["out"], load_policy()


def _fp(frames):
    return {k: hashlib.sha256(pd.util.hash_pandas_object(v, index=True).values.tobytes()).hexdigest() for k, v in frames.items()}


def _opts(out, kind):
    mo = out["MitigationOption"]
    return mo[(mo["option_type"] == kind) & (mo["is_recommendable"] == 1)].sort_values("mitigation_id")


# ------------------------------------------------------------------ engine hook safety
def test_engine_outputs_identical_without_or_with_empty_movement_table(ds):
    T, out, pol = ds
    a, _ = run_plan(T, pol, 1, "x")
    b, _ = run_plan({**T, "PlannedMovement": pd.DataFrame(columns=D.MOVEMENT_COLS)}, pol, 1, "x")
    for k in a:
        assert a[k].equals(b[k]), k


def test_engine_output_matches_the_exported_plan(ds):
    T, out, pol = ds
    a, _ = run_plan(T, pol, 20261022, "tiny")
    for k in ("Shortage", "MitigationOption", "ProjectedBalance", "ShortageCause"):
        assert a[k].reset_index(drop=True).equals(out[k].reset_index(drop=True)), k


def test_movement_is_dependent_demand_at_source_and_receipt_at_destination(ds):
    T, out, pol = ds
    pb = out["ProjectedBalance"]
    pairs = pb[["sku_id", "location_id"]].drop_duplicates()
    sku = pairs["sku_id"].value_counts().index[0]
    locs = list(pairs[pairs["sku_id"] == sku]["location_id"][:2])
    mv = pd.DataFrame([[sku, locs[0], sku, locs[1], 7, 1, 7, 2, "t"]], columns=D.MOVEMENT_COLS)
    o2, _ = run_plan({**T, "PlannedMovement": mv}, pol, 1, "x")
    def g(o, l):
        p_ = o["ProjectedBalance"]
        return p_[(p_["sku_id"] == sku) & (p_["location_id"] == l)].sort_values("week_start_date").reset_index(drop=True)
    s0, s1, r0, r1 = g(out, locs[0]), g(o2, locs[0]), g(out, locs[1]), g(o2, locs[1])
    assert (s1["dependent_demand_qty"] - s0["dependent_demand_qty"]).tolist()[:2] == [7, 0]
    assert ((s1["closing_qty"] - s0["closing_qty"]) == -7).all()
    assert (r1["scheduled_receipts_qty"] - r0["scheduled_receipts_qty"]).tolist()[:3] == [0, 7, 0]
    assert (r1["closing_qty"] - r0["closing_qty"]).tolist()[:3] == [0, 7, 7]


# ------------------------------------------------------------------ applying options
def test_apply_option_never_mutates_the_baseline(ds):
    T, out, pol = ds
    before, out_before = _fp(T), _fp(out)
    for m in out["MitigationOption"][out["MitigationOption"]["is_recommendable"] == 1]["mitigation_id"].head(25):
        D.apply_option(T, out, m)
    assert _fp(T) == before and _fp(out) == out_before


def test_new_po_option_becomes_a_real_planned_order(ds):
    T, out, pol = ds
    o = _opts(out, "NEW_PO").iloc[0]
    T2, desc, _ = D.apply_option(T, out, o["mitigation_id"])
    po = T2["PurchaseOrder"]
    assert len(po) == len(T["PurchaseOrder"]) + 1
    new = po.iloc[-1]
    assert new["status"] == "PLANNED" and new["qty_base"] == o["qty"] and new["supplier_id"] == o["supplier_id"] and new["eta_date"] == o["earliest_arrival_date"]
    assert new["po_id"] not in set(T["PurchaseOrder"]["po_id"]) and new["po_id"] in desc


def test_fully_covering_on_time_options_are_verified_as_resolved(ds):
    T, out, pol = ds
    mo = out["MitigationOption"]
    sh = out["Shortage"].set_index("shortage_id")
    full = mo[(mo["is_recommendable"] == 1) & (mo["weeks_late"] == 0) & (mo["option_type"].isin(["NEW_PO", "ALT_SUPPLIER_PO", "EXPEDITE_PO", "LOCATION_TRANSFER"]))]
    full = full[full["covered_qty"] >= full["shortage_id"].map(sh["shortage_qty"])].head(6)
    assert len(full)
    for m in full["mitigation_id"]:
        r = D.replan(T, out, pol, m)
        assert r["gap_after"] == 0 and r["verdict"] == "RESOLVED", (m, r["gap_before"], r["gap_after"])


def test_backorder_option_changes_nothing(ds):
    T, out, pol = ds
    m = _opts(out, "PARTIAL_FILL_BACKORDER")["mitigation_id"].iloc[0]
    r = D.replan(T, out, pol, m)
    assert r["gap_after"] == r["gap_before"] and r["shortage_units_delta"] == 0 and len(r["side_effects"]) == 0
    assert r["series_before"].equals(r["series_after"])


def test_transfer_moves_stock_out_of_the_donor(ds):
    T, out, pol = ds
    o = _opts(out, "LOCATION_TRANSFER").iloc[0]
    T2, _, _ = D.apply_option(T, out, o["mitigation_id"])
    o2, _ = run_plan(T2, pol, 1, "x")
    sku = out["Shortage"].set_index("shortage_id").at[o["shortage_id"], "sku_id"]
    def g(o_):
        p_ = o_["ProjectedBalance"]
        return p_[(p_["sku_id"] == sku) & (p_["location_id"] == o["source_location_id"])].sort_values("week_start_date")["closing_qty"].to_numpy()
    assert (g(out) - g(o2) == o["qty"]).all()


def test_production_replan_is_rechecked_against_work_centre_hours(ds):
    T, out, pol = ds
    p = _opts(out, "PRODUCTION_REPLAN")
    if p.empty:
        pytest.skip("no production re-plan option in the tiny dataset")
    o = p.iloc[0]
    T2, _, _ = D.apply_option(T, out, o["mitigation_id"])
    assert len(T2["ProductionPlan"]) == len(T["ProductionPlan"]) + 1
    o2, _ = run_plan(T2, pol, 1, "x")
    cap = T["ProductionCapacity"].set_index(["work_center_id", "week_start_date"])["available_hours"]
    rt = T["BillOfMaterial"].set_index("parent_sku_id")["run_time_hours_per_unit"]
    pp = T2["ProductionPlan"]
    wc, wk = pp.iloc[-1]["work_center_id"], pp.iloc[-1]["week_start_date"]
    on_wc = pp[pp["work_center_id"] == wc][["sku_id", "location_id"]].drop_duplicates()
    pb2 = o2["ProjectedBalance"]
    rows = pb2[pb2["week_start_date"] == wk].merge(on_wc, on=["sku_id", "location_id"])
    hours = float((rows["production_receipts_qty"] * rows["sku_id"].map(rt)).sum())
    assert hours <= float(cap[(wc, wk)]) + 1e-6  # the extra order was re-checked against the work-centre's hours
    pb1 = out["ProjectedBalance"]
    sk, lo = pp.iloc[-1]["sku_id"], pp.iloc[-1]["location_id"]
    before = int(pb1[(pb1["sku_id"] == sk) & (pb1["location_id"] == lo) & (pb1["week_start_date"] == wk)]["production_receipts_qty"].sum())
    after = int(pb2[(pb2["sku_id"] == sk) & (pb2["location_id"] == lo) & (pb2["week_start_date"] == wk)]["production_receipts_qty"].sum())
    assert before <= after <= before + int(o["qty"])


# ------------------------------------------------------------------ decision matrix
def test_matrix_ranks_by_verified_outcome_and_includes_engine_pick(ds):
    T, out, pol = ds
    sid = out["Shortage"].sort_values("priority_rank")["shortage_id"].iloc[0]
    m = D.decision_matrix(T, out, pol, sid, 4)
    t = m["table"]
    assert len(t) >= 2 and m["best"] == t.iloc[0]["mitigation_id"]
    assert t["verified_rank"].tolist() == list(range(1, len(t) + 1))
    order = t.assign(v=t["verdict"].map(D.VERDICT_ORDER))[["v", "gap_after", "side_effect_units", "engine_cost"]].to_numpy().tolist()
    assert order == sorted(order)
    rec = out["MitigationOption"].query("shortage_id == @sid and is_recommended == 1")["mitigation_id"].iloc[0]
    assert rec in set(t["mitigation_id"]) and m["engine_pick"] == rec and m["agrees"] == (m["best"] == rec)
    for _, row in t.iterrows():  # every number in the matrix comes from a replan result
        r = m["results"][row["mitigation_id"]]
        assert row["gap_after"] == r["gap_after"] and row["side_effect_units"] == r["side_effect_units"]


def test_gap_numbers_recompute_from_the_projected_balance(ds):
    T, out, pol = ds
    sid = out["Shortage"].sort_values("priority_rank")["shortage_id"].iloc[0]
    sh = out["Shortage"].set_index("shortage_id").loc[sid]
    m = D.decision_matrix(T, out, pol, sid, 2)
    r = next(iter(m["results"].values()))
    assert r["gap_before"] == int(sh["shortage_qty"])


def test_case_file_cites_real_evidence(ds):
    T, out, pol = ds
    sid = out["Shortage"].sort_values("priority_rank")["shortage_id"].iloc[0]
    m = D.decision_matrix(T, out, pol, sid, 2)
    md = D.case_file(T, out, pol, sid, m, m["best"], [{"check": "x", "ok": True, "detail": "y"}], "2025-12-29")
    for src in out["ShortageCause"].query("shortage_id == @sid")["source_id"]:
        assert src in md
    assert m["best"] in md and "## 5. Policy parameters used" in md and str(pol["backorder_cost_pct_per_week"]) in md


# ------------------------------------------------------------------ UI flow
APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _app(root, tmp, role="PLANNER", user="planner"):
    from streamlit.testing.v1 import AppTest
    os.environ.update(ORYVA_DATA_ROOT=str(root), ORYVA_DEFAULT_DATASET="tiny", ORYVA_STATE_DB=str(tmp / "s.sqlite"), ORYVA_LOG_DIR=str(tmp / "l"))
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["user"] = {"username": user, "role": role, "display_name": user, "supplier_id": None}
    at.session_state["nav"] = "Decision room"
    return at


@pytest.fixture(scope="module")
def root(tmp_path_factory, tiny_dir):
    r = tmp_path_factory.mktemp("dr_root")
    shutil.copytree(tiny_dir, r / "tiny")
    return r


def test_decision_room_verify_and_approve_is_audited(root, tmp_path):
    at = _app(root, tmp_path).run()
    assert not at.exception and not at.error
    at.button(key="dr_run").click().run()
    assert not at.exception and not at.error
    assert len(at.dataframe) >= 2
    ok = at.button(key="dr_ok")
    s = State(tmp_path / "s.sqlite")
    assert any(r["action"] == "decision.verified" for r in s.audit_rows())
    if not ok.disabled:
        ok.click().run()
        assert not at.exception
        acts = [r["action"] for r in s.audit_rows()]
        assert "decision.evidence" in acts and "mitigation.approved" in acts and s.verify_chain()[0]


def test_decision_room_read_only_role_cannot_approve(root, tmp_path):
    at = _app(root, tmp_path, "LOGISTICS_ANALYST", "analyst").run()
    at.button(key="dr_run").click().run()
    assert not at.exception and at.button(key="dr_ok").disabled
