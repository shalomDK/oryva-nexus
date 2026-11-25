"""Hand-computed golden example for the planning engine (documented in README 'worked example')."""
import numpy as np
import pandas as pd

from oryva.config import load_policy
from oryva.planning import run_plan

PO_ID = "PO-2026-999990"


def _golden(tiny):
    T = {k: v.copy() for k, v in tiny["T"].items()}
    sku_t = T["SKU"].set_index("sku_id")
    inv = T["Inventory"]
    cand = inv[inv["sku_id"].map(sku_t["sku_type"]) == "FINISHED_BUY"].iloc[0]
    s, l = cand["sku_id"], cand["location_id"]
    # demand W01..W03 = 40, 90, 30 ; zero afterwards
    fd = T["ForecastDemand"]
    m = (fd["sku_id"] == s) & (fd["location_id"] == l)
    q = np.zeros(m.sum(), dtype=int)
    q[:3] = [40, 90, 30]
    fd.loc[m, "forecast_qty"] = q
    fd.loc[m, "demand_driver"] = "BASELINE"
    # inventory: on-hand 100, nothing allocated/held, safety stock 20
    i = (inv["sku_id"] == s) & (inv["location_id"] == l)
    inv.loc[i, ["on_hand_qty", "allocated_qty", "quality_hold_qty", "available_qty", "safety_stock_qty"]] = [100, 0, 0, 100, 20]
    # replace all inbound for the pair by ONE PO: promised W02 (2026-01-05) but delayed one week -> ETA W03
    po = T["PurchaseOrder"]
    tmpl = po.iloc[0].copy()
    po = po[~((po["sku_id"] == s) & (po["ship_to_location_id"] == l))]
    sup = T["SKUSupplier"].set_index("sku_id").loc[s]
    sup = sup["supplier_id"] if isinstance(sup, pd.Series) else sup["supplier_id"].iloc[0]
    row = tmpl.copy()
    row["po_id"], row["sku_id"], row["supplier_id"], row["ship_to_location_id"] = PO_ID, s, sup, l
    row["order_uom"], row["order_qty"], row["qty_base"] = sku_t.at[s, "base_uom"], 80, 80
    row["requested_date"] = row["promised_date"] = "2026-01-05"
    row["eta_date"], row["order_date"], row["created_date"] = "2026-01-12", "2025-12-01", "2025-11-20"
    row["actual_receipt_date"], row["status"], row["supplier_ref_no"], row["carrier_id"] = None, "IN_TRANSIT", "SR-GOLDEN", None
    T["PurchaseOrder"] = pd.concat([po, pd.DataFrame([row])], ignore_index=True)
    return T, s, l


def test_projected_balance_shortage_cause_and_priority_by_hand(tiny):
    T, s, l = _golden(tiny)
    out, ctx = run_plan(T, load_policy(), 1, "golden")
    pb = out["ProjectedBalance"]
    pb = pb[(pb["sku_id"] == s) & (pb["location_id"] == l)].sort_values("week_start_date")
    # opening 100 -> W01 60 ; W02 60-90 = -30 ; W03 -30+80-30 = 20 ; then 20 forever
    assert pb["closing_qty"].tolist()[:4] == [60, -30, 20, 20]
    assert pb["scheduled_receipts_qty"].tolist()[:4] == [0, 0, 80, 0]
    sh = out["Shortage"]
    sh = sh[(sh["sku_id"] == s) & (sh["location_id"] == l)]
    assert len(sh) == 1
    r = sh.iloc[0]
    assert (r["first_short_week"], r["last_short_week"], r["peak_short_week"]) == ("2026W01", "2026W02", "2026W02") or \
        (r["first_short_week"], r["peak_short_week"]) == ("2026W02", "2026W02")
    assert r["shortage_qty"] == 50 and r["shortage_type"] == "STOCKOUT"
    cs = out["ShortageCause"]
    cs = cs[cs["shortage_id"] == r["shortage_id"]]
    assert cs["contribution_qty"].sum() == 50
    assert cs.iloc[0]["cause_code"] in ("INBOUND_LATE_TRANSPORT", "INBOUND_LATE_SUPPLIER")
    assert cs.iloc[0]["source_id"] == PO_ID


