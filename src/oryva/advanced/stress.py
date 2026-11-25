"""Supplier failure stress test: which single supplier failure would hurt the plan most, how soon, and are we prepared?

For each screened supplier the failure is simulated on COPIES of the input tables: its not-yet-shipped orders
(PLANNED / CONFIRMED) due within the outage window (or all of them) are cancelled and the supplier is put ON_HOLD so no
mitigation can use it.  Orders already shipped (IN_TRANSIT / DELAYED) still arrive.  The unchanged planning engine is
re-run and compared with the baseline; every reported number comes from that re-plan.

Per supplier: new/worsened shortages, shortage units, value at risk, service-level change, earliest impact week;
orders and units lost; preparedness (new/worsened shortages the engine can fully, partly or not recover with a
recommendable non-backorder option); SKUs whose only approved supplier is the failed one; and the heuristic supplier
disruption-risk rank (risk.supplier_disruption_risk) for comparison.

Screening: suppliers are evaluated in order of unshipped order volume (top_k) because each evaluation is a full
re-plan; suppliers outside the screened set are not evaluated."""
from __future__ import annotations

import pandas as pd

from .. import weeks as W
from ..planning import run_plan
from . import risk, supplier_intel
from .scenario import compare

UNSHIPPED = ("PLANNED", "CONFIRMED")


def exposure(T: dict) -> pd.DataFrame:
    po = T["PurchaseOrder"]
    op = po[po["status"].isin(UNSHIPPED)]
    e = op.groupby("supplier_id").agg(unshipped_orders=("po_id", "size"), unshipped_units=("qty_base", "sum"), skus=("sku_id", "nunique"))
    return e.sort_values(["unshipped_units", "unshipped_orders"], ascending=False)


def _lost_mask(po: pd.DataFrame, supplier_id: str, outage_weeks: int | None) -> pd.Series:
    m = (po["supplier_id"] == supplier_id) & po["status"].isin(UNSHIPPED)
    if outage_weeks is not None:
        m &= pd.Series(W.weeks_of(po["eta_date"]), index=po.index) <= outage_weeks
    return m


def fail_supplier(T: dict, supplier_id: str, outage_weeks: int | None = None) -> tuple[dict, int]:
    """Copy-on-write failure.  Returns (T2, number of orders cancelled); T is never modified."""
    po = T["PurchaseOrder"].copy()
    m = _lost_mask(po, supplier_id, outage_weeks)
    po.loc[m, "status"] = "CANCELLED"
    sup = T["Supplier"].copy()
    sup.loc[sup["supplier_id"] == supplier_id, "status"] = "ON_HOLD"
    return {**T, "PurchaseOrder": po, "Supplier": sup}, int(m.sum())


def single_sourced(T: dict, supplier_id: str) -> list:
    """SKUs whose only APPROVED sourcing record with an ACTIVE supplier is this supplier."""
    ss = T["SKUSupplier"]
    act = set(T["Supplier"].loc[T["Supplier"]["status"] == "ACTIVE", "supplier_id"]) | {supplier_id}
    ap = ss[(ss["approval_status"] == "APPROVED") & ss["supplier_id"].isin(act)]
    n = ap.groupby("sku_id")["supplier_id"].nunique()
    return sorted(s for s in ap.loc[ap["supplier_id"] == supplier_id, "sku_id"] if n.get(s, 0) == 1)


def evaluate_failure(T: dict, out: dict, policy: dict, supplier_id: str, outage_weeks: int | None = None, seed: int = 0) -> dict:
    T2, n_cancel = fail_supplier(T, supplier_id, outage_weeks)
    out2, _ = run_plan(T2, policy, seed, f"stress:{supplier_id}", run_id="RUN-0001")
    cmp = compare(out, out2)
    det = cmp["detail"]
    hit = det[det["change"].isin(["NEW", "WORSE"])]
    k = {r.metric: r for r in cmp["kpis"].itertuples()}
    sh2 = out2["Shortage"]
    keys = sh2["sku_id"] + "|" + sh2["location_id"] + "|" + sh2["first_short_week"]
    ids = list(sh2.loc[keys.isin(set(hit["k"])), "shortage_id"])
    mo = out2["MitigationOption"]
    act = mo[mo["shortage_id"].isin(ids) & (mo["is_recommendable"] == 1) & (mo["option_type"] != "PARTIAL_FILL_BACKORDER")]
    best = act.groupby("shortage_id")["fill_rate_pct"].max().reindex(ids).fillna(0.0)
    sole = single_sourced(T, supplier_id)
    lost = T["PurchaseOrder"][_lost_mask(T["PurchaseOrder"], supplier_id, outage_weeks)]
    first = min((int(x[-2:]) for x in hit["first_short_week"]), default=None)
    return {
        "supplier_id": supplier_id, "orders_cancelled": n_cancel, "units_lost": int(lost["qty_base"].sum()),
        "new_shortages": int((hit["change"] == "NEW").sum()), "worse_shortages": int((hit["change"] == "WORSE").sum()),
        "shortage_units_delta": int(k["shortage_units"].delta), "value_at_risk_delta": round(float(k["value_at_risk"].delta), 2),
        "service_level_delta": round(float(k["service_level_pct"].delta), 3), "first_impact_week": W.label(first) if first else None,
        "fully_recoverable": int((best >= 99.999).sum()), "partly_recoverable": int(((best > 0) & (best < 99.999)).sum()),
        "unrecoverable": int((best <= 0).sum()), "single_sourced_skus": len(sole), "single_sourced_affected": len(set(sole) & set(hit["sku_id"])),
        "affected": hit.drop(columns=["k"]).sort_values(["change", "shortage_qty"], ascending=[True, False]).reset_index(drop=True),
        "single_sourced_list": sole, "out": out2,
    }


