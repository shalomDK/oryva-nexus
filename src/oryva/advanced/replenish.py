"""Automated replenishment: purchase-order PROPOSALS derived from the planning engine's recommended supplier orders.

Every proposal is re-validated against source tables (MOQ, order multiple, remaining supplier capacity in the order week,
lead time, supplier status / approval) before it can be approved; approval/rejection and the resulting draft order live in
the application state database (never in the baseline dataset)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import dq, weeks as W


def _lt(T: dict, supplier: str, sku: str, loc: str, as_of: str):
    lt = T["LeadTime"]
    r = lt[(lt["supplier_id"] == supplier) & (lt["sku_id"] == sku) & (lt["effective_from"] <= as_of) & (lt["effective_to"].isna() | (lt["effective_to"] > as_of))]
    o = r[r["ship_to_location_id"] == loc]
    r = o if len(o) else r[r["ship_to_location_id"].isna()]
    return None if r.empty else int(r.sort_values("effective_from").iloc[-1]["total_lead_days"])


def _cap_row(T: dict, supplier: str, fam: str, ws: str):
    c = T["SupplierCapacity"]
    c = c[(c["supplier_id"] == supplier) & (c["product_family"] == fam) & (c["status"] == "ACTIVE") & (c["effective_from"] <= ws) & (c["effective_to"].isna() | (ws < c["effective_to"]))]
    return None if c.empty else c.sort_values("effective_from").iloc[-1]


def validate_proposal(p: dict, T: dict, out: dict, extra_committed: dict | None = None) -> list[dict]:
    """Independent re-derivation of every constraint from source tables.  Returns [{check, ok, detail}]."""
    extra_committed = extra_committed or {}
    sku = T["SKU"].set_index("sku_id")
    fam = sku.at[p["sku_id"], "product_family"]
    sup = T["Supplier"].set_index("supplier_id")
    od = p["order_date"]
    ws = dq.week_start_str(pd.Series([od])).iloc[0]
    cr = _cap_row(T, p["supplier_id"], fam, ws)
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
    add("supplier active", sup.at[p["supplier_id"], "status"] == "ACTIVE", f"status={sup.at[p['supplier_id'], 'status']}")
    ss = T["SKUSupplier"]
    ap = ss[(ss["sku_id"] == p["sku_id"]) & (ss["supplier_id"] == p["supplier_id"])]
    add("supplier approved for SKU", len(ap) > 0 and (ap["approval_status"] == "APPROVED").any(), f"{len(ap)} sourcing record(s)")
    lead = _lt(T, p["supplier_id"], p["sku_id"], p["location_id"], od if od > T['Inventory']['as_of_date'].iloc[0] else T['Inventory']['as_of_date'].iloc[0])
    add("lead time defined", lead is not None, f"lead={lead} d")
    if lead is not None:
        add("lead time consistent", lead == p["lead_days"], f"table={lead} d, proposal={p['lead_days']} d")
        arr = W.add_days(od, lead)
        late = arr > W.add_days(p["need_by_date"], 6)
        add("arrival vs need date (informational: late orders still reduce the gap)", True,
            f"arrival {arr} {'is LATE vs' if late else 'on time for'} need week of {p['need_by_date']}")
    if cr is None:
        add("capacity record exists", False, f"no active capacity for {p['supplier_id']}/{fam} week {ws}")
    else:
        moq, mult, cap = int(cr["min_order_qty"]), int(cr["order_multiple"]), int(cr["weekly_capacity_qty"])
        led = out["SupplierCapacityLedger"]
        com = led[(led["supplier_id"] == p["supplier_id"]) & (led["product_family"] == fam) & (led["week_start_date"] == ws)]["committed_qty"]
        committed = int(com.iloc[0]) if len(com) else 0
        committed += int(extra_committed.get((p["supplier_id"], fam, ws), 0))
        add("minimum order quantity", p["qty_base"] >= moq, f"qty {p['qty_base']} >= MOQ {moq}")
        add("order multiple", p["qty_base"] % mult == 0, f"qty {p['qty_base']} multiple of {mult}")
        add("supplier capacity", committed + p["qty_base"] <= cap, f"committed {committed} + {p['qty_base']} <= capacity {cap} (week {ws})")
    add("quantity positive", p["qty_base"] > 0, f"qty={p['qty_base']}")
    return checks


def build_proposals(T: dict, out: dict, policy: dict) -> pd.DataFrame:
    mo, sh = out["MitigationOption"], out["Shortage"].set_index("shortage_id")
    as_of = str(T["Inventory"]["as_of_date"].iloc[0])
    sku = T["SKU"].set_index("sku_id")
    ss = T["SKUSupplier"].set_index(["sku_id", "supplier_id"])["unit_price"]
    conv = T["UoMConversion"].set_index("sku_id")
    top = mo[(mo["is_recommended"] == 1) & mo["option_type"].isin(["NEW_PO", "ALT_SUPPLIER_PO"])]
    rows = []
    for r in top.itertuples():
        s = sh.loc[r.shortage_id]
        lead = int(r.lead_days)
        latest = W.add_days(s["need_by_date"], -lead)
        slack = (pd.Timestamp(latest) - pd.Timestamp(as_of)).days
        order_date = as_of if slack <= 14 else W.add_days(latest, -7)
        pack = None
        if s["sku_id"] in conv.index and r.qty % int(conv.at[s["sku_id"], "factor"]) == 0:
            pack = (conv.at[s["sku_id"], "from_uom"], int(r.qty // int(conv.at[s["sku_id"], "factor"])))
        price = float(ss.get((s["sku_id"], r.supplier_id), r.unit_cost))
        rows.append({"proposal_id": "RPL-" + r.mitigation_id[4:], "shortage_id": r.shortage_id, "mitigation_id": r.mitigation_id,
                     "sku_id": s["sku_id"], "location_id": s["location_id"], "supplier_id": r.supplier_id, "qty_base": int(r.qty),
                     "order_uom": pack[0] if pack else sku.at[s["sku_id"], "base_uom"], "order_qty": pack[1] if pack else int(r.qty),
                     "unit_price": price, "order_value": round(price * r.qty, 2), "lead_days": lead, "need_by_date": s["need_by_date"],
                     "latest_order_date": latest, "order_date": order_date, "expected_arrival": W.add_days(order_date, lead),
                     "on_time": W.add_days(order_date, lead) <= W.add_days(s["need_by_date"], 6), "covered_qty": int(r.covered_qty),
                     "approval_role": r.approval_required_role, "priority_rank": int(s["priority_rank"]), "shortage_qty": int(s["shortage_qty"])})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("priority_rank", kind="mergesort").reset_index(drop=True)
    # validate in priority order, accumulating same-week supplier load so proposals cannot jointly exceed capacity
    extra, ok, notes = {}, [], []
    fam = T["SKU"].set_index("sku_id")["product_family"]
    for p in df.to_dict("records"):
        chk = validate_proposal(p, T, out, extra)
        good = all(c["ok"] for c in chk)
        if good:
            ws = dq.week_start_str(pd.Series([p["order_date"]])).iloc[0]
            k = (p["supplier_id"], fam[p["sku_id"]], ws)
            extra[k] = extra.get(k, 0) + p["qty_base"]
        ok.append(good)
        notes.append("; ".join(c["check"] for c in chk if not c["ok"]))
    df["valid"], df["failed_checks"] = ok, notes
    return df

