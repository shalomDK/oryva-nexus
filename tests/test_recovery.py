"""Multi-shortage recovery planner: joint feasibility on shared constraints, verification by recalculation, honest
explanations, baseline isolation, and the permissioned/audited UI flow."""
import hashlib
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from oryva.advanced import decision as D
from oryva.advanced import recovery as R
from oryva.app.state import State
from oryva.config import load_policy

STARTER = Path("data/starter")


@pytest.fixture(scope="module")
def tinyds(tiny):
    return tiny["T"], tiny["out"], load_policy()


@pytest.fixture(scope="module")
def starter():
    if not (STARTER / "manifest.json").exists():
        pytest.skip("committed starter dataset not present")
    from oryva.advanced.data import load_dataset
    ds = load_dataset(STARTER)
    return ds["T"], ds["out"], ds["policy"]


@pytest.fixture(scope="module")
def conflict(starter):
    T, out, pol = starter
    sug = R.suggest_conflict_sets(T, out, pol)
    if sug.empty:
        pytest.skip("no conflicting shortages in this dataset")
    sids = list(sug.iloc[0]["shortages"])
    return sids, R.plan_recovery(T, out, pol, sids)


def _fp(frames):
    return {k: hashlib.sha256(pd.util.hash_pandas_object(v, index=True).values.tobytes()).hexdigest() for k, v in frames.items()}


# ------------------------------------------------------------------ stacking options
def test_options_stack_instead_of_overwriting(tinyds):
    T, out, pol = tinyds
    tr = out["MitigationOption"].query("option_type == 'LOCATION_TRANSFER' and is_recommendable == 1").drop_duplicates("shortage_id").head(2)
    assert len(tr) == 2
    T1, _, _ = D.apply_option(T, out, tr.iloc[0]["mitigation_id"])
    T2, _, _ = D.apply_option(T1, out, tr.iloc[1]["mitigation_id"])
    assert len(T1["PlannedMovement"]) == 1 and len(T2["PlannedMovement"]) == 2 and "PlannedMovement" not in T


def test_stacked_new_orders_get_distinct_ids(tinyds):
    T, out, pol = tinyds
    po = out["MitigationOption"].query("option_type == 'NEW_PO' and is_recommendable == 1").drop_duplicates("shortage_id").head(2)
    T2 = T
    for m in po["mitigation_id"]:
        T2, _, _ = D.apply_option(T2, out, m)
    new = T2["PurchaseOrder"].iloc[len(T["PurchaseOrder"]):]
    assert len(new) == len(po) and new["po_id"].is_unique and not new["po_id"].isin(T["PurchaseOrder"]["po_id"]).any()


# ------------------------------------------------------------------ joint feasibility
def test_independent_picks_are_collectively_infeasible_and_coordinated_plan_is_not(conflict):
    sids, res = conflict
    assert res["feasible"]["Independent best picks"] is False
    assert res["feasible"]["Coordinated plan"] is True
    co = res["comparison"].set_index("plan")
    assert co.at["Independent best picks", "shared_resource_violations"] >= 1 and co.at["Coordinated plan", "shared_resource_violations"] == 0
    u = res["usage"]["Coordinated plan"]
    assert not len(u) or not u["over"].any()


def test_coordinated_plan_is_no_costlier_than_any_feasible_start(conflict):
    sids, res = conflict
    obj = res["objective"]
    if res["feasible"]["Engine one-by-one picks"]:
        assert obj["Coordinated plan"] <= obj["Engine one-by-one picks"] + 1e-9
    c, caps = res["candidates"], res["caps"]
    rep = R._improve(c, caps, R._repair(c, caps, R.independent_picks(c)))
    assert obj["Coordinated plan"] <= R.objective(c, rep) + 1e-9


def test_coordinated_plan_is_locally_optimal(conflict):
    sids, res = conflict
    c, caps, plan = res["candidates"], res["caps"], res["plans"]["Coordinated plan"]
    base = R.objective(c, plan)
    for sid, g in c.groupby("shortage_id"):
        for m in g["mitigation_id"]:
            alt = {**plan, sid: m}
            if R.feasible(c, caps, alt):
                assert R.objective(c, alt) >= base - 1e-9, (sid, m)


def test_repair_always_reaches_feasibility(tinyds):
    T, out, pol = tinyds
    sids = list(out["Shortage"]["shortage_id"])
    c, caps = R.candidates(T, out, pol, sids)
    tight = {k: 0.0 for k in caps}  # every shared resource exhausted
    p = R._repair(c, tight, R.independent_picks(c))
    assert R.feasible(c, tight, p)


