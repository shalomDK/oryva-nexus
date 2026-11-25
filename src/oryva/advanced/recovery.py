"""Multi-shortage recovery planner.

A planner selects several shortages; ORYVA chooses ONE mitigation per shortage so that the set is jointly feasible on
shared constraints (supplier weekly capacity, donor surplus above safety stock, substitute surplus, work-centre spare
hours, quantity of an expedited order) and minimises action cost + cost of uncovered demand.

Candidates, objective and shared-resource capacities come from `optimize.build_candidates` (only options the planning
engine marked recommendable); the coordinated selection uses `optimize._solve` (Lagrangian relaxation + greedy repair).

Every plan is then VERIFIED: all chosen options are applied together to copies of the input tables
(`decision.apply_option`, stacked) and the planning engine is re-run once.  Reported outcomes (gaps, side effects,
service level, new capacity exceedances) come from that recalculation, never from adding up per-option estimates.
Plans compared: no action (current plan), independent best picks (each shortage optimised alone), the engine's own
recommendations, and the coordinated plan."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import weeks as W
from ..planning import run_plan
from . import optimize
from .decision import apply_option
from .scenario import compare

RES_LABEL = {"SUP": "supplier capacity", "DON": "donor stock above safety stock", "ALT": "substitute stock", "HRS": "work-centre spare hours", "PO": "expedited order quantity"}


def _res_text(k) -> str:
    if k is None:
        return "no shared resource"
    kind = k[0]
    if kind == "SUP":
        return f"{RES_LABEL[kind]} of {k[1]} / {k[2]} in the week of {k[3]}"
    if kind == "DON":
        return f"{RES_LABEL[kind]} of {k[1]} at {k[2]}"
    if kind == "ALT":
        return f"{RES_LABEL[kind]} of {k[1]} at {k[2]}"
    if kind == "HRS":
        return f"{RES_LABEL[kind]} on {k[1]} in the week of {k[2]}"
    return f"{RES_LABEL[kind]} of {k[1]}"


def candidates(T: dict, out: dict, policy: dict, shortage_ids: list) -> tuple[pd.DataFrame, dict]:
    c, caps = optimize.build_candidates(T, out, policy)
    c = c[c["shortage_id"].isin(shortage_ids)].reset_index(drop=True)
    return c, {k: v for k, v in caps.items() if k in set(c["res_key"].dropna())}


def _pick_by_shortage(c: pd.DataFrame, idx) -> dict:
    s = c.iloc[list(idx)]
    return dict(zip(s["shortage_id"], s["mitigation_id"]))


def independent_picks(c: pd.DataFrame) -> dict:
    """Each shortage's lowest-objective option, as if it were planned alone (ignores the other selected shortages)."""
    return _pick_by_shortage(c, c.groupby("shortage_id")["J"].idxmin().to_numpy())


def _usage(c: pd.DataFrame, picks: dict) -> dict:
    info = c.set_index("mitigation_id")
    use = {}
    for m in picks.values():
        k = info.at[m, "res_key"]
        if k is not None:
            use[k] = use.get(k, 0.0) + float(info.at[m, "res_amt"])
    return use


def feasible(c: pd.DataFrame, caps: dict, picks: dict) -> bool:
    return all(u <= caps[k] + 1e-9 for k, u in _usage(c, picks).items())


def objective(c: pd.DataFrame, picks: dict) -> float:
    return float(c.set_index("mitigation_id").loc[list(picks.values()), "J"].sum())


def _repair(c: pd.DataFrame, caps: dict, picks: dict) -> dict:
    """While a shared resource is over-subscribed, move the shortage whose switch costs least to an option that does not
    use that resource and fits everything else.  The backorder option uses no resource, so this always terminates."""
    picks = dict(picks)
    info = c.set_index("mitigation_id")
    by = {sid: g.sort_values(["J", "mitigation_id"]) for sid, g in c.groupby("shortage_id")}
    for _ in range(10_000):
        use = _usage(c, picks)
        over = [(u - caps[k], k) for k, u in use.items() if u > caps[k] + 1e-9]
        if not over:
            return picks
        _, k = max(over, key=lambda x: (x[0], str(x[1])))
        best = None
        for sid, m in sorted(picks.items()):
            if info.at[m, "res_key"] != k:
                continue
            for r in by[sid].itertuples():
                if r.mitigation_id == m or r.res_key == k:
                    continue
                if r.res_key is not None and use.get(r.res_key, 0.0) + r.res_amt > caps[r.res_key] + 1e-9:
                    continue
                d = float(r.J) - float(info.at[m, "J"])
                if best is None or (d, sid) < (best[0], best[1]):
                    best = (d, sid, r.mitigation_id)
                break
        if best is None:
            raise RuntimeError("cannot repair plan")  # unreachable: backorder is always available
        picks[best[1]] = best[2]
    raise RuntimeError("repair did not converge")