def stress_test(T: dict, out: dict, policy: dict, top_k: int = 10, outage_weeks: int | None = None, seed: int = 0) -> dict:
    ex = exposure(T)
    screened = list(ex.index[:top_k])
    card = supplier_intel.scorecard(T, out).set_index("supplier_id")
    dr = risk.supplier_disruption_risk(T, card.reset_index()).reset_index(drop=True)
    dr["heuristic_risk_rank"] = range(1, len(dr) + 1)
    dr = dr.set_index("supplier_id")
    results = {s: evaluate_failure(T, out, policy, s, outage_weeks, seed) for s in screened}
    rows = [{**{k: v for k, v in r.items() if k not in ("affected", "single_sourced_list", "out")},
             "supplier_score": float(card.at[s, "score"]), "heuristic_risk_rank": int(dr.at[s, "heuristic_risk_rank"]), "heuristic_band": dr.at[s, "band"]}
            for s, r in results.items()]
    t = pd.DataFrame(rows)
    if t.empty:
        return {"table": t, "results": results, "screened": screened, "total_suppliers": len(T["Supplier"]), "rank_correlation": None,
                "blind_spots": t, "outage_weeks": outage_weeks}
    t = t.sort_values(["shortage_units_delta", "value_at_risk_delta", "supplier_id"], ascending=[False, False, True]).reset_index(drop=True)
    t.insert(0, "impact_rank", range(1, len(t) + 1))
    # Spearman rank correlation = Pearson correlation of the ranks (computed without scipy)
    corr = round(float(t["impact_rank"].rank().corr(t["heuristic_risk_rank"].rank())), 3) if len(t) >= 3 else None
    blind = t.head(max(1, len(t) // 3))
    blind = blind[blind["heuristic_band"] != "HIGH"].reset_index(drop=True)
    return {"table": t, "results": results, "screened": screened, "total_suppliers": len(T["Supplier"]), "rank_correlation": corr,
            "blind_spots": blind, "outage_weeks": outage_weeks}


class _Ctx:
    def __init__(self, T, out):
        self.T, self.out, self.as_of = T, out, str(T["Inventory"]["as_of_date"].iloc[0])


def hedge_candidates(T: dict, out: dict, supplier_id: str, skus: list, limit: int = 3) -> pd.DataFrame:
    """Other ACTIVE suppliers that already supply each SKU's product family, with remaining capacity this week -
    candidates to QUALIFY as a second source (not approved for that SKU today)."""
    from .assistant import _capacity_now
    fam = T["SKU"].set_index("sku_id")["product_family"]
    sup = T["Supplier"].set_index("supplier_id")
    cap = T["SupplierCapacity"]
    rows = []
    for s in skus:
        f = fam[s]
        others = sorted(o for o in set(cap.loc[(cap["product_family"] == f) & (cap["status"] == "ACTIVE"), "supplier_id"]) - {supplier_id}
                        if sup.at[o, "status"] == "ACTIVE")
        if not others:
            rows.append({"sku_id": s, "product_family": f, "candidate_supplier": None, "remaining_capacity_this_week": None})
            continue
        cn = _capacity_now(_Ctx(T, out), others)
        cn = cn[cn["product_family"] == f].sort_values(["remaining_now", "supplier_id"], ascending=[False, True]).head(limit)
        rows += [{"sku_id": s, "product_family": f, "candidate_supplier": r.supplier_id, "remaining_capacity_this_week": int(r.remaining_now)} for r in cn.itertuples()]
    return pd.DataFrame(rows, columns=["sku_id", "product_family", "candidate_supplier", "remaining_capacity_this_week"])
