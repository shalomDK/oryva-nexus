"""Supplier failure stress test: verified by re-planning, consistent with the scenario simulator, baseline untouched."""
import hashlib
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from oryva import weeks as W
from oryva.advanced import stress as S
from oryva.advanced.scenario import Scenario, simulate
from oryva.app.state import State
from oryva.config import load_policy


@pytest.fixture(scope="module")
def ds(tiny):
    return tiny["T"], tiny["out"], load_policy()


def _fp(frames):
    return {k: hashlib.sha256(pd.util.hash_pandas_object(v, index=True).values.tobytes()).hexdigest() for k, v in frames.items()}


def test_failure_matches_the_scenario_simulator(ds):
    T, out, pol = ds
    s = S.exposure(T).index[0]
    r = S.evaluate_failure(T, out, pol, s, None)
    ref = simulate(T, out, Scenario(disabled_suppliers=[s]), pol)
    k = ref["kpis"].set_index("metric")["delta"]
    assert r["shortage_units_delta"] == int(k["shortage_units"]) and abs(r["value_at_risk_delta"] - k["value_at_risk"]) < 0.01
    assert r["new_shortages"] == ref["counts"]["new"] and r["worse_shortages"] == ref["counts"]["worse"]


def test_outage_window_only_cancels_orders_due_in_the_window(ds):
    T, out, pol = ds
    s = S.exposure(T).index[0]
    T2, n = S.fail_supplier(T, s, 4)
    po, po2 = T["PurchaseOrder"], T2["PurchaseOrder"]
    changed = po2[po2["status"] != po["status"]]
    assert len(changed) == n and (changed["supplier_id"] == s).all() and (W.weeks_of(changed["eta_date"]) <= 4).all()
    assert set(po.loc[changed.index, "status"]) <= {"PLANNED", "CONFIRMED"}
    assert T2["Supplier"].set_index("supplier_id").at[s, "status"] == "ON_HOLD"
    _, n_all = S.fail_supplier(T, s, None)
    assert n_all >= n


def test_supplier_without_open_orders_has_no_impact(ds):
    T, out, pol = ds
    po = T["PurchaseOrder"]
    idle = sorted(set(T["Supplier"]["supplier_id"]) - set(po.loc[po["status"].isin(["PLANNED", "CONFIRMED"]), "supplier_id"]))
    if not idle:
        pytest.skip("every supplier has open orders")
    r = S.evaluate_failure(T, out, pol, idle[0], None)
    assert r["orders_cancelled"] == 0 and r["new_shortages"] == 0 and r["shortage_units_delta"] <= 0


def test_ranking_is_by_verified_impact_and_preparedness_adds_up(ds):
    T, out, pol = ds
    r = S.stress_test(T, out, pol, 5, 8)
    t = r["table"]
    assert len(t) == len(r["screened"]) == min(5, len(S.exposure(T)))
    assert t["shortage_units_delta"].is_monotonic_decreasing or t["shortage_units_delta"].tolist() == sorted(t["shortage_units_delta"], reverse=True)
    for row in t.itertuples():
        assert row.fully_recoverable + row.partly_recoverable + row.unrecoverable == row.new_shortages + row.worse_shortages
    assert r["rank_correlation"] is None or -1 <= r["rank_correlation"] <= 1


def test_single_sourced_definition(ds):
    T, out, pol = ds
    s = S.exposure(T).index[0]
    ss = T["SKUSupplier"]
    act = set(T["Supplier"].query("status == 'ACTIVE'")["supplier_id"]) | {s}
    for sku in S.single_sourced(T, s):
        others = ss[(ss["sku_id"] == sku) & (ss["approval_status"] == "APPROVED") & ss["supplier_id"].isin(act)]["supplier_id"]
        assert set(others) == {s}


def test_hedge_candidates_are_active_same_family_and_not_the_failed_supplier(ds):
    T, out, pol = ds
    s = S.exposure(T).index[0]
    skus = S.single_sourced(T, s)[:3] or list(T["SKUSupplier"].query("supplier_id == @s")["sku_id"][:2])
    h = S.hedge_candidates(T, out, s, skus)
    fam = T["SKU"].set_index("sku_id")["product_family"]
    sup = T["Supplier"].set_index("supplier_id")
    cap = T["SupplierCapacity"]
    for r in h.dropna(subset=["candidate_supplier"]).itertuples():
        assert r.candidate_supplier != s and sup.at[r.candidate_supplier, "status"] == "ACTIVE"
        assert ((cap["supplier_id"] == r.candidate_supplier) & (cap["product_family"] == fam[r.sku_id])).any()


def test_stress_test_never_mutates_the_baseline(ds):
    T, out, pol = ds
    before, out_before = _fp(T), _fp(out)
    S.stress_test(T, out, pol, 3, None)
    assert _fp(T) == before and _fp(out) == out_before


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_stress_page_runs_and_is_audited(tmp_path_factory, tiny_dir, tmp_path):
    from streamlit.testing.v1 import AppTest
    root = tmp_path_factory.mktemp("st_root")
    shutil.copytree(tiny_dir, root / "tiny")
    os.environ.update(ORYVA_DATA_ROOT=str(root), ORYVA_DEFAULT_DATASET="tiny", ORYVA_STATE_DB=str(tmp_path / "s.sqlite"), ORYVA_LOG_DIR=str(tmp_path / "l"))
    at = AppTest.from_file(APP, default_timeout=600)
    at.session_state["user"] = {"username": "analyst", "role": "LOGISTICS_ANALYST", "display_name": "a", "supplier_id": None}
    at.session_state["nav"] = "Stress test"
    at.run()
    assert not at.exception and not at.error
    at.button(key="st_run").click().run()
    assert not at.exception and not at.error and len(at.dataframe) >= 2
    s = State(tmp_path / "s.sqlite")
    assert any(r["action"] == "stress.run" for r in s.audit_rows()) and s.verify_chain()[0]