def test_mitigation_cost_and_service_are_computed_from_rules(tiny):
    T, s, l = _golden(tiny)
    out, _ = run_plan(T, load_policy(), 1, "golden")
    sid = out["Shortage"].query("sku_id == @s and location_id == @l")["shortage_id"].iloc[0]
    mo = out["MitigationOption"].query("shortage_id == @sid")
    bo = mo[mo["option_type"] == "PARTIAL_FILL_BACKORDER"].iloc[0]
    # backorder cost = 50 units x unit_price x 8%/week x episode weeks
    price = T["SKU"].set_index("sku_id").at[s, "unit_price"]
    weeks = out["Shortage"].set_index("shortage_id").at[sid, "episode_weeks"]
    assert abs(bo["total_cost"] - round(50 * price * 0.08 * weeks, 2)) < 0.011 and bo["fill_rate_pct"] == 0
    new_po = mo[mo["option_type"] == "NEW_PO"]
    if len(new_po):
        o = new_po.iloc[0]
        assert o["qty"] % 1 == 0 and o["covered_qty"] <= 50 and o["cost_delta_vs_baseline"] == round(o["total_cost"] - bo["total_cost"], 2)


def test_duplicate_inbound_is_not_counted_twice(tiny):
    T, s, l = _golden(tiny)
    po = T["PurchaseOrder"]
    dup = po[po["po_id"] == PO_ID].copy()
    dup["po_id"] = "PO-2026-999991"
    T["PurchaseOrder"] = pd.concat([po, dup], ignore_index=True)
    out, _ = run_plan(T, load_policy(), 1, "golden")
    pb = out["ProjectedBalance"].query("sku_id == @s and location_id == @l").sort_values("week_start_date")
    assert pb["scheduled_receipts_qty"].tolist()[:4] == [0, 0, 80, 0]
    f = out["DataQualityFinding"]
    assert (f[(f["issue_type"] == "INBOUND_DOUBLE_COUNT")]["record_id"] == "PO-2026-999991").any()


def test_uom_mismatch_uses_converted_quantity(tiny):
    T, s, l = _golden(tiny)
    # 8 CASES of 10 recorded as qty_base=8 (not converted)
    conv = T["UoMConversion"]
    base = T["SKU"].set_index("sku_id").at[s, "base_uom"]
    pack = "BAG" if base == "KG" else "CASE"
    T["UoMConversion"] = conv[conv["sku_id"] != s]
    T["UoMConversion"] = pd.concat([T["UoMConversion"], pd.DataFrame([{"conversion_id": f"UOMC-{s}-{pack}", "sku_id": s, "from_uom": pack, "to_uom": base, "factor": 10.0}])], ignore_index=True)
    po = T["PurchaseOrder"]
    j = po.index[po["po_id"] == PO_ID][0]
    po.loc[j, ["order_uom", "order_qty", "qty_base"]] = [pack, 8, 8]
    out, _ = run_plan(T, load_policy(), 1, "golden")
    pb = out["ProjectedBalance"].query("sku_id == @s and location_id == @l").sort_values("week_start_date")
    assert pb["scheduled_receipts_qty"].tolist()[2] == 80  # 8 x 10, not 8
    f = out["DataQualityFinding"]
    assert (f[(f["issue_type"] == "UOM_MISMATCH")]["record_id"] == PO_ID).any()


def test_missing_lead_time_is_never_silently_defaulted(tiny):
    T, s, l = _golden(tiny)
    T["LeadTime"] = T["LeadTime"][T["LeadTime"]["sku_id"] != s]
    out, _ = run_plan(T, load_policy(), 1, "golden")
    sh = out["Shortage"].query("sku_id == @s and location_id == @l").iloc[0]
    assert sh["status"] == "NEEDS_REVIEW" and sh["data_quality_flag"] == "SHORTAGE_MISSING_LEAD_TIME"
    mo = out["MitigationOption"].query("shortage_id == @sh.shortage_id and option_type in ['NEW_PO','ALT_SUPPLIER_PO']")
    assert len(mo) and (mo["is_recommendable"] == 0).all() and (mo["lead_time_check"] == "MISSING").all()


def test_lead_time_of_zero_days_is_valid_not_missing(tiny):
    T, s, l = _golden(tiny)
    lt = T["LeadTime"]
    lt.loc[lt["sku_id"] == s, ["production_days", "transit_days", "total_lead_days", "p90_lead_days"]] = [0, 0, 0, 0]
    out, _ = run_plan(T, load_policy(), 1, "golden")
    sh = out["Shortage"].query("sku_id == @s and location_id == @l").iloc[0]
    assert sh["status"] != "NEEDS_REVIEW"

