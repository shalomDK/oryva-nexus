"""Labelled edge-case injection (PDF section 6) + ground-truth writer.

Protocol: the baseline is generated and validated clean FIRST.  Targets are then selected by documented,
deterministic rules (sorted keys; shortage chains found by running the planning engine on the clean data),
only the target rows are touched (or rows referencing them are added), and one ground-truth row is
written per injection.  Nothing else changes (blast-radius test).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import dq, ids, weeks as W
from .frames import finalize
from .schema import GROUND_TRUTH_COLS

OPEN_INJ = ("PLANNED", "CONFIRMED")


class InjectionError(RuntimeError):
    pass


def n_variant_b(P: dict) -> int:
    """Number of 'received order re-listed as open' double counts (variant B)."""
    return max(1, int(P["edge_cases"]["per_type"]) // 2) if int(P["edge_cases"]["per_type"]) > 0 else 0


def n_reserved(P: dict) -> int:
    """POs left out of the clean baseline so the exported PurchaseOrder table has exactly n_purchase_orders rows."""
    k = int(P["edge_cases"]["per_type"])
    return k + 1 + n_variant_b(P) if k > 0 else 0


def _next(df: pd.DataFrame, col: str, prefix: str) -> int:
    return int(df[col].str.extract(r"(\d+)$")[0].astype(int).max()) + 1 if len(df) else 1


def inject(T0: dict, out0: dict, P: dict):
    """Return (T1, ground_truth_df).  T0 is not modified."""
    k = int(P["edge_cases"]["per_type"])
    seed = P["seed"]
    as_of = P["as_of_date"]
    T = {n: df.copy() for n, df in T0.items()}
    gt = []

    def label(cls, issue, entity, rid, related, field, orig, inj, detect, decision, impact, rule):
        gt.append({"label_class": cls, "issue_type": issue, "entity": entity, "record_id": rid, "related_record_ids": related,
                   "injected_field": field, "original_value": orig, "injected_value": inj, "expected_detection": detect,
                   "expected_decision": decision, "impact_qty": impact, "rule_ref": rule, "seed": seed})

    sh = out0["Shortage"].sort_values("shortage_id")
    sh_pairs = list(zip(sh["sku_id"], sh["location_id"]))
    sh_skus_sorted = list(dict.fromkeys(sh["sku_id"]))
    sku_t = T["SKU"].set_index("sku_id")
    used: set = set()
    pe = dq.po_effective(T)
    po = T["PurchaseOrder"]
    poi = po.set_index("po_id")

    # ---------------------------------------------------------------- 1. inbound counted twice
    led = dq.ledger(T, pe)
    capmap = {(a, b, c): (int(d_), int(e_)) for a, b, c, d_, e_ in zip(led["supplier_id"], led["product_family"], led["week_start_date"],
                                                                      led["capacity_qty"], led["committed_qty"])}
    cand = pe[pe["status"].isin(OPEN_INJ) & ~pe["is_duplicate"] & ~pe["factor_missing"] & ~pe["uom_mismatch"]].sort_values("po_id")
    cand = cand.assign(ws=dq.week_start_str(cand["order_date"]))
    in_short = set(sh_pairs)
    pref = [r_ for r_ in cand.itertuples() if (r_.sku_id, r_.ship_to_location_id) in in_short]
    rest = [r_ for r_ in cand.itertuples() if (r_.sku_id, r_.ship_to_location_id) not in in_short]
    chosen_dup, chosen_near = [], []
    added = {}
    for r_ in pref + rest:
        if len(chosen_dup) >= k and len(chosen_near) >= 1:
            break
        key = (r_.supplier_id, r_.product_family, r_.ws)
        cap, com = capmap.get(key, (0, 0))
        if com + added.get(key, 0) + r_.qty_eff > cap or r_.sku_id in used:
            continue
        added[key] = added.get(key, 0) + r_.qty_eff
        used.add(r_.sku_id)
        (chosen_dup if len(chosen_dup) < k else chosen_near).append(r_)
    if len(chosen_dup) < k or (k and len(chosen_near) < 1):
        raise InjectionError("not enough eligible open POs for INBOUND_DOUBLE_COUNT")
    n_po = _next(po, "po_id", "PO")
    poe = T["PurchaseOrderEvent"]
    n_ev = _next(poe, "event_id", "POE")
    new_po, new_ev = [], []
    for j, r_ in enumerate(chosen_dup + chosen_near):
        near = j >= k
        row = poi.loc[r_.po_id].to_dict()
        row["po_id"] = ids.po(n_po)
        if near:
            row["supplier_ref_no"] = row["supplier_ref_no"] + "-B"
        new_po.append(row)
        for e in poe[poe["po_id"] == r_.po_id].itertuples():
            new_ev.append({"event_id": f"POE-{n_ev:06d}", "po_id": row["po_id"], "event_type": e.event_type, "from_status": e.from_status,
                           "to_status": e.to_status, "event_date": e.event_date, "actor_role": e.actor_role,
                           "delay_days": e.delay_days, "reason_code": e.reason_code})
            n_ev += 1
        if near:
            label("BOUNDARY", "INBOUND_DOUBLE_COUNT", "PurchaseOrder", row["po_id"], r_.po_id, "supplier_ref_no", r_.supplier_ref_no,
                  row["supplier_ref_no"], 0, "KEEP_AS_SEPARATE_ORDER", int(r_.qty_eff), "near-duplicate with a different supplier_ref_no is a legitimate second order")
        else:
            label("ANOMALY", "INBOUND_DOUBLE_COUNT", "PurchaseOrder", row["po_id"], r_.po_id, "po_id", "", row["po_id"], 1,
                  "EXCLUDE_DUPLICATE", int(r_.qty_eff), "same supplier/SKU/ship-to/promised date/supplier_ref_no counted twice")
        n_po += 1
    # variant B: an already RECEIVED order (in on-hand and an InventoryEvent receipt) is re-listed as an open PLANNED order
    rcv = pe[(pe["status"] == "RECEIVED") & ~pe["is_duplicate"]].sort_values("po_id")
    nb = 0
    for r_ in rcv.itertuples():
        if nb >= n_variant_b(P):
            break
        if r_.sku_id in used:
            continue
        used.add(r_.sku_id)
        row = poi.loc[r_.po_id].to_dict()
        row.update(po_id=ids.po(n_po), status="PLANNED", carrier_id=None, actual_receipt_date=None, created_date=as_of,
                   order_date=as_of, requested_date=W.week_start_s(2), promised_date=W.week_start_s(2), eta_date=W.week_start_s(2))
        new_po.append(row)
        new_ev.append({"event_id": f"POE-{n_ev:06d}", "po_id": row["po_id"], "event_type": "CREATED", "from_status": None,
                       "to_status": "PLANNED", "event_date": as_of, "actor_role": "PLANNER", "delay_days": None, "reason_code": None})
        n_ev += 1
        label("ANOMALY", "INBOUND_DOUBLE_COUNT", "PurchaseOrder", row["po_id"], r_.po_id, "variant", "",
              "RECEIVED_ORDER_RELISTED_AS_OPEN", 1, "EXCLUDE_DUPLICATE", int(r_.qty_eff),
              "order already received (in on-hand) is also listed as open inbound")
        n_po += 1
        nb += 1
    if nb < n_variant_b(P):
        raise InjectionError("not enough RECEIVED POs for INBOUND_DOUBLE_COUNT variant B")
    T["PurchaseOrder"] = finalize("PurchaseOrder", pd.concat([po, pd.DataFrame(new_po)], ignore_index=True))
    T["PurchaseOrderEvent"] = finalize("PurchaseOrderEvent", pd.concat([poe, pd.DataFrame(new_ev)], ignore_index=True))

    # ---------------------------------------------------------------- 2. units-of-measure mismatch
    pe = dq.po_effective(T)
    cand = pe[pe["status"].isin(OPEN_INJ + ("IN_TRANSIT", "DELAYED")) & ~pe["is_duplicate"] & (pe["qty_eff"] != 0)
              & ~pe["uom_mismatch"] & (pe["qty_eff"] != T["PurchaseOrder"].set_index("po_id").loc[pe["po_id"], "order_qty"].values)]
    cand = cand.sort_values("po_id")
    pref = [r_ for r_ in cand.itertuples() if (r_.sku_id, r_.ship_to_location_id) in in_short]
    rest = [r_ for r_ in cand.itertuples() if (r_.sku_id, r_.ship_to_location_id) not in in_short]
    n_done = 0
    po = T["PurchaseOrder"].set_index("po_id")
    for r_ in pref + rest:
        if n_done >= k:
            break
        if r_.sku_id in used:
            continue
        used.add(r_.sku_id)
        oq = int(po.at[r_.po_id, "order_qty"])
        po.at[r_.po_id, "qty_base"] = oq
        po.at[r_.po_id, "total_cost"] = round(oq * float(po.at[r_.po_id, "unit_price"]), 2)
        label("ANOMALY", "UOM_MISMATCH", "PurchaseOrder", r_.po_id, r_.sku_id, "qty_base", int(r_.qty_recorded), oq, 1,
              "USE_CONVERTED_QUANTITY", int(r_.qty_eff - oq), f"order in {po.at[r_.po_id, 'order_uom']} but qty_base not converted (x{r_.qty_eff / max(oq, 1):g})")
        n_done += 1
    if n_done < k:
        raise InjectionError("not enough eligible POs for UOM_MISMATCH")
    T["PurchaseOrder"] = finalize("PurchaseOrder", po.reset_index())

    # ---------------------------------------------------------------- 3. supplier capacity exceeded (+ boundary)
    pe = dq.po_effective(T)
    led = dq.ledger(T, pe)
    fut = led[(led["week_start_date"] >= as_of) & (led["committed_qty"] >= 5)].sort_values(["supplier_id", "product_family", "week_start_date"])
    capdf = T["SupplierCapacity"]
    n_cap = _next(capdf, "capacity_id", "SCAP")
    new_cap, seen = [], set()
    todo = [("ANOMALY", k), ("BOUNDARY", 1 if k else 0)]
    for cls, cnt in todo:
        got = 0
        for r_ in fut.itertuples():
            if got >= cnt:
                break
            if (r_.supplier_id, r_.product_family) in seen:
                continue
            base = capdf[(capdf["supplier_id"] == r_.supplier_id) & (capdf["product_family"] == r_.product_family)].sort_values("effective_from").iloc[0]
            newcap = max(1, int(np.floor(0.8 * r_.committed_qty))) if cls == "ANOMALY" else int(r_.committed_qty)
            ws = r_.week_start_date
            new_cap.append({"capacity_id": ids.counter("SCAP", n_cap), "supplier_id": r_.supplier_id, "product_family": r_.product_family,
                            "weekly_capacity_qty": newcap, "min_order_qty": int(base["min_order_qty"]), "order_multiple": int(base["order_multiple"]),
                            "capacity_uom": "MIXED", "status": "ACTIVE", "effective_from": ws, "effective_to": W.add_days(ws, 7)})
            n_cap += 1
            seen.add((r_.supplier_id, r_.product_family))
            key = dq.cap_key(r_.supplier_id, r_.product_family, ws)
            if cls == "ANOMALY":
                label("ANOMALY", "SUPPLIER_CAPACITY_EXCEEDED", "SupplierCapacityLedger", key, new_cap[-1]["capacity_id"], "weekly_capacity_qty",
                      int(r_.capacity_qty), newcap, 1, "FLAG_AND_LIMIT_MITIGATION_CAPACITY", int(r_.committed_qty - newcap),
                      "supplier capacity cut below already committed load")
            else:
                label("BOUNDARY", "SUPPLIER_CAPACITY_EXCEEDED", "SupplierCapacityLedger", key, new_cap[-1]["capacity_id"], "weekly_capacity_qty",
                      int(r_.capacity_qty), newcap, 0, "NO_ACTION", 0, "committed == capacity is not an exceedance")
            got += 1
        if got < cnt:
            raise InjectionError("not enough supplier-weeks for SUPPLIER_CAPACITY_EXCEEDED")
    if new_cap:
        T["SupplierCapacity"] = finalize("SupplierCapacity", pd.concat([capdf, pd.DataFrame(new_cap)], ignore_index=True))

    # ---------------------------------------------------------------- 4. shortage without lead time
    lt = T["LeadTime"]
    ss = T["SKUSupplier"]
    n_done, drop = 0, []
    for s in sh_skus_sorted:
        if n_done >= k:
            break
        if s in used or sku_t.at[s, "sku_type"] == "FINISHED_MAKE":
            continue
        sups = sorted(ss.loc[ss["sku_id"] == s, "supplier_id"])
        if not sups:
            continue
        used.add(s)
        for sp in sups:
            nrows = int(((lt["supplier_id"] == sp) & (lt["sku_id"] == s)).sum())
            drop.append((sp, s))
            label("ANOMALY", "SHORTAGE_MISSING_LEAD_TIME", "LeadTime", dq.lt_key(sp, s), s, "lead_time_row", f"{nrows} row(s)", "removed", 1,
                  "FLAG_AND_BLOCK_MITIGATION", 0, "shortage chain whose supplier-SKU lead time is not defined")
        n_done += 1
    if n_done < k:
        raise InjectionError("not enough shortage SKUs for SHORTAGE_MISSING_LEAD_TIME")
    if drop:
        dk = set(drop)
        T["LeadTime"] = finalize("LeadTime", lt[[(a, b) not in dk for a, b in zip(lt["supplier_id"], lt["sku_id"])]])

    # ---------------------------------------------------------------- 5. substitute not approved
    subs = T["SKUSubstitute"]
    sl = T["SKULocation"]
    stocked = {}
    for s_, l_ in zip(sl.loc[sl["stocking_status"] == "ACTIVE", "sku_id"], sl.loc[sl["stocking_status"] == "ACTIVE", "location_id"]):
        stocked.setdefault(l_, set()).add(s_)
    linked = set(zip(subs["sku_id"], subs["substitute_sku_id"]))
    cycle = ["PENDING", "REJECTED", "EXPIRED"]
    new_sub, n_done = [], 0
    for (s, l) in sh_pairs:
        if n_done >= k:
            break
        if s in used or sku_t.at[s, "sku_type"] != "FINISHED_BUY":
            continue
        alts = sorted(a for a in stocked.get(l, set()) if a != s and a not in used and (s, a) not in linked
                      and sku_t.at[a, "product_family"] == sku_t.at[s, "product_family"] and sku_t.at[a, "base_uom"] == sku_t.at[s, "base_uom"]
                      and sku_t.at[a, "sku_type"] == "FINISHED_BUY")
        if not alts:
            continue
        a = alts[0]
        st = cycle[n_done % 3]
        ef = W.add_days(as_of, -30)
        row = {"sku_id": s, "substitute_sku_id": a, "substitution_ratio": 1.0, "approval_status": st,
               "approved_by_role": "PLANNER" if st == "EXPIRED" else None,
               "approved_date": W.add_days(as_of, -200) if st == "EXPIRED" else None, "cost_penalty_pct": 2.0,
               "effective_from": W.add_days(as_of, -400) if st == "EXPIRED" else ef,
               "effective_to": W.add_days(as_of, -1) if st == "EXPIRED" else None}
        new_sub.append(row)
        used.update([s, a])
        label("ANOMALY", "SUBSTITUTE_NOT_APPROVED", "SKUSubstitute", dq.sub_key(s, a, row["effective_from"]), s, "approval_status", "", st, 1,
              "REJECT_OPTION_NEVER_RECOMMEND", 0, "candidate substitute whose approval is pending/rejected/expired")
        n_done += 1
    if n_done < k:
        raise InjectionError("not enough shortage pairs for SUBSTITUTE_NOT_APPROVED")
    T["SKUSubstitute"] = finalize("SKUSubstitute", pd.concat([subs, pd.DataFrame(new_sub)], ignore_index=True))

    g = pd.DataFrame(gt)
    g = g.sort_values(["issue_type", "label_class", "record_id"], kind="mergesort").reset_index(drop=True)
    g.insert(0, "label_id", [f"GT-{i:06d}" for i in range(1, len(g) + 1)])
    g["expected_detection"] = g["expected_detection"].astype(int)
    return T, g[GROUND_TRUTH_COLS]