def _improve(c: pd.DataFrame, caps: dict, picks: dict) -> dict:
    """1-swap local search: switch any shortage to a cheaper option whenever all shared limits still hold."""
    picks = dict(picks)
    info = c.set_index("mitigation_id")
    by = {sid: g.sort_values(["J", "mitigation_id"]) for sid, g in c.groupby("shortage_id")}
    changed = True
    while changed:
        changed = False
        use = _usage(c, picks)
        for sid in sorted(by):
            cur = picks[sid]
            jc, kc, ac = float(info.at[cur, "J"]), info.at[cur, "res_key"], float(info.at[cur, "res_amt"])
            for r in by[sid].itertuples():
                if float(r.J) >= jc - 1e-9:
                    break
                load = use.get(r.res_key, 0.0) - (ac if kc == r.res_key else 0.0)
                if r.res_key is None or load + r.res_amt <= caps[r.res_key] + 1e-9:
                    if kc is not None:
                        use[kc] -= ac
                    if r.res_key is not None:
                        use[r.res_key] = use.get(r.res_key, 0.0) + r.res_amt
                    picks[sid] = r.mitigation_id
                    changed = True
                    break
    return picks


def coordinated_picks(c: pd.DataFrame, caps: dict, engine: dict | None = None) -> tuple[dict, float, str]:
    """Best jointly-feasible plan found from several starts, each improved by local search.  Returns (picks, dual bound, start)."""
    chosen, lb = optimize._solve(c, caps)
    starts = {"repaired independent picks": _repair(c, caps, independent_picks(c)), "Lagrangian solver": _pick_by_shortage(c, chosen)}
    if engine and set(engine) == set(c["shortage_id"]) and feasible(c, caps, engine):
        starts["engine picks"] = engine
    best = None
    for name, s in starts.items():
        s = _improve(c, caps, _repair(c, caps, s))
        val = objective(c, s)
        if best is None or val < best[1] - 1e-9:
            best = (s, val, name)
    return best[0], lb, best[2]


def engine_picks(out: dict, shortage_ids: list) -> dict:
    mo = out["MitigationOption"]
    r = mo[mo["shortage_id"].isin(shortage_ids) & (mo["is_recommended"] == 1)]
    return dict(zip(r["shortage_id"], r["mitigation_id"]))


def resource_usage(c: pd.DataFrame, picks: dict, caps: dict) -> pd.DataFrame:
    s = c[c["mitigation_id"].isin(picks.values())]
    rows = []
    for k, g in s[s["res_key"].notna()].groupby("res_key"):
        rows.append({"resource": _res_text(k), "res_key": k, "used": float(g["res_amt"].sum()), "capacity": float(caps[k]),
                     "shortages": ", ".join(sorted(g["shortage_id"])), "over": float(g["res_amt"].sum()) > caps[k] + 1e-9})
    return pd.DataFrame(rows, columns=["resource", "res_key", "used", "capacity", "shortages", "over"])


def _gaps(out: dict, sid: str) -> tuple[int, int]:
    sh = out["Shortage"].set_index("shortage_id").loc[sid]
    return W.week_of(sh["need_by_date"]), W.week_of(sh["need_by_date"]) + int(sh["episode_weeks"]) - 1


def _pair_gap(out: dict, sku: str, loc: str, st: int, en: int) -> int:
    pb = out["ProjectedBalance"]
    d = pb[(pb["sku_id"] == sku) & (pb["location_id"] == loc)].sort_values("week_start_date").iloc[st - 1:en]
    return int(max(0, (d["safety_stock_qty"] - d["closing_qty"]).max()))