# ------------------------------------------------------------------ verification is a recalculation
def test_verified_gaps_come_from_the_recalculated_plan(conflict, starter):
    T, out, pol = starter
    sids, res = conflict
    r = res["results"]["Coordinated plan"]
    out2 = r["out"]
    assert out2 is not out
    for row in r["per_shortage"].itertuples():
        st, en = R._gaps(out, row.shortage_id)
        assert row.gap_after == R._pair_gap(out2, row.sku_id, row.location_id, st, en)


def test_independent_plan_side_effects_are_found_by_replanning(conflict, starter):
    T, out, pol = starter
    sids, res = conflict
    ind = res["results"]["Independent best picks"]
    assert ind["summary"]["side_effect_shortages"] >= 1  # the over-drawn donor goes short in the recalculated plan
    don = [k for k in res["usage"]["Independent best picks"].query("over")["res_key"] if k[0] == "DON"]
    if don:
        _, sku, loc = don[0]
        se = ind["side_effects"]
        assert ((se["sku_id"] == sku) & (se["location_id"] == loc)).any()


def test_no_action_row_matches_the_baseline(conflict, starter):
    T, out, pol = starter
    sids, res = conflict
    row = res["comparison"].iloc[0]
    assert row["plan"].startswith("Current") and row["gap_after"] == int(out["Shortage"].set_index("shortage_id").loc[sids, "shortage_qty"].sum())


def test_planning_never_mutates_the_baseline(starter):
    T, out, pol = starter
    before, out_before = _fp(T), _fp(out)
    sids = list(out["Shortage"].sort_values("priority_rank")["shortage_id"].head(4))
    R.plan_recovery(T, out, pol, sids)
    assert _fp(T) == before and _fp(out) == out_before


# ------------------------------------------------------------------ explanations
def test_every_candidate_is_explained(conflict):
    sids, res = conflict
    ex, c = res["explanation"], res["candidates"]
    assert set(ex["mitigation_id"]) == set(c["mitigation_id"])
    sel = ex[ex["decision"] == "SELECTED"]
    assert set(sel["shortage_id"]) == set(sids) and sel["reason"].str.len().gt(20).all()
    plan = res["plans"]["Coordinated plan"]
    assert dict(zip(sel["shortage_id"], sel["mitigation_id"])) == plan


def test_cheaper_rejected_options_are_explained_by_a_capacity_conflict(conflict):
    sids, res = conflict
    ex = res["explanation"]
    jsel = ex[ex["decision"] == "SELECTED"].set_index("shortage_id")["objective"]
    cheaper = ex[(ex["decision"] != "SELECTED") & (ex["objective"] < ex["shortage_id"].map(jsel) - 1e-6)]
    assert len(cheaper) >= 1 and cheaper["reason"].str.startswith("would exceed").all()


# ------------------------------------------------------------------ UI flow
APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    if not (STARTER / "manifest.json").exists():
        pytest.skip("committed starter dataset not present")
    r = tmp_path_factory.mktemp("rp_root")
    shutil.copytree(STARTER, r / "starter")
    return r


def _app(root, tmp, role="PLANNER", user="planner"):
    from streamlit.testing.v1 import AppTest
    os.environ.update(ORYVA_DATA_ROOT=str(root), ORYVA_DEFAULT_DATASET="starter", ORYVA_STATE_DB=str(tmp / "s.sqlite"), ORYVA_LOG_DIR=str(tmp / "l"))
    at = AppTest.from_file(APP, default_timeout=600)
    at.session_state["user"] = {"username": user, "role": role, "display_name": user, "supplier_id": None}
    at.session_state["nav"] = "Recovery planner"
    return at


def test_recovery_page_build_verify_and_approve(root, tmp_path):
    at = _app(root, tmp_path).run()
    assert not at.exception and not at.error
    at.button(key="rp_run").click().run()
    assert not at.exception and not at.error
    s = State(tmp_path / "s.sqlite")
    assert any(r["action"] == "recovery.verified" for r in s.audit_rows())
    ok = at.button(key="rp_ok")
    assert not ok.disabled
    ok.click().run()
    assert not at.exception and not at.error
    acts = [r["action"] for r in s.audit_rows()]
    assert "recovery.approved" in acts and acts.count("mitigation.approved") >= 1 and s.verify_chain()[0]


def test_analyst_can_verify_but_not_approve(root, tmp_path):
    at = _app(root, tmp_path, "LOGISTICS_ANALYST", "analyst").run()
    at.button(key="rp_run").click().run()
    assert not at.exception and at.button(key="rp_ok").disabled
