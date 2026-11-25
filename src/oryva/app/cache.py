"""Cached, read-only accessors for the loaded dataset and derived analytics (keyed by dataset path)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from ..advanced import replenish, risk, supplier_intel
from ..advanced.assistant import Ctx
from ..advanced.data import load_dataset
from .. import weeks as W


@st.cache_resource(show_spinner="Loading dataset...")
def get_ds(path: str) -> dict:
    return load_dataset(path)


@st.cache_resource(show_spinner="Computing supplier intelligence...")
def get_card(path: str) -> pd.DataFrame:
    ds = get_ds(path)
    return supplier_intel.scorecard(ds["T"], ds["out"])


@st.cache_resource(show_spinner="Scoring shortage risk...")
def get_risk(path: str) -> pd.DataFrame:
    ds = get_ds(path)
    return risk.shortage_risk(ds["T"], ds["out"], get_card(path))


@st.cache_resource(show_spinner="Building replenishment proposals...")
def get_proposals(path: str) -> pd.DataFrame:
    ds = get_ds(path)
    return replenish.build_proposals(ds["T"], ds["out"], ds["policy"])


@st.cache_resource(show_spinner="Preparing assistant context...")
def get_ctx(path: str) -> Ctx:
    ds = get_ds(path)
    return Ctx(ds["T"], ds["out"], ds["policy"], get_card(path))


@st.cache_resource(show_spinner="Aggregating demand and inventory...")
def get_stats(path: str) -> dict:
    ds = get_ds(path)
    fd, pb = ds["T"]["ForecastDemand"], ds["out"]["ProjectedBalance"]
    wk = fd.groupby(["sku_id", "location_id"])["forecast_qty"].mean().rename("avg_weekly_demand").reset_index()
    weekly = pb.groupby("week_start_date").agg(demand=("gross_demand_qty", "sum"), dependent=("dependent_demand_qty", "sum"), receipts=("scheduled_receipts_qty", "sum"),
                                              production=("production_receipts_qty", "sum"), closing=("closing_qty", "sum"), short_pairs=("shortfall_qty", lambda x: int((x > 0).sum()))).reset_index()
    avail = pb["opening_qty"] + pb["scheduled_receipts_qty"] + pb["production_receipts_qty"]
    dem = pb["gross_demand_qty"] + pb["dependent_demand_qty"]
    pb2 = pd.DataFrame({"week_start_date": pb["week_start_date"], "unmet": np.maximum(0, dem - np.maximum(0, avail)), "dem": dem})
    sl = pb2.groupby("week_start_date").agg(unmet=("unmet", "sum"), dem=("dem", "sum")).reset_index()
    sl["service_level_pct"] = (100 * (1 - sl["unmet"] / sl["dem"].replace(0, np.nan))).fillna(100).round(2)
    weekly = weekly.merge(sl[["week_start_date", "service_level_pct"]], on="week_start_date")
    weekly["iso_week"] = [W.label(W.week_of(d)) for d in weekly["week_start_date"]]
    fam = ds["T"]["SKU"].set_index("sku_id")["product_family"]
    fdw = fd.assign(family=fd["sku_id"].map(fam)).groupby(["iso_week", "family"])["forecast_qty"].sum().reset_index()
    return {"avg_demand": wk, "weekly": weekly, "demand_family_week": fdw}


@st.cache_resource(show_spinner="Looking for shortages that compete for the same resources...")
def get_conflicts(path: str) -> pd.DataFrame:
    from ..advanced import recovery
    ds = get_ds(path)
    return recovery.suggest_conflict_sets(ds["T"], ds["out"], ds["policy"], top=8)
