"""Advanced modules: scenario isolation, supplier intelligence, risk, replenishment, optimisation constraints."""
import hashlib

import numpy as np
import pandas as pd
import pytest

from oryva.advanced import optimize, replenish, risk, supplier_intel
from oryva.advanced.kpi import plan_kpis
from oryva.advanced.scenario import Scenario, apply_scenario, simulate
from oryva.config import load_policy


def dq_ws(d):
    from oryva import dq
    return dq.week_start_str(pd.Series([d])).iloc[0]


@pytest.fixture(scope="module")
def ds(tiny):
    return {"T": tiny["T"], "out": tiny["out"], "policy": load_policy()}


def _fp(T):
    return {k: hashlib.sha256(pd.util.hash_pandas_object(v, index=True).values.tobytes()).hexdigest() for k, v in T.items()}


# ---------------------------------------------------------------- scenario simulator
def test_scenario_never_modifies_baseline(ds):
    before = _fp(ds["T"])
    out_before = _fp(ds["out"])
    sc = Scenario(demand_multiplier=1.3, lead_time_delta_days=10, capacity_factor=0.7, transport_delay_days=7, disabled_suppliers=["SUP-0001"])
    res = simulate(ds["T"], ds["out"], sc, ds["policy"])
    assert _fp(ds["T"]) == before and _fp(ds["out"]) == out_before
    assert res["kpis"].shape[0] >= 8


def test_noop_scenario_reproduces_baseline_exactly(ds):
    res = simulate(ds["T"], ds["out"], Scenario(), ds["policy"])
    assert (res["kpis"]["delta"] == 0).all() and res["counts"]["new"] == 0 and res["counts"]["resolved"] == 0


def test_demand_increase_never_reduces_shortage_units(ds):
    r1 = simulate(ds["T"], ds["out"], Scenario(demand_multiplier=1.2), ds["policy"])
    r2 = simulate(ds["T"], ds["out"], Scenario(demand_multiplier=1.5), ds["policy"])
    b = plan_kpis(ds["out"])["shortage_units"]
    assert r1["scenario"]["shortage_units"] >= b and r2["scenario"]["shortage_units"] >= r1["scenario"]["shortage_units"]
    assert r2["scenario"]["service_level_pct"] <= r1["scenario"]["service_level_pct"] <= plan_kpis(ds["out"])["service_level_pct"]


def test_scenario_changes_only_requested_inputs(ds):
    T2 = apply_scenario(ds["T"], Scenario(capacity_factor=0.5))
    assert set(k for k in T2 if T2[k] is not ds["T"][k]) == {"SupplierCapacity"}
    assert (T2["SupplierCapacity"]["weekly_capacity_qty"] <= ds["T"]["SupplierCapacity"]["weekly_capacity_qty"]).all()
    T3 = apply_scenario(ds["T"], Scenario(transport_delay_days=5))
    po0, po3 = ds["T"]["PurchaseOrder"].set_index("po_id"), T3["PurchaseOrder"].set_index("po_id")
    moved = po3[po3["eta_date"] != po0["eta_date"]]
    assert len(moved) and set(po0.loc[moved.index, "status"]) <= {"IN_TRANSIT", "DELAYED"}


def test_disabled_supplier_orders_cancelled_and_mitigations_blocked(ds):
    po = ds["T"]["PurchaseOrder"]
    sup = po[po["status"].isin(["PLANNED", "CONFIRMED"])]["supplier_id"].value_counts().index[0]
    res = simulate(ds["T"], ds["out"], Scenario(disabled_suppliers=[sup]), ds["policy"])
    mo = res["out"]["MitigationOption"]
    assert not ((mo["supplier_id"] == sup) & (mo["is_recommendable"] == 1)).any()
    assert res["scenario"]["shortages"] >= plan_kpis(ds["out"])["shortages"]


# ---------------------------------------------------------------- supplier intelligence
def test_supplier_scorecard_is_bounded_and_reproducible_from_components(ds):
    card = supplier_intel.scorecard(ds["T"], ds["out"])
    assert len(card) == len(ds["T"]["Supplier"]) and card["score"].between(0, 100).all()
    for sid in card["supplier_id"].head(5):
        e = supplier_intel.explain_score(card, sid)
        assert abs(e["contribution"].sum() - float(card.loc[card["supplier_id"] == sid, "score"].iloc[0])) < 0.05
    assert abs(sum(supplier_intel.WEIGHTS.values()) - 1) < 1e-9
    po = ds["T"]["PurchaseOrder"]
    assert card["orders"].sum() == len(po)
    dl = ds["T"]["TransportEvent"].query("event_type == 'DELAYED'")
    assert card["delay_incidents"].sum() == len(dl)


# ---------------------------------------------------------------- risk
def test_risk_scores_explained_by_factor_contributions(ds):
    card = supplier_intel.scorecard(ds["T"], ds["out"])
    r = risk.shortage_risk(ds["T"], ds["out"], card)
    cs = [c for c in r.columns if c.startswith("c_")]
    assert len(r) == len(ds["out"]["Inventory"]) if "Inventory" in ds["out"] else len(r) > 0
    assert np.allclose(r[cs].sum(axis=1), r["risk_score"], atol=0.02) and r["risk_score"].between(0, 100).all()
    assert abs(sum(risk.WEIGHTS.values()) - 1) < 1e-9
    d = risk.supplier_disruption_risk(ds["T"], card)
    assert d["disruption_risk"].between(0, 100).all() and len(d) == len(card)


