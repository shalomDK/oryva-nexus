"""Supplier performance intelligence: deterministic, data-derived scorecard (no random or hard-coded scores).

Definitions (all computed from exported tables):
* on_time_pct        - share of orders with a supplier commitment (CONFIRMED/IN_TRANSIT/DELAYED/RECEIVED) whose
                       delivery is on or before the requested date (received: actual receipt; open: current ETA).
* fulfilment_pct     - share of ordered quantity placed in supplier-weeks that are within the supplier's capacity
                       (deliverable in full).  The dataset has no partial-shipment records, so this is the in-full proxy.
* delay_incidents / avg_delay_days / avg_slip_days - from TransportEvent DELAYED rows and promised-vs-requested slip.
* lead_time_ratio    - realised lead time (received orders: receipt - order date) / planned LeadTime (None if no received orders).
* peak_util_pct / avg_util_pct / weeks_over_90 - from the capacity ledger.
* shortage exposure  - shortage units whose cause records point at this supplier's purchase orders.
Composite score (0-100) = 0.35 on-time + 0.20 fulfilment + 0.20 delay + 0.15 capacity headroom + 0.10 exposure,
with delay_score = 100 - min(100, 1.5*delayed_share_pct + 4*avg_slip_days),
capacity_score = 100 - min(100, 2.5*max(0, peak_util_pct - 60)), exposure_score = 100*(1 - exposed_units_share).
Tier: A >= 85, B >= 70, C >= 55, else D.  Suppliers with < 3 committed orders are flagged low confidence."""
from __future__ import annotations

import numpy as np
import pandas as pd

WEIGHTS = {"on_time": 0.35, "fulfilment": 0.20, "delay": 0.20, "capacity": 0.15, "exposure": 0.10}
COMMITTED = ("CONFIRMED", "IN_TRANSIT", "DELAYED", "RECEIVED")


def scorecard(T: dict, out: dict) -> pd.DataFrame:
    po = T["PurchaseOrder"].copy()
    sup = T["Supplier"].set_index("supplier_id")
    led = out["SupplierCapacityLedger"]
    tre = T["TransportEvent"]
    po["committed"] = po["status"].isin(COMMITTED)
    done = po["status"] == "RECEIVED"
    deliv = po["actual_receipt_date"].where(done, po["eta_date"])
    po["on_time"] = (deliv <= po["requested_date"])
    po["slip"] = (pd.to_datetime(po["promised_date"]) - pd.to_datetime(po["requested_date"])).dt.days
    delayed = tre[tre["event_type"] == "DELAYED"].merge(po[["po_id", "supplier_id"]], on="po_id")
    g = po.groupby("supplier_id")
    s = pd.DataFrame({"orders": g.size(), "received": g["status"].apply(lambda x: (x == "RECEIVED").sum()),
                      "cancelled": g["status"].apply(lambda x: (x == "CANCELLED").sum()),
                      "committed_orders": g["committed"].sum()})
    c = po[po["committed"]]
    s["on_time_pct"] = (c.groupby("supplier_id")["on_time"].mean() * 100).round(2)
    s["avg_slip_days"] = c.groupby("supplier_id")["slip"].mean().round(2)
    s["delay_incidents"] = delayed.groupby("supplier_id").size()
    s["avg_delay_days"] = delayed.groupby("supplier_id")["delay_days"].mean().round(2)
    s["max_delay_days"] = delayed.groupby("supplier_id")["delay_days"].max()
    lt = T["LeadTime"][T["LeadTime"]["ship_to_location_id"].isna()].groupby(["supplier_id", "sku_id"])["total_lead_days"].first()
    r = po[done].copy()
    r["planned"] = [lt.get((a, b), np.nan) for a, b in zip(r["supplier_id"], r["sku_id"])]
    r["realised"] = (pd.to_datetime(r["actual_receipt_date"]) - pd.to_datetime(r["order_date"])).dt.days
    s["lead_time_ratio"] = (r.groupby("supplier_id").apply(lambda d: (d["realised"] / d["planned"]).mean(), include_groups=False)).round(3)
    if len(led):
        lg = led.groupby("supplier_id")
        s["peak_util_pct"] = lg["utilisation_pct"].max().round(2)
        s["avg_util_pct"] = lg["utilisation_pct"].mean().round(2)
        s["weeks_over_90"] = lg["utilisation_pct"].apply(lambda x: int((x >= 90).sum()))
        over = led[led["status"] == "EXCEEDED"].groupby("supplier_id")["committed_qty"].sum()
        tot = led.groupby("supplier_id")["committed_qty"].sum()
        s["fulfilment_pct"] = (100 * (1 - over.reindex(tot.index).fillna(0) / tot)).round(2)
    cs = out["ShortageCause"].merge(po[["po_id", "supplier_id"]], left_on="source_id", right_on="po_id")
    exposure = cs.groupby("supplier_id").agg(shortages_exposed=("shortage_id", "nunique"), exposed_units=("contribution_qty", "sum"))
    s = s.join(exposure)
    s = s.reindex(sup.index)
    for col in ("orders", "received", "cancelled", "committed_orders", "delay_incidents", "weeks_over_90", "shortages_exposed", "exposed_units"):
        s[col] = s[col].fillna(0).astype(int)
    s["on_time_pct"] = s["on_time_pct"].fillna(100.0)
    s["fulfilment_pct"] = s["fulfilment_pct"].fillna(100.0)
    for col in ("avg_slip_days", "avg_delay_days", "peak_util_pct", "avg_util_pct"):
        s[col] = s[col].fillna(0.0)
    delayed_share = 100 * s["delay_incidents"] / s["committed_orders"].replace(0, np.nan)
    s["delay_score"] = (100 - np.minimum(100, 1.5 * delayed_share.fillna(0) + 4 * s["avg_slip_days"].clip(lower=0))).round(2)
    s["capacity_score"] = (100 - np.minimum(100, 2.5 * np.maximum(0, s["peak_util_pct"] - 60))).round(2)
    tot_exp = max(1, float(out["Shortage"]["shortage_qty"].sum()))
    s["exposure_score"] = (100 * (1 - np.minimum(1, s["exposed_units"] / tot_exp * 20))).round(2)
    s["score"] = (WEIGHTS["on_time"] * s["on_time_pct"] + WEIGHTS["fulfilment"] * s["fulfilment_pct"] + WEIGHTS["delay"] * s["delay_score"]
                  + WEIGHTS["capacity"] * s["capacity_score"] + WEIGHTS["exposure"] * s["exposure_score"]).round(2)
    s["tier"] = pd.cut(s["score"], [-1, 55, 70, 85, 101], labels=["D", "C", "B", "A"], right=False).astype(str)
    s["confidence"] = np.where(s["committed_orders"] >= 3, "ok", "low (<3 committed orders)")
    s = s.join(sup[["supplier_name", "region", "tier", "status"]].rename(columns={"tier": "contract_tier", "status": "supplier_status"}))
    s.index.name = "supplier_id"
    return s.reset_index()


def explain_score(card: pd.DataFrame, supplier_id: str) -> pd.DataFrame:
    r = card[card["supplier_id"] == supplier_id]
    if r.empty:
        raise KeyError(supplier_id)
    r = r.iloc[0]
    comp = {"on_time": r["on_time_pct"], "fulfilment": r["fulfilment_pct"], "delay": r["delay_score"], "capacity": r["capacity_score"], "exposure": r["exposure_score"]}
    return pd.DataFrame([{"component": k, "value": float(v), "weight": WEIGHTS[k], "contribution": round(float(v) * WEIGHTS[k], 2)} for k, v in comp.items()])
