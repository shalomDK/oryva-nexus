"""Decision Room: verify mitigation options by re-running the planning engine with the option applied.

For one shortage, every candidate option is applied to COPIES of the input tables (never the baseline) and the planning
engine is re-run.  The result shows what really happens: the target shortage's gap before and after, side effects
elsewhere in the network (e.g. a transfer donor or a component going short), service-level / value-at-risk deltas and
supplier capacity use.  The engine's own estimate (fill rate, cost) is shown next to the replan-verified outcome.

How each option type is represented in the input tables (also listed as assumptions in every result):
* NEW_PO / ALT_SUPPLIER_PO -> a new PLANNED purchase order (ordered at as-of, arriving on the option's earliest date)
* EXPEDITE_PO              -> the referenced order's promised/ETA date moved to the option's earliest arrival date
* PRODUCTION_REPLAN        -> an extra PLANNED production order; the engine re-applies work-centre hour limits and BOM
                              explosion, so capacity cuts and component demand are real
* LOCATION_TRANSFER        -> a planned movement: outflow from the donor in week 1, receipt at the shortage location in
                              the arrival week
* SUBSTITUTE_SKU           -> a planned movement: the substitute SKU is consumed at the same location from the shortage
                              week and covers the stated quantity of the original SKU
* PARTIAL_FILL_BACKORDER   -> no supply change
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .. import weeks as W
from ..planning import run_plan
from .scenario import compare

MOVEMENT_COLS = ["from_sku_id", "from_location_id", "to_sku_id", "to_location_id", "out_qty", "out_week", "in_qty", "in_week", "mitigation_id"]


def _next_id(series: pd.Series, prefix: str) -> str:
    n = series.str.extract(r"(\d+)$")[0].astype(int).max() + 1
    return f"{prefix}{n:06d}"


def _add_movement(T: dict, row: list) -> pd.DataFrame:
    """Append a planned movement to any movements already applied (so several options can be stacked)."""
    new = pd.DataFrame([row], columns=MOVEMENT_COLS)
    prev = T.get("PlannedMovement")
    return new if prev is None or len(prev) == 0 else pd.concat([prev, new], ignore_index=True)


def apply_option(T: dict, out: dict, mitigation_id: str) -> tuple[dict, str, list[str]]:
    """Return (T2, description, assumptions).  Only the tables that change are copied; T is never mutated."""
    mo = out["MitigationOption"].set_index("mitigation_id")
    if mitigation_id not in mo.index:
        raise KeyError(mitigation_id)
    o = mo.loc[mitigation_id]
    sh = out["Shortage"].set_index("shortage_id").loc[o["shortage_id"]]
    sku, loc = sh["sku_id"], sh["location_id"]
    as_of = str(T["Inventory"]["as_of_date"].iloc[0])
    p0 = W.week_of(sh["need_by_date"])
    T2 = dict(T)
    t = o["option_type"]
    assumptions = []
    if t in ("NEW_PO", "ALT_SUPPLIER_PO"):
        po = T["PurchaseOrder"]
        arr = o["earliest_arrival_date"]
        base_uom = T["SKU"].set_index("sku_id").at[sku, "base_uom"]
        row = {c: None for c in po.columns}
        row.update(po_id=_next_id(po["po_id"], "PO-2026-"), supplier_id=o["supplier_id"], sku_id=sku, ship_to_location_id=loc, carrier_id=None,
                   created_date=as_of, order_date=as_of, requested_date=arr, promised_date=arr, eta_date=arr, actual_receipt_date=None,
                   order_qty=int(o["qty"]), order_uom=base_uom, qty_base=int(o["qty"]), unit_price=float(o["unit_cost"]),
                   total_cost=round(int(o["qty"]) * float(o["unit_cost"]), 2), supplier_ref_no=f"SIM-{mitigation_id}", status="PLANNED")
        T2["PurchaseOrder"] = pd.concat([po, pd.DataFrame([row])], ignore_index=True)
        desc = f"new planned order {row['po_id']} for {int(o['qty']):,} units from {o['supplier_id']}, ordered {as_of}, arriving {arr}"
        assumptions.append("the supplier confirms the order on the as-of date and delivers on the option's earliest arrival date")
    elif t == "EXPEDITE_PO":
        po = T["PurchaseOrder"].copy()
        m = po["po_id"] == o["ref_po_id"]
        old = po.loc[m, "eta_date"].iloc[0]
        po.loc[m, ["promised_date", "eta_date"]] = o["earliest_arrival_date"]
        T2["PurchaseOrder"] = po
        desc = f"order {o['ref_po_id']} expedited from ETA {old} to {o['earliest_arrival_date']}"
        assumptions.append("the carrier/supplier achieves the expedited date at the policy premium")
    elif t == "PRODUCTION_REPLAN":
        pp = T["ProductionPlan"]
        bom = T["BillOfMaterial"].set_index("parent_sku_id")
        mine = pp[(pp["sku_id"] == sku) & (pp["location_id"] == loc)]
        wc = mine["work_center_id"].iloc[0] if len(mine) else None
        if wc is None:
            raise ValueError("no work centre for this SKU-location")
        w = W.week_of(o["earliest_arrival_date"])
        qty = int(o["qty"])
        row = {"production_plan_id": _next_id(pp["production_plan_id"], "PP-2026-"), "sku_id": sku, "location_id": loc, "work_center_id": wc,
               "bom_id": bom.at[sku, "bom_id"], "iso_week": W.label(w), "week_start_date": W.week_start_s(w), "planned_qty": qty,
               "required_hours": round(qty * float(bom.at[sku, "run_time_hours_per_unit"]), 4), "status": "PLANNED"}
        T2["ProductionPlan"] = pd.concat([pp, pd.DataFrame([row])], ignore_index=True)
        desc = f"extra production order {row['production_plan_id']} for {qty:,} units in {W.label(w)} on {wc}"
        assumptions.append("work-centre hour limits and BOM component demand are re-applied by the planning engine")
    elif t == "LOCATION_TRANSFER":
        arr_w = W.week_of(o["earliest_arrival_date"])
        T2["PlannedMovement"] = _add_movement(T, [sku, o["source_location_id"], sku, loc, int(o["qty"]), 1, int(o["covered_qty"]), arr_w, mitigation_id])
        desc = f"transfer of {int(o['qty']):,} units from {o['source_location_id']} (ships {W.label(1)}) to {loc} (arrives {W.label(arr_w)})"
        assumptions.append("stock leaves the donor in the first week and arrives at the shortage location in the arrival week")
    elif t == "SUBSTITUTE_SKU":
        T2["PlannedMovement"] = _add_movement(T, [o["alt_sku_id"], loc, sku, loc, int(o["qty"]), p0, int(o["covered_qty"]), p0, mitigation_id])
        desc = f"{int(o['qty']):,} units of substitute {o['alt_sku_id']} used at {loc} from {W.label(p0)} to cover {int(o['covered_qty']):,} units of {sku}"
        assumptions.append("customers accept the substitute at the approved substitution ratio from the first shortage week")
    else:
        desc = "accept the backorder: no supply change"
        assumptions.append("no supply action; the shortage remains and a backorder penalty applies")
    return T2, desc, assumptions


def _pair_series(out: dict, sku: str, loc: str) -> pd.DataFrame:
    pb = out["ProjectedBalance"]
    d = pb[(pb["sku_id"] == sku) & (pb["location_id"] == loc)].sort_values("week_start_date")
    return d[["iso_week", "closing_qty", "safety_stock_qty", "scheduled_receipts_qty", "dependent_demand_qty", "production_receipts_qty"]].reset_index(drop=True)


def replan(T: dict, out: dict, policy: dict, mitigation_id: str, seed: int = 0) -> dict:
    """Apply one option and re-run the planning engine.  Returns the verified effect on the target shortage and the network."""
    mo = out["MitigationOption"].set_index("mitigation_id")
    o = mo.loc[mitigation_id]
    sid = o["shortage_id"]
    sh = out["Shortage"].set_index("shortage_id").loc[sid]
    sku, loc = sh["sku_id"], sh["location_id"]
    T2, desc, assumptions = apply_option(T, out, mitigation_id)
    out2, _ = run_plan(T2, policy, seed, "decision", run_id="RUN-0001")
    before, after = _pair_series(out, sku, loc), _pair_series(out2, sku, loc)
    st, en = W.week_of(sh["need_by_date"]), W.week_of(sh["need_by_date"]) + int(sh["episode_weeks"]) - 1
    win = slice(st - 1, en)
    gap_b = int(max(0, (before["safety_stock_qty"] - before["closing_qty"]).iloc[win].max()))
    gap_a = int(max(0, (after["safety_stock_qty"] - after["closing_qty"]).iloc[win].max()))
    so_b = int((before["closing_qty"].iloc[win] < 0).sum())
    so_a = int((after["closing_qty"].iloc[win] < 0).sum())
    cmp = compare(out, out2)
    det = cmp["detail"]
    side = det[~((det["sku_id"] == sku) & (det["location_id"] == loc))]
    harm = side[side["change"].isin(["NEW", "WORSE"])]
    k = {r.metric: r for r in cmp["kpis"].itertuples()}
    if gap_b == 0:
        verdict = "NO GAP"
    elif gap_a == 0:
        verdict = "RESOLVED"
    elif gap_a < gap_b:
        verdict = "REDUCED"
    elif gap_a == gap_b:
        verdict = "UNCHANGED"
    else:
        verdict = "WORSE"
    cap = None
    if o["option_type"] in ("NEW_PO", "ALT_SUPPLIER_PO"):
        fam = T["SKU"].set_index("sku_id").at[sku, "product_family"]
        ws = pd.Timestamp(str(T["Inventory"]["as_of_date"].iloc[0]))
        ws = (ws - pd.Timedelta(days=ws.weekday())).strftime("%Y-%m-%d")

        def util(o_):
            led = o_["SupplierCapacityLedger"]
            r = led[(led["supplier_id"] == o["supplier_id"]) & (led["product_family"] == fam) & (led["week_start_date"] == ws)]
            return (float(r["utilisation_pct"].iloc[0]), int(r["committed_qty"].iloc[0]), int(r["capacity_qty"].iloc[0])) if len(r) else (0.0, 0, None)
        cap = {"supplier_id": o["supplier_id"], "product_family": fam, "week": ws, "before": util(out), "after": util(out2)}
    return {
        "mitigation_id": mitigation_id, "shortage_id": sid, "option_type": o["option_type"], "description": desc, "assumptions": assumptions,
        "sku_id": sku, "location_id": loc, "window": (W.label(st), W.label(en)), "gap_before": gap_b, "gap_after": gap_a,
        "gap_closed_pct": round(100.0 * (gap_b - gap_a) / gap_b, 2) if gap_b else 100.0, "stockout_weeks_before": so_b, "stockout_weeks_after": so_a,
        "verdict": verdict, "side_effects": harm[["sku_id", "location_id", "first_short_week", "shortage_qty", "primary_cause_code", "change"]].reset_index(drop=True),
        "side_effect_units": int(harm["shortage_qty"].sum()), "improved_elsewhere": int(side["change"].isin(["RESOLVED", "BETTER"]).sum()),
        "service_level_delta": round(float(k["service_level_pct"].delta), 3), "shortage_units_delta": int(k["shortage_units"].delta),
        "value_at_risk_delta": round(float(k["value_at_risk"].delta), 2), "series_before": before, "series_after": after, "capacity": cap,
        "engine_cost": float(o["total_cost"]), "engine_fill_pct": float(o["fill_rate_pct"]), "engine_rank": int(o["rank"]),
        "engine_recommended": bool(o["is_recommended"]), "approval_role": o["approval_required_role"],
    }


VERDICT_ORDER = {"RESOLVED": 0, "NO GAP": 0, "REDUCED": 1, "UNCHANGED": 2, "WORSE": 3}


def decision_matrix(T: dict, out: dict, policy: dict, shortage_id: str, max_options: int = 4, seed: int = 0) -> dict:
    """Replan every recommendable option (top `max_options` by engine rank, plus the backorder baseline) and rank them by
    the VERIFIED outcome: gap closed (desc), side-effect units (asc), engine incremental cost (asc)."""
    mo = out["MitigationOption"]
    opts = mo[(mo["shortage_id"] == shortage_id) & (mo["is_recommendable"] == 1)].sort_values("rank")
    chosen = list(opts[opts["option_type"] != "PARTIAL_FILL_BACKORDER"]["mitigation_id"].head(max_options))
    chosen += list(opts[opts["option_type"] == "PARTIAL_FILL_BACKORDER"]["mitigation_id"].head(1))
    results = {m: replan(T, out, policy, m, seed) for m in chosen}
    rows = []
    for m, r in results.items():
        rows.append({"mitigation_id": m, "option_type": r["option_type"], "engine_rank": r["engine_rank"], "engine_recommended": r["engine_recommended"],
                     "engine_fill_pct": r["engine_fill_pct"], "engine_cost": r["engine_cost"], "gap_before": r["gap_before"], "gap_after": r["gap_after"],
                     "gap_closed_pct": r["gap_closed_pct"], "verdict": r["verdict"], "side_effect_shortages": len(r["side_effects"]),
                     "side_effect_units": r["side_effect_units"], "service_level_delta": r["service_level_delta"], "shortage_units_delta": r["shortage_units_delta"],
                     "approval_role": r["approval_role"], "action": r["description"]})
    t = pd.DataFrame(rows)
    if t.empty:
        return {"table": t, "results": results, "best": None, "engine_pick": None, "agrees": None}
    t["_v"] = t["verdict"].map(VERDICT_ORDER)
    t = t.sort_values(["_v", "gap_after", "side_effect_units", "engine_cost", "mitigation_id"]).drop(columns="_v").reset_index(drop=True)
    t.insert(0, "verified_rank", range(1, len(t) + 1))
    best = t.iloc[0]["mitigation_id"]
    eng = t[t["engine_recommended"]]["mitigation_id"]
    eng = eng.iloc[0] if len(eng) else None
    return {"table": t, "results": results, "best": best, "engine_pick": eng, "agrees": best == eng}


def evidence(T: dict, out: dict, shortage_id: str) -> dict:
    """Source records behind a shortage: cause rows plus the purchase orders / events / forecast rows they cite."""
    cs = out["ShortageCause"][out["ShortageCause"]["shortage_id"] == shortage_id]
    po_ids = list(cs.loc[cs["source_table"] == "PurchaseOrder", "source_id"])
    fd_ids = list(cs.loc[cs["source_table"] == "ForecastDemand", "source_id"])
    pp_ids = list(cs.loc[cs["source_table"] == "ProductionPlan", "source_id"])
    po = T["PurchaseOrder"][T["PurchaseOrder"]["po_id"].isin(po_ids)]
    ev = T["PurchaseOrderEvent"][T["PurchaseOrderEvent"]["po_id"].isin(po_ids)]
    te = T["TransportEvent"][T["TransportEvent"]["po_id"].isin(po_ids)]
    fd = T["ForecastDemand"][T["ForecastDemand"]["demand_id"].isin(fd_ids)]
    pp = T["ProductionPlan"][T["ProductionPlan"]["production_plan_id"].isin(pp_ids)]
    sh = out["Shortage"].set_index("shortage_id").loc[shortage_id]
    inv = T["Inventory"][(T["Inventory"]["sku_id"] == sh["sku_id"]) & (T["Inventory"]["location_id"] == sh["location_id"])]
    dq = out["DataQualityFinding"]
    flags = dq[dq["related_record_ids"].fillna("").str.contains(shortage_id, regex=False) | dq["record_id"].isin(po_ids)]
    return {"causes": cs, "purchase_orders": po, "po_events": ev, "transport_events": te, "forecast_rows": fd, "production_plans": pp,
            "inventory": inv, "findings": flags}


POLICY_KEYS = ["expedite_premium_pct", "expedite_premium_cap_pct", "freight_pct", "transfer_freight_pct", "transfer_lead_days", "holding_cost_pct_excess",
               "backorder_cost_pct_per_week", "approval_spend_threshold", "production_frozen_weeks"]


def _md(df: pd.DataFrame, cols: list[str]) -> str:
    if df is None or len(df) == 0:
        return "_none_"
    d = df[cols]
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "\n".join("| " + " | ".join("" if (isinstance(v, float) and math.isnan(v)) or v is None else (f"{v:,.2f}" if isinstance(v, float) else str(v)) for v in r) + " |"
                            for r in d.itertuples(index=False))


def case_file(T: dict, out: dict, policy: dict, shortage_id: str, matrix: dict, chosen: str, checks: list[dict], as_of: str) -> str:
    """Self-contained Markdown record of the decision: problem, evidence, assumptions, options compared, verified outcome."""
    sh = out["Shortage"].set_index("shortage_id").loc[shortage_id]
    ev = evidence(T, out, shortage_id)
    r = matrix["results"][chosen]
    L = [f"# Decision case file - {shortage_id}", "",
         f"As of {as_of}. SKU {sh['sku_id']} at {sh['location_id']}: {sh['shortage_type']} of {int(sh['shortage_qty']):,} units from {sh['first_short_week']} "
         f"for {int(sh['episode_weeks'])} week(s); value at risk ${float(sh['value_at_risk']):,.2f}; priority rank {int(sh['priority_rank'])}; status {sh['status']}; "
         f"data-quality flag {sh['data_quality_flag']}.", "",
         "## 1. Why the shortage occurs (engine cause attribution)", _md(ev["causes"], ["cause_code", "contribution_qty", "source_table", "source_id", "explanation"]), "",
         "### Source records cited", "Purchase orders:", _md(ev["purchase_orders"], ["po_id", "supplier_id", "status", "requested_date", "promised_date", "eta_date", "qty_base"]),
         "", "Order events:", _md(ev["po_events"], ["po_id", "event_type", "event_date", "to_status", "delay_days", "reason_code"]),
         "", "Forecast rows:", _md(ev["forecast_rows"], ["demand_id", "forecast_qty", "demand_driver"]),
         "", "Production plans:", _md(ev["production_plans"], ["production_plan_id", "iso_week", "planned_qty", "status"]),
         "", "Inventory snapshot:", _md(ev["inventory"], ["inventory_id", "on_hand_qty", "allocated_qty", "available_qty", "safety_stock_qty"]),
         "", "Related data-quality findings:", _md(ev["findings"], ["finding_id", "issue_type", "record_id"]), "",
         "## 2. Options compared by re-running the planning engine",
         _md(matrix["table"], ["verified_rank", "mitigation_id", "option_type", "engine_rank", "engine_fill_pct", "engine_cost", "gap_before", "gap_after", "verdict",
                               "side_effect_shortages", "side_effect_units", "service_level_delta"]), "",
         f"Verified best: **{matrix['best']}**; engine recommendation: **{matrix['engine_pick']}** ({'agree' if matrix['agrees'] else 'differ'}).", "",
         f"## 3. Chosen option: {chosen} ({r['option_type']})", f"Action: {r['description']}.", "",
         f"Verified effect: gap over {r['window'][0]}-{r['window'][1]} {r['gap_before']:,} -> {r['gap_after']:,} units ({r['verdict']}); stock-out weeks "
         f"{r['stockout_weeks_before']} -> {r['stockout_weeks_after']}; network shortage units {r['shortage_units_delta']:+,}; service level {r['service_level_delta']:+.3f} pts; "
         f"{len(r['side_effects'])} side-effect shortage(s) elsewhere ({r['side_effect_units']:,} units).", "",
         "Side effects:", _md(r["side_effects"], ["sku_id", "location_id", "first_short_week", "shortage_qty", "change"]), "",
         "Assumptions: " + "; ".join(r["assumptions"]) + ".", "",
         "## 4. Validation against source tables", _md(pd.DataFrame(checks), ["check", "ok", "detail"]) if checks else "_none_", "",
         "## 5. Policy parameters used", "\n".join(f"- {k}: {policy.get(k)}" for k in POLICY_KEYS), ""]
    return "\n".join(L) + "\n"