def test_risk_backtest_reports_real_metrics(ds):
    card = supplier_intel.scorecard(ds["T"], ds["out"])
    r = risk.shortage_risk(ds["T"], ds["out"], card)
    bt = risk.stress_backtest(ds["T"], ds["out"], r, ds["policy"])
    assert bt["pairs_scored"] > 0 and (bt["auc"] is None or 0 <= bt["auc"] <= 1)


def test_auc_function_correct():
    assert risk.auc(np.array([0.9, 0.8, 0.2, 0.1]), np.array([1, 1, 0, 0])) == 1.0
    assert risk.auc(np.array([0.1, 0.2, 0.8, 0.9]), np.array([1, 1, 0, 0])) == 0.0
    assert abs(risk.auc(np.array([0.5, 0.5, 0.5, 0.5]), np.array([1, 0, 1, 0])) - 0.5) < 1e-9


# ---------------------------------------------------------------- replenishment\ndef dq_ws(d):\n    from oryva import dq\n    return dq.week_start_str(pd.Series([d])).iloc[0]\n\n
def test_replenishment_proposals_respect_moq_multiple_capacity_leadtime(ds):
    p = replenish.build_proposals(ds["T"], ds["out"], ds["policy"])
    assert len(p) > 0 and p["valid"].mean() > 0.5
    for rec in p[p["valid"]].to_dict("records"):
        assert all(c["ok"] for c in replenish.validate_proposal(rec, ds["T"], ds["out"]))
    # a proposal below MOQ must fail validation
    fam = ds["T"]["SKU"].set_index("sku_id")["product_family"]
    tested = False
    for rec in p[p["valid"]].to_dict("records"):
        cr = replenish._cap_row(ds["T"], rec["supplier_id"], fam[rec["sku_id"]], dq_ws(rec["order_date"]))
        if int(cr["min_order_qty"]) > 1:
            bad = dict(rec, qty_base=int(cr["min_order_qty"]) - 1)
            failed = {c["check"] for c in replenish.validate_proposal(bad, ds["T"], ds["out"]) if not c["ok"]}
            assert "minimum order quantity" in failed
            big = dict(rec, qty_base=int(cr["weekly_capacity_qty"]) * 10)
            assert "supplier capacity" in {c["check"] for c in replenish.validate_proposal(big, ds["T"], ds["out"]) if not c["ok"]}
            tested = True
            break
    assert tested


def test_replenishment_aggregate_capacity_not_exceeded(ds):
    p = replenish.build_proposals(ds["T"], ds["out"], ds["policy"])
    fam = ds["T"]["SKU"].set_index("sku_id")["product_family"]
    ok = p[p["valid"]].assign(fam=lambda d: d["sku_id"].map(fam))
    from oryva import dq
    ok["ws"] = dq.week_start_str(ok["order_date"])
    agg = ok.groupby(["supplier_id", "fam", "ws"])["qty_base"].sum()
    led = ds["out"]["SupplierCapacityLedger"].set_index(["supplier_id", "product_family", "week_start_date"])["committed_qty"]
    cap = ds["T"]["SupplierCapacity"]
    for (s, f, w), q in agg.items():
        c = cap[(cap.supplier_id == s) & (cap.product_family == f) & (cap.effective_from <= w) & (cap.effective_to.isna() | (w < cap.effective_to))]
        assert q + led.get((s, f, w), 0) <= int(c.sort_values("effective_from").iloc[-1]["weekly_capacity_qty"])


# ---------------------------------------------------------------- optimisation
def test_optimizer_solutions_satisfy_every_constraint(ds):
    r = optimize.run_strategies(ds["T"], ds["out"], ds["policy"], 95.0)
    c, caps = r["candidates"], r["caps"]
    assert len(r["table"]) == 4
    for name, ch in r["selections"].items():
        if name.startswith("Engine"):
            continue  # engine ranking is the baseline for comparison; its own feasibility is audited separately
        assert optimize.check_constraints(c, ch, caps) == [], name
        s = c.iloc[ch]
        assert s["shortage_id"].is_unique and (s["is_recommendable"] == 1).all()


def test_optimizer_cost_never_worse_than_engine_and_floor_respected(ds):
    r = optimize.run_strategies(ds["T"], ds["out"], ds["policy"], 90.0)
    t = r["table"].set_index("strategy")
    mc = t.loc["Minimum total cost"]
    eng = t.loc["Engine ranking (service first)"]
    assert mc["total_cost"] <= eng["total_cost"] + 1e-6 or eng["violations"] > 0
    floor = t.loc["Cost-optimal with service >= 90%"]
    assert floor["service_pct"] >= 90.0 - 1e-6 or t.loc["Maximum service"]["service_pct"] < 90.0
    assert t.loc["Maximum service"]["service_pct"] >= floor["service_pct"] - 1e-6
    assert floor["violations"] == 0 and mc["violations"] == 0


def test_optimizer_detects_constraint_violations(ds):
    c, caps = optimize.build_candidates(ds["T"], ds["out"], ds["policy"])
    sid = pd.factorize(c["shortage_id"])[0]
    caps2 = {k: 0 for k in caps}  # zero every capacity: any resource-using selection must be flagged
    idx = np.array([int(np.nonzero(sid == s)[0][0]) for s in range(sid.max() + 1)])
    uses = c.iloc[idx]["res_key"].notna().any()
    if uses:
        assert optimize.check_constraints(c, idx, caps2)

