"""Planning engine: data-quality gate -> gross requirements -> scheduled receipts -> production (capacity
limited) -> projected available balance -> shortage episodes -> cause attribution -> prioritisation ->
mitigation options (policy, lead-time and capacity checks; cost/service trade-offs) -> event history.

Pure function of the INPUT tables + policy.  It never reads ground truth.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import dq, ids, weeks as W
from .config import policy_hash
from .frames import finalize

ENGINE_VERSION = "1.0.0"
OPEN = ("PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED")
TYPE_ORDER = {t: i for i, t in enumerate(["EXPEDITE_PO", "NEW_PO", "ALT_SUPPLIER_PO", "SUBSTITUTE_SKU",
                                          "LOCATION_TRANSFER", "PRODUCTION_REPLAN", "PARTIAL_FILL_BACKORDER"])}


def _d(s):
    return date.fromisoformat(s)


def _fill(covered, D, weeks_late, ep_weeks):
    return round(100.0 * min(1.0, covered / D) * (1.0 - min(1.0, weeks_late / max(1, ep_weeks))), 2)


def run_plan(T: dict, policy: dict, seed: int = 0, profile: str = "", run_id: str = "RUN-0001"):
    NW = 52
    inv = T["Inventory"].sort_values(["sku_id", "location_id"]).reset_index(drop=True)
    nP = len(inv)
    as_of = str(inv["as_of_date"].iloc[0])
    as_of_d = _d(as_of)
    ws_asof = dq.week_start_str(pd.Series([as_of])).iloc[0]
    pair_mi = pd.MultiIndex.from_frame(inv[["sku_id", "location_id"]])
    pair_of = {k: i for i, k in enumerate(pair_mi)}
    sku_t = T["SKU"].set_index("sku_id")
    loc_t = T["Location"].set_index("location_id")
    sup_t = T["Supplier"].set_index("supplier_id")

    def pidx(df, sc="sku_id", lc="location_id"):
        return pair_mi.get_indexer(pd.MultiIndex.from_frame(df[[sc, lc]]))

    # -------------------------------------------------------------- Stage 0: data-quality gate
    pe = dq.po_effective(T)
    led = dq.ledger(T, pe)
    miss_lt = dq.missing_lead_times(T)
    unappr = dq.unapproved_substitutes(T, as_of)

    # -------------------------------------------------------------- Stage 1: gross requirements
    fd = T["ForecastDemand"]
    pi = pidx(fd)
    wi = W.weeks_of(fd["week_start_date"]) - 1
    D = np.zeros((nP, NW), dtype=np.int64)
    np.add.at(D, (pi, wi), fd["forecast_qty"].to_numpy(np.int64))
    med = np.median(D, axis=1)
    spikes = defaultdict(list)
    sp = fd[fd["demand_driver"] == "SPIKE"]
    for p_, w_, q_, did in zip(pidx(sp), W.weeks_of(sp["week_start_date"]), sp["forecast_qty"], sp["demand_id"]):
        spikes[int(p_)].append((int(w_), int(q_), did))

    # -------------------------------------------------------------- Stage 3: scheduled receipts
    pe_open = pe[pe["status"].isin(OPEN) & ~pe["is_duplicate"] & ~pe["factor_missing"]]
    R = np.zeros((nP, NW), dtype=np.int64)
    rw = W.weeks_of(pe_open["eta_date"])
    rp = pidx(pe_open, "sku_id", "ship_to_location_id")
    ok = (rw >= 1) & (rw <= NW) & (rp >= 0)
    np.add.at(R, (rp[ok], rw[ok] - 1), pe_open["qty_eff"].to_numpy(np.int64)[ok])

    # -------------------------------------------------------------- Stage 4: production (capacity limited) + BOM explosion
    Prod = np.zeros((nP, NW), dtype=np.int64)
    DEP = np.zeros((nP, NW), dtype=np.int64)
    pl_all = T["ProductionPlan"].merge(T["BillOfMaterial"][["bom_id", "run_time_hours_per_unit", "lot_size"]], on="bom_id")
    pl = pl_all[pl_all["status"] != "CANCELLED"].copy()
    cancelled_plans = pl_all[pl_all["status"] == "CANCELLED"]
    pl["hours_req"] = pl["planned_qty"] * pl["run_time_hours_per_unit"]
    tot = pl.groupby(["work_center_id", "week_start_date"])["hours_req"].transform("sum")
    avail_h = T["ProductionCapacity"].set_index(["work_center_id", "week_start_date"])["available_hours"]
    pl["avail"] = avail_h.reindex(pd.MultiIndex.from_frame(pl[["work_center_id", "week_start_date"]])).values
    # Capacity rule: remove the minimum number of whole lots (largest orders first, round-robin) until the
    # work-centre-week fits in its available hours.  Within capacity nothing is cut.
    pl["capped_qty"] = pl["planned_qty"].astype(np.int64)
    over = pl[tot > pl["avail"] + 1e-9]
    for _, g in over.groupby(["work_center_id", "week_start_date"]):
        capx, used = float(g["avail"].iloc[0]), float(g["hours_req"].sum())
        order_ix = list(g.sort_values(["hours_req", "production_plan_id"], ascending=[False, True]).index)
        while used > capx + 1e-9:
            moved = False
            for ix in order_ix:
                lot_, rt_ = int(pl.at[ix, "lot_size"]), float(pl.at[ix, "run_time_hours_per_unit"])
                if pl.at[ix, "capped_qty"] >= lot_:
                    pl.at[ix, "capped_qty"] -= lot_
                    used -= lot_ * rt_
                    moved = True
                    if used <= capx + 1e-9:
                        break
            if not moved:
                break
    pl["cutback"] = pl["planned_qty"] - pl["capped_qty"]
    pl["week"] = W.weeks_of(pl["week_start_date"])
    if len(pl):
        pp_i = pidx(pl)
        np.add.at(Prod, (pp_i, pl["week"].to_numpy() - 1), pl["capped_qty"].to_numpy(np.int64))
        ex = pl.merge(T["BOMLine"], on="bom_id")
        ex["dep"] = np.ceil(ex["capped_qty"] * ex["qty_per"] * (1 + ex["scrap_pct"]) - 1e-9).astype(np.int64)
        di = pair_mi.get_indexer(pd.MultiIndex.from_arrays([ex["component_sku_id"], ex["location_id"]]))
        okd = di >= 0
        np.add.at(DEP, (di[okd], ex["week"].to_numpy()[okd] - 1), ex["dep"].to_numpy()[okd])
    used_hours = pl.assign(h=pl["capped_qty"] * pl["run_time_hours_per_unit"]).groupby(["work_center_id", "week"])["h"].sum().to_dict()
    cap_h = {(a, W.week_of(b)): float(c) for (a, b), c in avail_h.items()}
    plan_cut = defaultdict(list)
    for rr in pl[pl["cutback"] > 0].itertuples():
        plan_cut[(rr.sku_id, rr.location_id)].append((int(rr.week), int(rr.cutback), rr.production_plan_id, "PRODUCTION_CAPACITY"))
    for rr in cancelled_plans.itertuples():
        plan_cut[(rr.sku_id, rr.location_id)].append((W.week_of(rr.week_start_date), int(rr.planned_qty), rr.production_plan_id, "PRODUCTION_PLAN_CANCELLED"))
    plan_id_at = {(r_.sku_id, r_.location_id, W.week_of(r_.week_start_date)): r_.production_plan_id for r_ in pl_all.itertuples()}
    wc_of_pair = pl_all.groupby(["sku_id", "location_id"])["work_center_id"].first().to_dict()
    bom_of_sku = T["BillOfMaterial"].set_index("parent_sku_id")[["run_time_hours_per_unit", "lot_size"]].to_dict("index")

    # -------------------------------------------------------------- optional planned stock movements (simulation only)
    # Used by the decision simulator to model a location transfer or a substitution: the source pair gets an outflow
    # (treated as dependent demand) and the receiving pair a scheduled receipt.  Exported datasets never contain this
    # table, so the mandatory planning outputs are unchanged.
    mv = T.get("PlannedMovement")
    if mv is not None and len(mv):
        oi = pair_mi.get_indexer(pd.MultiIndex.from_arrays([mv["from_sku_id"], mv["from_location_id"]]))
        ii = pair_mi.get_indexer(pd.MultiIndex.from_arrays([mv["to_sku_id"], mv["to_location_id"]]))
        for o_, i_, oq, ow, iq, iw in zip(oi, ii, mv["out_qty"], mv["out_week"], mv["in_qty"], mv["in_week"]):
            if o_ >= 0 and 1 <= int(ow) <= NW:
                DEP[o_, int(ow) - 1] += int(oq)
            if i_ >= 0 and 1 <= int(iw) <= NW:
                R[i_, int(iw) - 1] += int(iq)

    # -------------------------------------------------------------- Stage 5: projected available balance
    avail0 = inv["available_qty"].to_numpy(np.int64)
    net = R + Prod - D - DEP
    closing = avail0[:, None] + np.cumsum(net, axis=1)
    opening = closing - net
    ss = inv["safety_stock_qty"].to_numpy(np.int64)
    wk_idx = np.arange(1, NW + 1)
    wl = [W.label(int(w)) for w in wk_idx]
    wsd = [W.week_start_s(int(w)) for w in wk_idx]
    pb = pd.DataFrame({
        "run_id": run_id, "sku_id": np.repeat(inv["sku_id"].to_numpy(), NW), "location_id": np.repeat(inv["location_id"].to_numpy(), NW),
        "iso_week": np.tile(wl, nP), "week_start_date": np.tile(wsd, nP), "opening_qty": opening.reshape(-1),
        "gross_demand_qty": D.reshape(-1), "dependent_demand_qty": DEP.reshape(-1),
        "scheduled_receipts_qty": R.reshape(-1), "production_receipts_qty": Prod.reshape(-1),
        "closing_qty": closing.reshape(-1), "safety_stock_qty": np.repeat(ss, NW),
        "shortfall_qty": np.maximum(0, ss[:, None] - closing).reshape(-1)})

    # -------------------------------------------------------------- per-pair PO evidence
    po_full = T["PurchaseOrder"].set_index("po_id")
    pe2 = pe.copy()
    pe2["ws"] = dq.week_start_str(pe2["order_date"])
    util = {(a, b, c): u for a, b, c, u in zip(led["supplier_id"], led["product_family"], led["week_start_date"], led["utilisation_pct"])}
    pair_pos = defaultdict(list)
    for r_ in pe2[~pe2["is_duplicate"] & ~pe2["factor_missing"]].itertuples():
        pair_pos[(r_.sku_id, r_.ship_to_location_id)].append({
            "po": r_.po_id, "sup": r_.supplier_id, "status": r_.status, "qty": int(r_.qty_eff),
            "req_w": W.week_of(r_.requested_date), "prom_w": W.week_of(r_.promised_date), "eta_w": W.week_of(r_.eta_date),
            "eta": r_.eta_date, "util": util.get((r_.supplier_id, r_.product_family, r_.ws), 0.0),
            "price": float(po_full.at[r_.po_id, "unit_price"])})
    dq_pairs = defaultdict(set)
    for r_ in pe[pe["is_duplicate"]].itertuples():
        dq_pairs[(r_.sku_id, r_.ship_to_location_id)].add("INBOUND_DOUBLE_COUNT")
    for r_ in pe[pe["uom_mismatch"] | pe["factor_missing"]].itertuples():
        dq_pairs[(r_.sku_id, r_.ship_to_location_id)].add("UOM_MISMATCH")
    exceeded = led[led["status"] == "EXCEEDED"]
    exc_keys = set(zip(exceeded["supplier_id"], exceeded["product_family"], exceeded["week_start_date"]))
    for r_ in pe2[~pe2["is_duplicate"]].itertuples():
        if (r_.supplier_id, r_.product_family, r_.ws) in exc_keys and r_.status != "CANCELLED":
            dq_pairs[(r_.sku_id, r_.ship_to_location_id)].add("SUPPLIER_CAPACITY_EXCEEDED")
    miss_skus = set(miss_lt["sku_id"])

    # -------------------------------------------------------------- Stage 6: shortage episodes
    short = closing < ss[:, None]
    eps = []
    for p in np.nonzero(short.any(1))[0]:
        m = short[p].astype(int)
        d = np.diff(np.concatenate([[0], m, [0]]))
        for st, en in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1):
            seg = ss[p] - closing[p, st: en + 1]
            k = int(np.argmax(seg))
            eps.append({"p": int(p), "st": int(st) + 1, "en": int(en) + 1, "pw": int(st) + k + 1, "D": int(seg[k]),
                        "type": "STOCKOUT" if closing[p, st: en + 1].min() < 0 else "SAFETY_STOCK_BREACH"})
    price_of = sku_t["unit_price"].to_dict()
    cost_of = sku_t["unit_cost"].to_dict()
    for e in eps:
        s, l = pair_mi[e["p"]]
        e["sku"], e["loc"] = s, l
        e["price"] = float(price_of[s])
        e["var"] = e["D"] * e["price"]
        e["weeks"] = e["en"] - e["st"] + 1
        e["dem"] = int((D[e["p"], e["st"] - 1: e["en"]] + DEP[e["p"], e["st"] - 1: e["en"]]).sum())
    for i, e in enumerate(eps, start=1):  # IDs by sorted (sku, location, start week): stable & immutable
        e["id"] = ids.short(i)
    pol = policy
    maxv = max([e["var"] for e in eps], default=1.0) or 1.0
    for e in eps:
        urg = 1.0 - min(e["st"] - 1, 12) / 12.0
        gap = min(1.0, e["D"] / max(1, e["dem"]))
        crit = pol["criticality_weight"][sku_t.at[e["sku"], "criticality"]]
        w_ = pol["priority_weights"]
        e["score"] = round(100.0 * (w_["urgency"] * urg + w_["value"] * (e["var"] / maxv) + w_["criticality"] * crit + w_["service_gap"] * gap), 2)
    order = sorted(eps, key=lambda e: (-e["score"], e["st"], e["sku"], e["loc"]))
    for rank, e in enumerate(order, start=1):
        e["rank"] = rank

    # -------------------------------------------------------------- Stage 7: cause attribution (waterfall)
    causes = []
    min_lead = {}
    ltd = T["LeadTime"]
    for r_ in ltd.itertuples():
        min_lead[r_.sku_id] = min(min_lead.get(r_.sku_id, 10 ** 6), int(r_.total_lead_days))
    for e in eps:
        s, l, p, pw, rem = e["sku"], e["loc"], e["p"], e["pw"], e["D"]
        cs = []

        def take(code, q, tbl, rid, text):
            nonlocal rem
            q = min(rem, int(q))
            if q > 0:
                cs.append((code, q, tbl, rid, text))
                rem -= q
        pos = sorted(pair_pos.get((s, l), []), key=lambda x: x["po"])
        for x in pos:
            if x["status"] in OPEN and x["req_w"] <= pw < x["eta_w"]:
                if x["prom_w"] > pw:
                    code = "SUPPLIER_CAPACITY" if x["util"] >= pol["supplier_util_constrained_pct"] else "INBOUND_LATE_SUPPLIER"
                    txt = f"PO {x['po']} promised after need week {W.label(pw)} (supplier utilisation {x['util']:.0f}%)"
                else:
                    code = "INBOUND_LATE_TRANSPORT"
                    txt = f"PO {x['po']} ETA {x['eta']} slipped past need week {W.label(pw)} due to transport delay"
                take(code, x["qty"], "PurchaseOrder", x["po"], txt)
        for x in pos:
            if x["status"] == "CANCELLED" and x["req_w"] <= pw:
                take("INBOUND_CANCELLED", x["qty"], "PurchaseOrder", x["po"], f"PO {x['po']} was cancelled")
        for (w_, q_, pid, code) in sorted(plan_cut.get((s, l), [])):
            if w_ <= pw:
                take(code, q_, "ProductionPlan", pid, f"plan {pid} reduced/cancelled ({code.lower()})")
        for (w_, q_, did) in sorted(spikes.get(p, [])):
            if w_ <= pw:
                take("DEMAND_SPIKE", max(0, q_ - int(med[p])), "ForecastDemand", did, f"forecast {q_} vs median {int(med[p])}")
        if rem > 0:
            invid = ids.inv(s, l)
            if sku_t.at[s, "sku_type"] == "FINISHED_MAKE":
                take("PRODUCTION_PLAN_SHORTFALL", rem, "Inventory", invid, "planned production below forecast + safety stock")
            elif not any(x["status"] != "CANCELLED" for x in pos):
                need_d = (W.week_start(e["st"]) - as_of_d).days
                if need_d < min_lead.get(s, 0):
                    take("INSUFFICIENT_LEAD_TIME", rem, "Inventory", invid, f"need in {need_d} d < shortest lead time {min_lead[s]} d")
                else:
                    take("NO_INBOUND_PLANNED", rem, "Inventory", invid, "no open inbound order covers the need")
            else:
                take("INBOUND_QTY_SHORTFALL", rem, "Inventory", invid, "open inbound quantity below forecast + safety stock")
        e["causes"] = cs
        e["primary"] = max(cs, key=lambda c: c[1])[0]
        e["dqflag"] = "SHORTAGE_MISSING_LEAD_TIME" if s in miss_skus else \
            next((f for f in ("INBOUND_DOUBLE_COUNT", "UOM_MISMATCH", "SUPPLIER_CAPACITY_EXCEEDED") if f in dq_pairs.get((s, l), set())), "NONE")

    # -------------------------------------------------------------- Stage 9: mitigation options
    sup_status = sup_t["status"].to_dict()
    sku_sup = defaultdict(list)
    for r_ in T["SKUSupplier"].sort_values(["sku_id", "is_preferred", "supplier_id"], ascending=[True, False, True]).itertuples():
        sku_sup[r_.sku_id].append((r_.supplier_id, int(r_.is_preferred), r_.approval_status, float(r_.unit_price)))
    lt_rows = defaultdict(list)
    for r_ in ltd.itertuples():
        if r_.effective_from <= as_of and (r_.effective_to is None or pd.isna(r_.effective_to) or as_of < r_.effective_to):
            lt_rows[(r_.supplier_id, r_.sku_id)].append((r_.ship_to_location_id if isinstance(r_.ship_to_location_id, str) else None,
                                                         int(r_.total_lead_days), r_.transport_mode, r_.effective_from))

    def lt_lookup(sup, sku, loc):
        rows = lt_rows.get((sup, sku), [])
        pref = [x for x in rows if x[0] == loc] or [x for x in rows if x[0] is None]
        return max(pref, key=lambda x: x[3]) if pref else None
    caprows = defaultdict(list)
    for r_ in T["SupplierCapacity"][T["SupplierCapacity"]["status"] == "ACTIVE"].itertuples():
        caprows[(r_.supplier_id, r_.product_family)].append((r_.effective_from, None if pd.isna(r_.effective_to) else r_.effective_to,
                                                             int(r_.weekly_capacity_qty), int(r_.min_order_qty), int(r_.order_multiple)))

    def cap_at(sup, fam, ws):
        c = [x for x in caprows.get((sup, fam), []) if x[0] <= ws and (x[1] is None or ws < x[1])]
        return max(c, key=lambda x: x[0]) if c else None
    committed = {(a, b, c): int(q) for a, b, c, q in zip(led["supplier_id"], led["product_family"], led["week_start_date"], led["committed_qty"])}
    subs = defaultdict(list)
    for r_ in T["SKUSubstitute"].itertuples():
        subs[r_.sku_id].append(r_)
    unappr_keys = {dq.sub_key(r_.sku_id, r_.substitute_sku_id, r_.effective_from) for r_ in unappr.itertuples()}
    pairs_of_sku = defaultdict(list)
    for (s_, l_), i_ in pair_of.items():
        pairs_of_sku[s_].append(i_)
    resv = defaultdict(float)
    min_sur = lambda p_, from_w: int(max(0, (closing[p_, from_w - 1:] - ss[p_]).min()))  # noqa: E731
    mit_rows, sh_rows = [], []

    for e in order:  # priority order: higher-priority recommendations reserve capacity first
        s, l, p, D_, p0 = e["sku"], e["loc"], e["p"], e["D"], e["st"]
        price = e["price"]
        ucost = float(cost_of[s])
        fam = sku_t.at[s, "product_family"]
        opts = []

        def mk(otype, **kw):
            base = dict(option_type=otype, supplier_id=None, alt_sku_id=None, source_location_id=None, ref_po_id=None,
                        production_plan_id=None, qty=0, covered_qty=0, unit_cost=ucost, expedite_premium=0.0, freight_cost=0.0,
                        excess_cost=0.0, penalty_cost=0.0, lead_days=None, earliest_arrival_date=None, weeks_late=0,
                        capacity_available_qty=None, capacity_check="NA", policy_check="PASS", policy_reason=None,
                        lead_time_check="NA", approval_required_role="PLANNER", blocked=False, res=None)
            base.update(kw)
            opts.append(base)

        # -- expedite late open POs
        pos = [x for x in pair_pos.get((s, l), []) if x["status"] in ("CONFIRMED", "IN_TRANSIT", "DELAYED") and x["eta_w"] > p0]
        for x in sorted(pos, key=lambda x: (-x["qty"], x["po"]))[: pol["max_expedite_pos"]]:
            gain = min(pol["expedite_max_days_gain"], max(0, (_d(x["eta"]) - (as_of_d + timedelta(days=pol["expedite_min_days"]))).days))
            if gain <= 0:
                continue
            new_eta = _d(x["eta"]) - timedelta(days=gain)
            arr_w = W.week_of(new_eta)
            cov = min(x["qty"], D_)
            reasons = []
            if sup_status[x["sup"]] != "ACTIVE":
                reasons.append("SUPPLIER_NOT_ACTIVE")
            if pol["expedite_premium_pct"] > pol["expedite_premium_cap_pct"]:
                reasons.append("EXPEDITE_PREMIUM_OVER_CAP")
            mk("EXPEDITE_PO", supplier_id=x["sup"], ref_po_id=x["po"], qty=x["qty"], covered_qty=cov, unit_cost=x["price"],
               expedite_premium=round(cov * x["price"] * pol["expedite_premium_pct"] / 100, 2),
               freight_cost=round(cov * x["price"] * pol["expedite_freight_pct"] / 100, 2), lead_days=(new_eta - as_of_d).days,
               earliest_arrival_date=_s(new_eta), weeks_late=max(0, arr_w - p0), capacity_available_qty=x["qty"],
               capacity_check="PASS", policy_check="FAIL" if reasons else "PASS", policy_reason=";".join(reasons) or None,
               lead_time_check="OK" if arr_w <= p0 else "LATE")
        # -- new PO / alternative supplier PO
        if sku_t.at[s, "sku_type"] != "FINISHED_MAKE":
            n_alt = 0
            for (sup, pref, appr, sp_) in sku_sup.get(s, []):
                if not pref:
                    if n_alt >= pol["max_alt_suppliers"]:
                        continue
                    n_alt += 1
                reasons = []
                if sup_status[sup] != "ACTIVE":
                    reasons.append("SUPPLIER_NOT_ACTIVE")
                if appr != "APPROVED":
                    reasons.append("SUPPLIER_NOT_APPROVED")
                lt = lt_lookup(sup, s, l)
                otype = "NEW_PO" if pref else "ALT_SUPPLIER_PO"
                if lt is None:
                    mk(otype, supplier_id=sup, unit_cost=sp_, policy_check="FAIL" if reasons else "PASS",
                       policy_reason=";".join(reasons + ["MISSING_LEAD_TIME"]), lead_time_check="MISSING", blocked=True)
                    continue
                arr = as_of_d + timedelta(days=lt[1])
                arr_w = W.week_of(arr)
                cr = cap_at(sup, fam, ws_asof)
                if cr is None:
                    mk(otype, supplier_id=sup, unit_cost=sp_, policy_check="FAIL", policy_reason=";".join(reasons + ["NO_CAPACITY_RECORD"]),
                       lead_days=lt[1], earliest_arrival_date=_s(arr), lead_time_check="OK" if arr_w <= p0 else "LATE", capacity_check="FAIL",
                       capacity_available_qty=0)
                    continue
                remaining = max(0, cr[2] - committed.get((sup, fam, ws_asof), 0) - int(resv[("SUP", sup, fam, ws_asof)]))
                moq, mult = cr[3], cr[4]
                want = max(moq, dq_ru(D_, mult))
                qty = want if remaining >= want else ((remaining // mult) * mult if remaining >= moq else 0)
                cov = min(qty, D_)
                frt = pol["freight_pct"][sup_t.at[sup, "region"]]
                mk(otype, supplier_id=sup, qty=qty, covered_qty=cov, unit_cost=sp_,
                   freight_cost=round(qty * sp_ * frt / 100, 2),
                   penalty_cost=round(max(0.0, sp_ - float(sku_sup[s][0][3])) * qty, 2),
                   excess_cost=round(max(0, qty - D_) * sp_ * pol["holding_cost_pct_excess"] / 100, 2), lead_days=lt[1],
                   earliest_arrival_date=_s(arr), weeks_late=max(0, arr_w - p0), capacity_available_qty=remaining,
                   capacity_check="PASS" if qty > 0 else "FAIL", policy_check="FAIL" if reasons else "PASS",
                   policy_reason=";".join(reasons) or None, lead_time_check="OK" if arr_w <= p0 else "LATE",
                   approval_required_role="OPS_MANAGER" if qty * sp_ > pol["approval_spend_threshold"] else "PLANNER",
                   res=("SUP", sup, fam, ws_asof, qty))
        # -- substitutes (every link is evaluated; non-approved ones are kept for audit and rejected by policy)
        for sb in subs.get(s, []):
            a = sb.substitute_sku_id
            reasons = []
            key = dq.sub_key(sb.sku_id, a, sb.effective_from)
            if key in unappr_keys:
                reasons.append("SUBSTITUTE_NOT_APPROVED" if sb.approval_status != "APPROVED" else "SUBSTITUTE_OUT_OF_EFFECTIVE_WINDOW")
            q_ = pair_of.get((a, l))
            ratio = float(sb.substitution_ratio)
            need_alt = int(math.ceil(D_ * ratio - 1e-9))
            if q_ is None:
                mk("SUBSTITUTE_SKU", alt_sku_id=a, policy_check="FAIL" if reasons else "PASS",
                   policy_reason=";".join(reasons + ["SUBSTITUTE_NOT_STOCKED_AT_LOCATION"]), capacity_check="FAIL", capacity_available_qty=0)
                continue
            sur = max(0, min_sur(q_, p0) - int(resv[("ALT", q_)]))
            qa = min(need_alt, sur)
            cov = int(qa / ratio + 1e-9)
            ap_ = float(price_of[a])
            mk("SUBSTITUTE_SKU", alt_sku_id=a, qty=qa, covered_qty=min(cov, D_), unit_cost=float(cost_of[a]),
               penalty_cost=round(qa * ap_ * float(sb.cost_penalty_pct) / 100 + qa * max(0.0, ap_ - price), 2), lead_days=0,
               earliest_arrival_date=as_of, capacity_available_qty=sur, capacity_check="PASS" if qa > 0 else "FAIL",
               policy_check="FAIL" if reasons else "PASS", policy_reason=";".join(reasons) or None, lead_time_check="OK",
               res=("ALT", q_, qa))
        # -- transfers from donor locations that stay above their own safety stock
        donors = []
        for q_ in pairs_of_sku.get(s, []):
            if q_ == p:
                continue
            sur = max(0, min_sur(q_, 1) - int(resv[("DON", q_)]))
            if sur > 0:
                donors.append((-sur, pair_mi[q_][1], q_, sur))
        for (_, dloc, q_, sur) in sorted(donors)[: pol["max_transfer_donors"]]:
            same = loc_t.at[dloc, "region"] == loc_t.at[l, "region"]
            lead = pol["transfer_lead_days"]["same_region" if same else "other_region"]
            qty = min(D_, sur)
            arr = as_of_d + timedelta(days=lead)
            mk("LOCATION_TRANSFER", source_location_id=dloc, qty=qty, covered_qty=qty,
               freight_cost=round(qty * price * pol["transfer_freight_pct"]["same_region" if same else "other_region"] / 100, 2),
               lead_days=lead, earliest_arrival_date=_s(arr), weeks_late=max(0, W.week_of(arr) - p0), capacity_available_qty=sur,
               capacity_check="PASS", lead_time_check="OK" if W.week_of(arr) <= p0 else "LATE", res=("DON", q_, qty))
        # -- production re-plan using spare work-centre hours
        if sku_t.at[s, "sku_type"] == "FINISHED_MAKE" and s in bom_of_sku:
            rt, lot = bom_of_sku[s]["run_time_hours_per_unit"], int(bom_of_sku[s]["lot_size"])
            wc = wc_of_pair.get((s, l))
            fw = pol["production_frozen_weeks"]
            found = None
            if wc and p0 > fw:
                for w_ in range(p0, fw, -1):
                    spare = cap_h.get((wc, w_), 0.0) - used_hours.get((wc, w_), 0.0) - resv[("HRS", wc, w_)]
                    units = int(max(0.0, spare) / rt // lot * lot)
                    if units > 0:
                        found = (w_, units)
                        break
            if found:
                w_, units = found
                qty = min(dq_ru(D_, lot), units)
                mk("PRODUCTION_REPLAN", qty=qty, covered_qty=min(qty, D_), freight_cost=0.0,
                   expedite_premium=round(qty * ucost * pol["production_changeover_pct"] / 100, 2),
                   lead_days=(W.week_start(w_) - as_of_d).days, earliest_arrival_date=W.week_start_s(w_), capacity_available_qty=units,
                   capacity_check="PASS", production_plan_id=plan_id_at.get((s, l, w_)), lead_time_check="OK",
                   res=("HRS", wc, w_, qty * rt))
            else:
                mk("PRODUCTION_REPLAN", capacity_check="FAIL", capacity_available_qty=0,
                   policy_check="FAIL" if p0 <= fw else "PASS", policy_reason="WITHIN_FROZEN_HORIZON" if p0 <= fw else "NO_SPARE_CAPACITY")
        # -- accept backorder (always available: guarantees a cost/service alternative)
        bo = round(D_ * price * pol["backorder_cost_pct_per_week"] / 100 * e["weeks"], 2)
        mk("PARTIAL_FILL_BACKORDER", penalty_cost=bo, weeks_late=e["weeks"], capacity_check="NA", lead_time_check="NA")
        # -- derive, rank, reserve
        for i_, o in enumerate(opts, start=1):
            o["seq"] = i_
            o["total_cost"] = round(o["expedite_premium"] + o["freight_cost"] + o["excess_cost"] + o["penalty_cost"], 2)
            o["fill"] = _fill(o["covered_qty"], D_, o["weeks_late"], e["weeks"]) if o["option_type"] != "PARTIAL_FILL_BACKORDER" else 0.0
            o["recommendable"] = int(o["policy_check"] == "PASS" and o["capacity_check"] != "FAIL" and o["lead_time_check"] != "MISSING"
                                     and (o["covered_qty"] > 0 or o["option_type"] == "PARTIAL_FILL_BACKORDER"))
        base_cost = opts[-1]["total_cost"]
        ranked = sorted(opts, key=lambda o: (0 if o["recommendable"] else 1, -round(o["fill"] / 5), o["total_cost"],
                                             TYPE_ORDER[o["option_type"]], o["supplier_id"] or "", o["seq"]))
        for rk, o in enumerate(ranked, start=1):
            o["rank"] = rk
            o["is_rec"] = int(rk == 1 and o["recommendable"])
            o["cost_delta"] = round(o["total_cost"] - base_cost, 2)
        top = ranked[0]
        if top["is_rec"] and top["res"]:
            r_ = top["res"]
            if r_[0] == "SUP":
                resv[("SUP", r_[1], r_[2], r_[3])] += r_[4]
            elif r_[0] in ("ALT", "DON"):
                resv[(r_[0], r_[1])] += r_[2]
            elif r_[0] == "HRS":
                resv[("HRS", r_[1], r_[2])] += r_[3]
        e["opts"] = opts

    # -------------------------------------------------------------- assemble output tables
    findings = []

    def fnd(issue, entity, rid, rel, qty, detail):
        findings.append({"issue_type": issue, "entity": entity, "record_id": rid, "related_record_ids": rel, "impact_qty": qty, "detail": detail})
    for r_ in pe[pe["is_duplicate"]].sort_values("po_id").itertuples():
        fnd("INBOUND_DOUBLE_COUNT", "PurchaseOrder", r_.po_id, r_.duplicate_of, int(r_.qty_eff),
            f"duplicate of {r_.duplicate_of}: same supplier/SKU/ship-to/promised date/supplier_ref_no; excluded from supply")
    for r_ in pe[pe["uom_mismatch"]].sort_values("po_id").itertuples():
        fnd("UOM_MISMATCH", "PurchaseOrder", r_.po_id, None, int(abs(r_.qty_recorded - r_.qty_eff)),
            f"qty_base {r_.qty_recorded} != order_qty x factor = {r_.qty_eff}; engine uses the recomputed quantity")
    for r_ in pe[pe["factor_missing"]].sort_values("po_id").itertuples():
        fnd("UOM_FACTOR_MISSING", "PurchaseOrder", r_.po_id, None, int(r_.qty_recorded), "no UoM conversion; excluded from supply")
    for r_ in exceeded.itertuples():
        fnd("SUPPLIER_CAPACITY_EXCEEDED", "SupplierCapacityLedger", dq.cap_key(r_.supplier_id, r_.product_family, r_.week_start_date), None,
            int(r_.committed_qty - r_.capacity_qty), f"committed {r_.committed_qty} > capacity {r_.capacity_qty}")
    sh_by_sku = defaultdict(list)
    for e in eps:
        sh_by_sku[e["sku"]].append(e["id"])
    for r_ in miss_lt.itertuples():
        if r_.sku_id in sh_by_sku:
            fnd("SHORTAGE_MISSING_LEAD_TIME", "LeadTime", dq.lt_key(r_.supplier_id, r_.sku_id), "|".join(sh_by_sku[r_.sku_id][:5]), None,
                "shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review")
    for r_ in unappr.itertuples():
        if r_.sku_id in sh_by_sku:
            fnd("SUBSTITUTE_NOT_APPROVED", "SKUSubstitute", dq.sub_key(r_.sku_id, r_.substitute_sku_id, r_.effective_from),
                "|".join(sh_by_sku[r_.sku_id][:5]), None, f"substitute status {r_.approval_status}: option kept for audit, never recommended")
    for i, f_ in enumerate(findings, start=1):
        f_["finding_id"] = f"DQF-{i:06d}"
        f_["run_id"] = run_id

    shs, cs_rows, mit, she, mie = [], [], [], [], []
    ec = {"she": 0, "mie": 0}

    def nid(k):
        ec[k] += 1
        return f"{'SHE' if k == 'she' else 'MIE'}-{ec[k]:06d}"
    for e in eps:
        needs = e["dqflag"] == "SHORTAGE_MISSING_LEAD_TIME"
        final = "NEEDS_REVIEW" if needs else "MITIGATION_PROPOSED"
        shs.append({"shortage_id": e["id"], "run_id": run_id, "sku_id": e["sku"], "location_id": e["loc"],
                    "first_short_week": W.label(e["st"]), "last_short_week": W.label(e["en"]), "peak_short_week": W.label(e["pw"]),
                    "need_by_date": W.week_start_s(e["st"]), "episode_weeks": e["weeks"], "shortage_type": e["type"],
                    "shortage_qty": e["D"], "value_at_risk": round(e["var"], 2), "priority_score": e["score"],
                    "priority_rank": e["rank"], "primary_cause_code": e["primary"], "data_quality_flag": e["dqflag"], "status": final})
        prev = None
        for to, cm in (("DETECTED", "shortfall found in projected balance"), ("ANALYZED", f"{len(e['causes'])} cause record(s) attributed"),
                       (final, "lead time missing: supplier mitigations blocked" if needs else f"{len(e['opts'])} mitigation option(s) generated")):
            she.append({"event_id": nid("she"), "shortage_id": e["id"], "from_status": prev, "to_status": to, "event_date": as_of,
                        "actor_role": "SYSTEM", "comment": cm})
            prev = to
        for k, (code, q, tbl, rid, txt) in enumerate(e["causes"], start=1):
            cs_rows.append({"shortage_id": e["id"], "cause_seq": k, "cause_code": code, "contribution_qty": q,
                            "source_table": tbl, "source_id": rid, "explanation": txt})
        for o in e["opts"]:
            mid = ids.mit(e["id"], o["seq"])
            mit.append({"mitigation_id": mid, "shortage_id": e["id"], "option_type": o["option_type"], "supplier_id": o["supplier_id"],
                        "alt_sku_id": o["alt_sku_id"], "source_location_id": o["source_location_id"], "ref_po_id": o["ref_po_id"],
                        "production_plan_id": o["production_plan_id"], "qty": o["qty"], "covered_qty": o["covered_qty"],
                        "unit_cost": o["unit_cost"], "expedite_premium": o["expedite_premium"], "freight_cost": o["freight_cost"],
                        "excess_cost": o["excess_cost"], "penalty_cost": o["penalty_cost"], "total_cost": o["total_cost"],
                        "cost_delta_vs_baseline": o["cost_delta"], "lead_days": o["lead_days"],
                        "earliest_arrival_date": o["earliest_arrival_date"], "weeks_late": o["weeks_late"], "fill_rate_pct": o["fill"],
                        "capacity_available_qty": o["capacity_available_qty"], "capacity_check": o["capacity_check"],
                        "policy_check": o["policy_check"], "policy_reason": o["policy_reason"], "lead_time_check": o["lead_time_check"],
                        "approval_required_role": o["approval_required_role"], "is_recommendable": o["recommendable"], "rank": o["rank"],
                        "is_recommended": o["is_rec"], "status": "PROPOSED" if o["recommendable"] else "REJECTED"})
            mie.append({"event_id": nid("mie"), "mitigation_id": mid, "from_status": None, "to_status": "PROPOSED", "event_date": as_of,
                        "actor_role": "SYSTEM", "comment": "generated by planning engine"})
            if not o["recommendable"]:
                mie.append({"event_id": nid("mie"), "mitigation_id": mid, "from_status": "PROPOSED", "to_status": "REJECTED",
                            "event_date": as_of, "actor_role": "SYSTEM",
                            "comment": o["policy_reason"] or ("capacity" if o["capacity_check"] == "FAIL" else "no coverage")})

    ledger_out = led.assign(run_id=run_id, iso_week=[W.label(W.week_of(x)) for x in led["week_start_date"]])
    out = {
        "PlanRun": pd.DataFrame([{"run_id": run_id, "as_of_date": as_of, "seed": seed, "profile": profile, "engine_version": ENGINE_VERSION,
                                  "policy_hash": policy_hash(policy), "n_pairs": nP, "n_shortages": len(eps)}]),
        "ProjectedBalance": pb, "SupplierCapacityLedger": ledger_out, "Shortage": pd.DataFrame(shs),
        "ShortageCause": pd.DataFrame(cs_rows), "MitigationOption": pd.DataFrame(mit), "ShortageEvent": pd.DataFrame(she),
        "MitigationEvent": pd.DataFrame(mie), "DataQualityFinding": pd.DataFrame(findings),
    }
    for k in out:
        if len(out[k]) == 0:
            out[k] = pd.DataFrame(columns=__import__("oryva.schema", fromlist=["T"]).T[k].cols)
        out[k] = finalize(k, out[k])
    ctx = {"episodes": eps, "closing": closing, "inv": inv, "pe": pe, "ledger": led, "pair_of": pair_of, "R": R, "D": D, "DEP": DEP, "Prod": Prod}
    return out, ctx


def dq_ru(x, m):
    return int(-(-int(x) // int(m)) * int(m))


def _s(d):
    return d if isinstance(d, str) else d.isoformat()
