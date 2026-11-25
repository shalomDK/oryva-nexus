"""Risk prediction: explainable early-warning scores for SKU-location shortages and supplier disruptions.

Shortage risk (0-100) = 100 * sum_i w_i * f_i, each f_i in [0,1] computed ONLY from baseline plan + master data
(no ground truth, no scenario knowledge) over the next `horizon` weeks:
  buffer (0.30)             1 - (min projected surplus over safety stock / avg weekly demand) / 4 weeks
  volatility (0.10)         forecast_stdev / forecast mean, scaled by 0.6
  inbound_dependency (0.15) share of horizon demand that must be met by receipts, not on-hand
  supplier_risk (0.15)      quantity-weighted (100 - supplier score)/100 of inbound orders in the horizon
  delay_exposure (0.10)     share of inbound quantity on orders already delayed/slipped
  capacity_pressure (0.10)  peak utilisation of the supplier-weeks the inbound orders sit in (60 % -> 0, 100 % -> 1)
  spike_exposure (0.10)     (max weekly forecast / median - 1) / 2, clipped
Every row carries the per-factor contribution so each score is explainable.  Validation: `stress_backtest` re-runs the
planning engine under a stress scenario and measures how well the score ranked the pairs that actually became short.
Supplier disruption risk = 100 - scorecard score + status/single-source/open-delay adjustments, with contributions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import weeks as W
from .scenario import Scenario, simulate

WEIGHTS = {"buffer": 0.30, "volatility": 0.10, "inbound_dependency": 0.15, "supplier_risk": 0.15, "delay_exposure": 0.10,
           "capacity_pressure": 0.10, "spike_exposure": 0.10}
BANDS = [(60, "HIGH"), (35, "MEDIUM"), (0, "LOW")]


def band(x: float) -> str:
    return next(b for t, b in BANDS if x >= t)


def shortage_risk(T: dict, out: dict, card: pd.DataFrame, horizon: int = 8) -> pd.DataFrame:
    pb = out["ProjectedBalance"].copy()
    pb["w"] = W.weeks_of(pb["week_start_date"])
    pb = pb[pb["w"] <= horizon].sort_values(["sku_id", "location_id", "w"])
    g = pb.groupby(["sku_id", "location_id"])
    dem = g.apply(lambda d: (d["gross_demand_qty"] + d["dependent_demand_qty"]).sum(), include_groups=False)
    mean_w = (dem / horizon).clip(lower=0.5)
    surplus = g.apply(lambda d: (d["closing_qty"] - d["safety_stock_qty"]).min(), include_groups=False)
    rec = g["scheduled_receipts_qty"].sum() + g["production_receipts_qty"].sum()
    f = pd.DataFrame({"buffer": np.clip(1 - (surplus / mean_w) / 4.0, 0, 1), "inbound_dependency": np.clip(rec / (dem + 1), 0, 1)})
    fd = T["ForecastDemand"].copy()
    fd["w"] = W.weeks_of(fd["week_start_date"])
    fh = fd[fd["w"] <= horizon].groupby(["sku_id", "location_id"])
    cv = (fh["forecast_stdev"].mean() / fh["forecast_qty"].mean().clip(lower=0.5))
    f["volatility"] = np.clip(cv / 0.6, 0, 1)
    full = fd.groupby(["sku_id", "location_id"])["forecast_qty"]
    f["spike_exposure"] = np.clip((full.max() / full.median().clip(lower=1) - 1) / 2.0, 0, 1)
    # inbound order based factors
    po = T["PurchaseOrder"]
    po = po[po["status"].isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"])].copy()
    po["w"] = W.weeks_of(po["eta_date"])
    po = po[(po["w"] >= 1) & (po["w"] <= horizon)]
    sc = card.set_index("supplier_id")["score"]
    po["risk"] = (100 - po["supplier_id"].map(sc).fillna(100)) / 100
    po["delayed"] = ((po["status"] == "DELAYED") | (po["eta_date"] > po["promised_date"])).astype(float)
    po["ws"] = (pd.to_datetime(po["order_date"]) - pd.to_timedelta(pd.to_datetime(po["order_date"]).dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    fam = T["SKU"].set_index("sku_id")["product_family"]
    po["fam"] = po["sku_id"].map(fam)
    led = out["SupplierCapacityLedger"].set_index(["supplier_id", "product_family", "week_start_date"])["utilisation_pct"]
    po["util"] = [led.get((a, b, c), 0.0) for a, b, c in zip(po["supplier_id"], po["fam"], po["ws"])]
    po["util_f"] = np.clip((po["util"] - 60) / 40.0, 0, 1)
    pg = po.groupby(["sku_id", "ship_to_location_id"])
    qsum = pg["qty_base"].sum()
    f["supplier_risk"] = (pg.apply(lambda d: (d["risk"] * d["qty_base"]).sum(), include_groups=False) / qsum)
    f["delay_exposure"] = (pg.apply(lambda d: (d["delayed"] * d["qty_base"]).sum(), include_groups=False) / qsum)
    f["capacity_pressure"] = pg["util_f"].max()
    f.index.names = ["sku_id", "location_id"]
    f = f.reindex(g.size().index).fillna(0.0)
    contrib = pd.DataFrame({f"c_{k}": (100 * w * f[k]).round(2) for k, w in WEIGHTS.items() if k in f})
    res = pd.concat([f.round(3).add_prefix("f_"), contrib], axis=1)
    res["risk_score"] = contrib.sum(axis=1).round(2)
    res["band"] = res["risk_score"].map(band)
    sh = out["Shortage"].copy()
    sh["w"] = [int(x[-2:]) for x in sh["first_short_week"]]
    already = set(zip(sh.loc[sh["w"] <= horizon, "sku_id"], sh.loc[sh["w"] <= horizon, "location_id"]))
    res["already_short"] = [k in already for k in res.index]
    top = contrib.apply(lambda r: ", ".join(f"{c[2:]} {v:.0f}" for c, v in r.sort_values(ascending=False).head(3).items() if v > 0), axis=1)
    res["top_factors"] = top
    return res.reset_index().sort_values("risk_score", ascending=False, kind="mergesort").reset_index(drop=True)


def supplier_disruption_risk(T: dict, card: pd.DataFrame) -> pd.DataFrame:
    po = T["PurchaseOrder"]
    open_po = po[po["status"].isin(["IN_TRANSIT", "DELAYED", "CONFIRMED", "PLANNED"])]
    ss = T["SKUSupplier"]
    approved = ss[ss["approval_status"] == "APPROVED"]
    n_sup = approved.groupby("sku_id")["supplier_id"].nunique()
    single = approved[approved["sku_id"].map(n_sup) == 1].groupby("supplier_id").size()
    nsku = approved.groupby("supplier_id").size()
    delayed_open = open_po[(open_po["status"] == "DELAYED")].groupby("supplier_id").size()
    c = card.set_index("supplier_id")
    r = pd.DataFrame({"base": 100 - c["score"]})
    r["status_adj"] = np.where(c["supplier_status"] != "ACTIVE", 25.0, 0.0)
    r["single_source_adj"] = (15 * (single.reindex(c.index).fillna(0) / nsku.reindex(c.index).replace(0, np.nan)).fillna(0)).round(2)
    r["open_delay_adj"] = np.minimum(15.0, 3.0 * delayed_open.reindex(c.index).fillna(0))
    r["disruption_risk"] = np.minimum(100, r.sum(axis=1)).round(2)
    r["band"] = r["disruption_risk"].map(lambda x: "HIGH" if x >= 40 else ("MEDIUM" if x >= 25 else "LOW"))
    r = r.join(c[["supplier_name", "region", "supplier_status", "score", "tier"]])
    return r.reset_index().sort_values("disruption_risk", ascending=False, kind="mergesort").reset_index(drop=True)


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    s = pd.Series(scores)
    ranks = s.rank(method="average").to_numpy()
    n1, n0 = int(labels.sum()), int((1 - labels).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[labels == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def stress_backtest(T: dict, out: dict, risk: pd.DataFrame, policy: dict, horizon: int = 8, demand_mult: float = 1.15, delay_days: int = 7) -> dict:
    """Does the risk score rank the pairs that become short under a stress scenario (never used to compute the score)?"""
    sc = Scenario(name="risk-backtest", demand_multiplier=demand_mult, week_from=1, week_to=horizon, transport_delay_days=delay_days, transport_scope="all_open")
    res = simulate(T, out, sc, policy)
    s2 = res["out"]["Shortage"]
    s2 = s2[[int(x[-2:]) <= horizon for x in s2["first_short_week"]]]
    new_short = set(zip(s2["sku_id"], s2["location_id"]))
    pool = risk[~risk["already_short"]].copy()
    pool["y"] = [int((a, b) in new_short) for a, b in zip(pool["sku_id"], pool["location_id"])]
    a = auc(pool["risk_score"].to_numpy(), pool["y"].to_numpy())
    k = max(1, int(0.1 * len(pool)))
    topk = pool.head(k)
    base_rate = pool["y"].mean() if len(pool) else float("nan")
    return {"scenario": sc.describe(), "pairs_scored": len(pool), "newly_short_under_stress": int(pool["y"].sum()), "base_rate": round(float(base_rate), 4),
            "auc": round(a, 4) if a == a else None, "precision_at_top10pct": round(float(topk["y"].mean()), 4) if len(topk) else None,
            "lift_at_top10pct": round(float(topk["y"].mean() / base_rate), 2) if base_rate and base_rate == base_rate and len(topk) else None}
