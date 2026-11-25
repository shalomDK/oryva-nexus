"""Deterministic KPI calculations shared by the dashboard, scenarios, optimiser and assistant (no hard-coded numbers)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def service_level(pb: pd.DataFrame) -> dict:
    """Unmet demand = demand - max(0, opening + receipts + production)  (per SKU-location-week)."""
    avail = pb["opening_qty"] + pb["scheduled_receipts_qty"] + pb["production_receipts_qty"]
    dem = pb["gross_demand_qty"] + pb["dependent_demand_qty"]
    unmet = np.maximum(0, dem - np.maximum(0, avail))
    d = float(dem.sum())
    return {"demand_units": d, "unmet_units": float(unmet.sum()), "service_level_pct": round(100.0 * (1 - unmet.sum() / d), 3) if d else 100.0,
            "stockout_pair_weeks": int((pb["closing_qty"] < 0).sum())}


def plan_kpis(out: dict) -> dict:
    sh, mo, pb = out["Shortage"], out["MitigationOption"], out["ProjectedBalance"]
    rec = mo[mo["is_recommended"] == 1]
    bo = mo[mo["option_type"] == "PARTIAL_FILL_BACKORDER"]
    k = service_level(pb)
    k.update({
        "shortages": int(len(sh)), "shortage_units": int(sh["shortage_qty"].sum()), "value_at_risk": round(float(sh["value_at_risk"].sum()), 2),
        "stockouts": int((sh["shortage_type"] == "STOCKOUT").sum()), "needs_review": int((sh["status"] == "NEEDS_REVIEW").sum()),
        "recommended_cost": round(float(rec["total_cost"].sum()), 2), "do_nothing_cost": round(float(bo["total_cost"].sum()), 2),
        "mean_fill_rate_pct": round(float(rec["fill_rate_pct"].mean()), 2) if len(rec) else 100.0,
        "pairs": int(pb[["sku_id", "location_id"]].drop_duplicates().shape[0]),
    })
    k["pairs_with_shortage_pct"] = round(100.0 * sh[["sku_id", "location_id"]].drop_duplicates().shape[0] / max(1, k["pairs"]), 2)
    return k
