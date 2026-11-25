"""Optimisation engine: choose ONE mitigation per shortage to minimise total cost (action cost + cost of uncovered
demand) subject to shared-resource constraints (supplier weekly capacity, donor surplus above safety stock, substitute
surplus, work-centre spare hours, expedite PO quantity) and an optional service-level floor.

Method (pure numpy; scipy is not available on the target machine): Lagrangian relaxation of the resource constraints
with sub-gradient updates, followed by a deterministic greedy repair, so the returned plan ALWAYS satisfies every
constraint (verified by `check_constraints`).  The dual bound gives an optimality gap for each strategy.
Candidates are limited to options the planning engine marked recommendable (policy, lead-time, capacity checks passed)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import weeks as W


def build_candidates(T: dict, out: dict, policy: dict) -> tuple[pd.DataFrame, dict]:
    mo, sh = out["MitigationOption"], out["Shortage"]
    sku = T["SKU"].set_index("sku_id")
    rate = policy["backorder_cost_pct_per_week"] / 100.0
    c = mo[mo["is_recommendable"] == 1].merge(
        sh[["shortage_id", "sku_id", "location_id", "shortage_qty", "episode_weeks", "priority_rank", "need_by_date"]], on="shortage_id")
    price = c["sku_id"].map(sku["unit_price"])
    c["eff_cover"] = c["shortage_qty"] * c["fill_rate_pct"] / 100.0
    c["unmet_units"] = c["shortage_qty"] - c["eff_cover"]
    c["unmet_cost"] = c["unmet_units"] * price * rate * c["episode_weeks"]
    isbo = c["option_type"] == "PARTIAL_FILL_BACKORDER"
    c["action_cost"] = np.where(isbo, 0.0, c["total_cost"])
    c["J"] = c["action_cost"] + c["unmet_cost"]
    pb = out["ProjectedBalance"]
    sur = (pb["closing_qty"] - pb["safety_stock_qty"]).groupby([pb["sku_id"], pb["location_id"]]).min().clip(lower=0).astype(int)
    ledger = out["SupplierCapacityLedger"]
    as_of = str(T["Inventory"]["as_of_date"].iloc[0])
    ws = pd.Timestamp(as_of)
    ws = (ws - pd.Timedelta(days=ws.weekday())).strftime("%Y-%m-%d")
    com = {(a, b): q for a, b, c_, q in zip(ledger["supplier_id"], ledger["product_family"], ledger["week_start_date"], ledger["committed_qty"]) if c_ == ws}
    pp = T["ProductionPlan"]
    wc_of = pp.groupby(["sku_id", "location_id"])["work_center_id"].first().to_dict()
    bom = T["BillOfMaterial"].set_index("parent_sku_id")["run_time_hours_per_unit"]
    avail_h = T["ProductionCapacity"].set_index(["work_center_id", "week_start_date"])["available_hours"]
    req_h = pp.groupby(["work_center_id", "week_start_date"])["required_hours"].sum()
    from .. import dq
    pe = dq.po_effective(T)
    po = pe.set_index("po_id")["qty_eff"]  # unit-of-measure corrected quantities
    closing = {k: g.sort_values("week_start_date")["closing_qty"].to_numpy() for k, g in pb.groupby(["sku_id", "location_id"])}
    ssq = pb.groupby(["sku_id", "location_id"])["safety_stock_qty"].first()
    c["p0"] = [W.week_of(d) for d in c["need_by_date"]]
    alt_p0 = c[c["option_type"] == "SUBSTITUTE_SKU"].groupby(["alt_sku_id", "location_id"])["p0"].min().to_dict()
    keys, amts, caps = [], [], {}
    from ..advanced.replenish import _cap_row
    for r in c.itertuples():
        k, a = None, 0.0
        if r.option_type in ("NEW_PO", "ALT_SUPPLIER_PO"):
            fam = sku.at[r.sku_id, "product_family"]
            k = ("SUP", r.supplier_id, fam, ws)
            if k not in caps:
                cr = _cap_row(T, r.supplier_id, fam, ws)
                caps[k] = max(0, (int(cr["weekly_capacity_qty"]) if cr is not None else 0) - com.get((r.supplier_id, fam), 0))
            a = float(r.qty)
        elif r.option_type == "LOCATION_TRANSFER":
            k = ("DON", r.sku_id, r.source_location_id)
            caps[k] = int(sur.get((r.sku_id, r.source_location_id), 0))
            a = float(r.qty)
        elif r.option_type == "SUBSTITUTE_SKU":
            k = ("ALT", r.alt_sku_id, r.location_id)
            arr = closing.get((r.alt_sku_id, r.location_id))
            p0 = alt_p0[(r.alt_sku_id, r.location_id)]  # earliest week any shortage starts consuming this substitute
            caps[k] = max(0, int((arr[p0 - 1:] - ssq[(r.alt_sku_id, r.location_id)]).min())) if arr is not None else 0
            a = float(r.qty)
        elif r.option_type == "PRODUCTION_REPLAN":
            wc = wc_of.get((r.sku_id, r.location_id))
            wk = r.earliest_arrival_date
            k = ("HRS", wc, wk)
            caps[k] = max(0.0, float(avail_h.get((wc, wk), 0.0)) - float(req_h.get((wc, wk), 0.0)))
            a = float(r.qty) * float(bom.get(r.sku_id, 0.0))
        elif r.option_type == "EXPEDITE_PO":
            k = ("PO", r.ref_po_id)
            caps[k] = int(po.get(r.ref_po_id, 0))
            a = float(r.covered_qty)
        keys.append(k)
        amts.append(a)
    c["res_key"], c["res_amt"] = keys, amts
    return c.sort_values(["priority_rank", "mitigation_id"], kind="mergesort").reset_index(drop=True), caps


def _solve(c: pd.DataFrame, caps: dict, mu: float = 0.0, iters: int = 80) -> tuple[np.ndarray, float]:
    """Return (chosen row index per shortage, dual lower bound) for objective J - mu*eff_cover."""
    sid = pd.factorize(c["shortage_id"])[0]
    n_s = sid.max() + 1
    base = (c["J"] - mu * c["eff_cover"]).to_numpy(float)
    keys = {k: i for i, k in enumerate(caps)}
    rid = np.array([keys.get(k, -1) if k is not None else -1 for k in c["res_key"]])
    amt = c["res_amt"].to_numpy(float)
    cap = np.array([caps[k] for k in keys], float) if keys else np.zeros(0)
    lam = np.zeros(len(cap))
    order = np.argsort(sid, kind="stable")
    starts = np.r_[0, np.nonzero(np.diff(sid[order]))[0] + 1]

    def pick(l):
        adj = base + np.where(rid >= 0, l[np.maximum(rid, 0)] * amt, 0.0)
        mins = np.minimum.reduceat(adj[order], starts)
        # first option attaining the minimum within each shortage (deterministic)
        chosen = np.empty(n_s, int)
        o_adj = adj[order]
        for s_i, st in enumerate(starts):
            en = starts[s_i + 1] if s_i + 1 < len(starts) else len(order)
            chosen[s_i] = order[st + int(np.argmin(o_adj[st:en]))]
        return chosen, mins

    best_lb, chosen = -np.inf, None
    step0 = max(1e-9, float(np.median(base[base > 0])) if (base > 0).any() else 1.0)
    for it in range(iters):
        chosen, mins = pick(lam)
        lb = float(mins.sum() - (lam * cap).sum())
        best_lb = max(best_lb, lb)
        use = np.zeros(len(cap))
        sel_r, sel_a = rid[chosen], amt[chosen]
        np.add.at(use, sel_r[sel_r >= 0], sel_a[sel_r >= 0])
        viol = use - cap
        if len(cap) == 0 or (viol <= 1e-9).all():
            break
        scale = np.maximum(cap, 1.0)
        lam = np.maximum(0.0, lam + (step0 / (1 + it)) * (viol / scale) / max(1.0, 0.1 * np.sqrt(it + 1)) * (viol > 0))
    # deterministic greedy repair so the result is always feasible
    chosen = chosen.copy()
    sel_r = rid[chosen]
    use = np.zeros(len(cap))
    np.add.at(use, sel_r[sel_r >= 0], amt[chosen][sel_r >= 0])
    guard = 0
    while len(cap) and (use > cap + 1e-9).any() and guard < 10000:
        guard += 1
        r = int(np.argmax(use - cap))
        users = [s_i for s_i in range(n_s) if rid[chosen[s_i]] == r]
        best = None
        for s_i in users:
            st = starts[s_i]
            en = starts[s_i + 1] if s_i + 1 < len(starts) else len(order)
            for o in order[st:en]:
                ro = rid[o]
                if o == chosen[s_i]:
                    continue
                if ro >= 0 and ro != r and use[ro] + amt[o] > cap[ro] + 1e-9:
                    continue
                if ro == r:
                    continue
                regret = (base[o] - base[chosen[s_i]]) / max(amt[chosen[s_i]], 1e-9)
                if best is None or regret < best[0]:
                    best = (regret, s_i, o)
        if best is None:
            break
        _, s_i, o = best
        use[r] -= amt[chosen[s_i]]
        if rid[o] >= 0:
            use[rid[o]] += amt[o]
        chosen[s_i] = o
    return chosen, best_lb


def evaluate(c: pd.DataFrame, chosen: np.ndarray, caps: dict, lb: float | None = None, mu: float = 0.0) -> dict:
    s = c.iloc[chosen]
    D = float(s["shortage_qty"].sum())
    out = {"shortages": len(s), "action_cost": round(float(s["action_cost"].sum()), 2), "uncovered_cost": round(float(s["unmet_cost"].sum()), 2),
           "total_cost": round(float(s["J"].sum()), 2), "uncovered_units": round(float(s["unmet_units"].sum()), 1),
           "service_pct": round(100 * float(s["eff_cover"].sum()) / D, 2) if D else 100.0,
           "orders": int(s["option_type"].isin(["NEW_PO", "ALT_SUPPLIER_PO"]).sum()),
           "mix": s["option_type"].value_counts().to_dict(), "violations": len(check_constraints(c, chosen, caps))}
    if lb is not None and mu == 0.0 and lb > -np.inf:
        out["dual_lower_bound"] = round(lb, 2)
        out["optimality_gap_pct"] = round(100 * max(0.0, (out["total_cost"] - lb)) / max(out["total_cost"], 1e-9), 2)
    return out


def check_constraints(c: pd.DataFrame, chosen, caps: dict) -> list[dict]:
    """Independent feasibility check of a selection (one option per shortage, every shared resource within capacity)."""
    s = c.iloc[chosen]
    bad = []
    if s["shortage_id"].duplicated().any() or set(s["shortage_id"]) != set(c["shortage_id"]):
        bad.append({"resource": "selection", "used": len(s), "capacity": c["shortage_id"].nunique()})
    use = {}
    for k, a in zip(s["res_key"], s["res_amt"]):
        if k is not None:
            use[k] = use.get(k, 0.0) + a
    bad += [{"resource": str(k), "used": round(u, 3), "capacity": caps[k]} for k, u in use.items() if u > caps[k] + 1e-6]
    if (s["is_recommendable"] != 1).any():
        bad.append({"resource": "policy", "used": int((s["is_recommendable"] != 1).sum()), "capacity": 0})
    return bad


def run_strategies(T: dict, out: dict, policy: dict, service_floor: float = 95.0) -> dict:
    c, caps = build_candidates(T, out, policy)
    if c.empty:
        return {"table": pd.DataFrame(), "selections": {}, "candidates": c, "caps": caps}
    sid = pd.factorize(c["shortage_id"])[0]
    order = np.argsort(sid, kind="stable")
    sel = {}
    # engine (service-first ranking)
    eng = c.index[c["is_recommended"] == 1].to_numpy()
    eng_by_s = {sid[i]: i for i in eng}
    sel["Engine ranking (service first)"] = (np.array([eng_by_s[s] for s in range(sid.max() + 1)]), None, 0.0)
    ch, lb = _solve(c, caps, 0.0)
    sel["Minimum total cost"] = (ch, lb, 0.0)
    # service floor: bisection on the service-value multiplier mu
    lo, hi = 0.0, float(c["J"].max() / max(c["eff_cover"].replace(0, np.nan).min(), 1e-9)) * 10 + 1.0
    best = None
    for _ in range(30):
        mid = (lo + hi) / 2
        ch2, lb2 = _solve(c, caps, mid, iters=40)
        sv = evaluate(c, ch2, caps)["service_pct"]
        if sv >= service_floor:
            best, hi = (ch2, lb2, mid), mid
        else:
            lo = mid
    if best is None:
        ch2, lb2 = _solve(c, caps, hi, iters=40)
        best = (ch2, lb2, hi)
    floor_name = f"Cost-optimal with service >= {service_floor:g}%"
    sel[floor_name] = best
    ch3, lb3 = _solve(c, caps, hi * 5, iters=40)
    sel["Maximum service"] = (ch3, lb3, hi * 5)
    max_service = evaluate(c, ch3, caps)["service_pct"]
    rows = []
    for name, (ch_, lb_, mu_) in sel.items():
        e = evaluate(c, ch_, caps, lb_, mu_)
        row = {"strategy": name, **{k: v for k, v in e.items() if k != "mix"}, "option_mix": ", ".join(f"{k}:{v}" for k, v in e["mix"].items())}
        row["note"] = ""
        if name == floor_name and e["service_pct"] < service_floor - 1e-6:
            row["note"] = f"service floor {service_floor:g}% is NOT attainable under the capacity constraints (maximum achievable {max_service:.2f}%)"
        rows.append(row)
    return {"table": pd.DataFrame(rows), "selections": {k: v[0] for k, v in sel.items()}, "candidates": c, "caps": caps}