def verify(T: dict, out: dict, policy: dict, picks: dict, shortage_ids: list, seed: int = 0) -> dict:
    """Apply every chosen option together and re-run the planning engine once."""
    T2, descs = T, []
    for sid in shortage_ids:
        m = picks.get(sid)
        if m is None:
            continue
        T2, desc, _ = apply_option(T2, out, m)
        descs.append(desc)
    out2 = run_plan(T2, policy, seed, "recovery", run_id="RUN-0001")[0] if picks else out
    sh = out["Shortage"].set_index("shortage_id")
    sku_t = T["SKU"].set_index("sku_id")
    rate = policy["backorder_cost_pct_per_week"] / 100.0
    mo = out["MitigationOption"].set_index("mitigation_id")
    rows, targets = [], set()
    for sid in shortage_ids:
        s = sh.loc[sid]
        st, en = _gaps(out, sid)
        targets.add((s["sku_id"], s["location_id"]))
        gb = int(s["shortage_qty"])
        ga = _pair_gap(out2, s["sku_id"], s["location_id"], st, en)
        verdict = "RESOLVED" if ga == 0 else ("REDUCED" if ga < gb else ("UNCHANGED" if ga == gb else "WORSE"))
        m = picks.get(sid)
        o = mo.loc[m] if m is not None else None
        action_cost = 0.0 if o is None or o["option_type"] == "PARTIAL_FILL_BACKORDER" else float(o["total_cost"])
        residual = ga * float(sku_t.at[s["sku_id"], "unit_price"]) * rate * int(s["episode_weeks"])
        rows.append({"shortage_id": sid, "sku_id": s["sku_id"], "location_id": s["location_id"], "mitigation_id": m,
                     "option_type": None if o is None else o["option_type"], "gap_before": gb, "gap_after": ga, "verdict": verdict,
                     "action_cost": round(action_cost, 2), "residual_backorder_cost": round(residual, 2)})
    per = pd.DataFrame(rows)
    cmp = compare(out, out2)
    det = cmp["detail"]
    side = det[np.array([(a, b) not in targets for a, b in zip(det["sku_id"], det["location_id"])], dtype=bool)]
    harm = side[side["change"].isin(["NEW", "WORSE"])].reset_index(drop=True)
    f0, f1 = out["DataQualityFinding"], out2["DataQualityFinding"]
    cap0 = set(f0.loc[f0["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED", "record_id"])
    cap_new = sorted(set(f1.loc[f1["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED", "record_id"]) - cap0)
    k = {r.metric: r for r in cmp["kpis"].itertuples()}
    summary = {
        "targets": len(per), "resolved": int((per["verdict"] == "RESOLVED").sum()), "reduced": int((per["verdict"] == "REDUCED").sum()),
        "unchanged": int((per["verdict"] == "UNCHANGED").sum()), "worse": int((per["verdict"] == "WORSE").sum()),
        "gap_before": int(per["gap_before"].sum()), "gap_after": int(per["gap_after"].sum()),
        "action_cost": round(float(per["action_cost"].sum()), 2), "residual_backorder_cost": round(float(per["residual_backorder_cost"].sum()), 2),
        "side_effect_shortages": len(harm), "side_effect_units": int(harm["shortage_qty"].sum()), "new_capacity_exceedances": len(cap_new),
        "service_level_delta": round(float(k["service_level_pct"].delta), 3), "network_shortage_units_delta": int(k["shortage_units"].delta),
        "value_at_risk_delta": round(float(k["value_at_risk"].delta), 2),
    }
    summary["total_cost"] = round(summary["action_cost"] + summary["residual_backorder_cost"], 2)
    return {"per_shortage": per, "summary": summary, "side_effects": harm, "new_capacity_exceedances": cap_new, "actions": descs, "out": out2}


def explain(c: pd.DataFrame, caps: dict, chosen: dict, independent: dict) -> pd.DataFrame:
    """For every candidate of every selected shortage: chosen / rejected and why (objective gap or shared-resource conflict)."""
    used = {}
    for m in chosen.values():
        r = c[c["mitigation_id"] == m].iloc[0]
        if r["res_key"] is not None:
            used[r["res_key"]] = used.get(r["res_key"], 0.0) + r["res_amt"]
    rows = []
    for sid, g in c.groupby("shortage_id", sort=False):
        pick = chosen[sid]
        jp = float(g.loc[g["mitigation_id"] == pick, "J"].iloc[0])
        for r in g.sort_values("J").itertuples():
            if r.mitigation_id == pick:
                if pick == independent.get(sid):
                    why = "lowest total cost (action + uncovered demand) for this shortage, and it fits the shared capacity"
                else:
                    ind = g[g["mitigation_id"] == independent[sid]].iloc[0]
                    others = sorted(set(c[c["mitigation_id"].isin(chosen.values()) & c["res_key"].apply(lambda x: x == ind["res_key"])]["shortage_id"]) - {sid})
                    why = (f"its cheapest option {ind['mitigation_id']} ({ind['option_type']}) needs {ind['res_amt']:,.0f} of {_res_text(ind['res_key'])}, "
                           f"which is limited to {caps.get(ind['res_key'], 0):,.0f} and also used by {', '.join(others) if others else 'other selected shortages'}; "
                           f"this is the best option that keeps the whole plan feasible (+{jp - float(ind['J']):,.2f} objective)")
                rows.append({"shortage_id": sid, "mitigation_id": r.mitigation_id, "option_type": r.option_type, "decision": "SELECTED", "objective": round(float(r.J), 2), "reason": why})
                continue
            k = r.res_key
            pick_k = g.loc[g["mitigation_id"] == pick, "res_key"].iloc[0]
            load = used.get(k, 0.0) - (g.loc[g["mitigation_id"] == pick, "res_amt"].iloc[0] if pick_k == k else 0.0)
            if k is not None and load + r.res_amt > caps[k] + 1e-9:
                why = f"would exceed {_res_text(k)}: needs {r.res_amt:,.0f}, only {max(0.0, caps[k] - load):,.0f} left after the other selected actions"
            else:
                if float(r.J) > jp + 1e-9:
                    why = f"higher total cost than the selected option (+{float(r.J) - jp:,.2f})"
                elif float(r.J) >= jp - 1e-9:
                    why = "same total cost as the selected option; the selected one comes first in the deterministic order"
                else:
                    why = "cheaper on its own but not selected by the search (no single swap to it kept the plan feasible together with the other choices)"
            rows.append({"shortage_id": sid, "mitigation_id": r.mitigation_id, "option_type": r.option_type, "decision": "rejected", "objective": round(float(r.J), 2), "reason": why})
    return pd.DataFrame(rows)


def suggest_conflict_sets(T: dict, out: dict, policy: dict, top: int = 5) -> pd.DataFrame:
    """Groups of shortages whose independent best options over-subscribe the same shared resource (from real data)."""
    c, caps = optimize.build_candidates(T, out, policy)
    ind = c.loc[c.groupby("shortage_id")["J"].idxmin()]
    ind = ind[ind["res_key"].notna()]
    rows = []
    for k, g in ind.groupby("res_key"):
        if g["shortage_id"].nunique() >= 2 and g["res_amt"].sum() > caps[k] + 1e-9:
            rows.append({"resource": _res_text(k), "shortages": sorted(g["shortage_id"].unique()), "demand": float(g["res_amt"].sum()), "capacity": float(caps[k])})
    df = pd.DataFrame(rows, columns=["resource", "shortages", "demand", "capacity"])
    return df.assign(n=df["shortages"].map(len)).sort_values(["n", "demand"], ascending=False).head(top).reset_index(drop=True)


def plan_recovery(T: dict, out: dict, policy: dict, shortage_ids: list, seed: int = 0, compare_plans: bool = True) -> dict:
    shortage_ids = list(dict.fromkeys(shortage_ids))
    c, caps = candidates(T, out, policy, shortage_ids)
    missing = [s for s in shortage_ids if s not in set(c["shortage_id"])]
    if missing:
        raise ValueError(f"no recommendable options for {missing}")
    ind = independent_picks(c)
    eng = engine_picks(out, shortage_ids)
    coord, lb, start = coordinated_picks(c, caps, eng)
    plans = {"Coordinated plan": coord}
    if compare_plans:
        plans = {"Independent best picks": ind, "Engine one-by-one picks": eng, "Coordinated plan": coord}
    results = {name: verify(T, out, policy, p, shortage_ids, seed) for name, p in plans.items()}
    rows = [{"plan": "Current plan (no action)", "targets": len(shortage_ids), "resolved": 0, "reduced": 0, "unchanged": len(shortage_ids), "worse": 0,
             "gap_before": int(out["Shortage"].set_index("shortage_id").loc[shortage_ids, "shortage_qty"].sum()),
             "gap_after": int(out["Shortage"].set_index("shortage_id").loc[shortage_ids, "shortage_qty"].sum()), "action_cost": 0.0,
             "residual_backorder_cost": None, "total_cost": None, "side_effect_shortages": 0, "side_effect_units": 0, "new_capacity_exceedances": 0,
             "service_level_delta": 0.0, "network_shortage_units_delta": 0, "value_at_risk_delta": 0.0, "shared_resource_violations": 0}]
    for name, r in results.items():
        usage = resource_usage(c, plans[name], caps)
        rows.append({"plan": name, **r["summary"], "shared_resource_violations": int(usage["over"].sum()) if len(usage) else 0})
    t = pd.DataFrame(rows)
    nb = results["Coordinated plan"]["per_shortage"]
    bo_rate = policy["backorder_cost_pct_per_week"] / 100.0
    sh = out["Shortage"].set_index("shortage_id")
    price = T["SKU"].set_index("sku_id")["unit_price"]
    base_pen = sum(int(sh.at[s, "shortage_qty"]) * float(price[sh.at[s, "sku_id"]]) * bo_rate * int(sh.at[s, "episode_weeks"]) for s in shortage_ids)
    t.loc[0, "residual_backorder_cost"] = round(base_pen, 2)
    t.loc[0, "total_cost"] = round(base_pen, 2)
    return {"comparison": t, "plans": plans, "results": results, "candidates": c, "caps": caps, "dual_lower_bound": lb, "start": start,
            "objective": {name: round(objective(c, p), 2) for name, p in plans.items()}, "feasible": {name: feasible(c, caps, p) for name, p in plans.items()},
            "explanation": explain(c, caps, coord, ind), "usage": {name: resource_usage(c, p, caps) for name, p in plans.items()},
            "coordinated": nb}
