"""Data-quality gate: detectors shared by the planning engine (Stage 0) and the validator.

These implement the engine side of the five mandatory edge cases.  They read ONLY input tables
(never ground truth).  Record keys are canonical so findings can be scored against ground truth.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def cap_key(sup, fam, ws) -> str:
    return f"{sup}|{fam}|{ws}"


def lt_key(sup, sku) -> str:
    return f"{sup}|{sku}"


def sub_key(sku, alt, eff_from) -> str:
    return f"{sku}>{alt}@{eff_from}"


def po_effective(T: dict) -> pd.DataFrame:
    """Per-PO effective base quantity after UoM normalisation + duplicate detection."""
    po = T["PurchaseOrder"].sort_values("po_id").reset_index(drop=True)
    sku = T["SKU"][["sku_id", "base_uom", "product_family"]]
    conv = T["UoMConversion"][["sku_id", "from_uom", "factor"]]
    m = po.merge(sku, on="sku_id", how="left").merge(
        conv, left_on=["sku_id", "order_uom"], right_on=["sku_id", "from_uom"], how="left")
    factor = np.where(m["order_uom"] == m["base_uom"], 1.0, m["factor"].astype(float))
    expected = m["order_qty"].astype(float) * factor
    missing = np.isnan(factor)
    mismatch = (~missing) & (np.abs(m["qty_base"].astype(float) - expected) > 1e-6)
    out = pd.DataFrame({
        "po_id": m["po_id"], "supplier_id": m["supplier_id"], "sku_id": m["sku_id"],
        "ship_to_location_id": m["ship_to_location_id"], "product_family": m["product_family"],
        "status": m["status"], "order_date": m["order_date"], "requested_date": m["requested_date"],
        "promised_date": m["promised_date"], "eta_date": m["eta_date"], "supplier_ref_no": m["supplier_ref_no"],
        "qty_recorded": m["qty_base"].astype("int64"),
        "qty_eff": np.where(missing, 0, np.rint(expected)).astype("int64"),
        "uom_mismatch": mismatch, "factor_missing": missing})
    key = ["supplier_id", "sku_id", "ship_to_location_id", "promised_date", "supplier_ref_no"]
    out["is_duplicate"] = out.duplicated(key, keep="first")
    first = out[~out["is_duplicate"]].set_index(key)["po_id"]
    dkeys = out[out["is_duplicate"]][key]
    out["duplicate_of"] = None
    if len(dkeys):
        out.loc[out["is_duplicate"], "duplicate_of"] = pd.MultiIndex.from_frame(dkeys).map(first.to_dict().get).values
    # variant B: an open PO re-lists an order that was already RECEIVED (its quantity is already in on-hand)
    k4 = ["supplier_id", "sku_id", "ship_to_location_id", "supplier_ref_no"]
    rec = out[out["status"] == "RECEIVED"].drop_duplicates(k4).set_index(k4)["po_id"].to_dict()
    openm = out["status"].isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"]) & ~out["is_duplicate"]
    if rec and openm.any():
        orig = pd.Series(pd.MultiIndex.from_frame(out.loc[openm, k4]).map(rec.get), index=out.index[openm])
        hit = orig.notna()
        out.loc[hit.index[hit], "is_duplicate"] = True
        out.loc[hit.index[hit], "duplicate_of"] = orig[hit].values
    return out


def week_start_str(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates)
    return (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")


def capacity_for(cap: pd.DataFrame, keys: pd.DataFrame) -> pd.Series:
    """Capacity effective at `week_start_date` per (supplier_id, product_family); the row with the latest
    effective_from wins when windows overlap (supersession rule)."""
    k = keys.reset_index(drop=True).copy()
    k["_i"] = np.arange(len(k))
    m = k.merge(cap[cap["status"] == "ACTIVE"], on=["supplier_id", "product_family"], how="left")
    ok = (m["effective_from"] <= m["week_start_date"]) & (m["effective_to"].isna() | (m["week_start_date"] < m["effective_to"]))
    m = m[ok].sort_values(["_i", "effective_from"])
    last = m.groupby("_i").tail(1).set_index("_i")["weekly_capacity_qty"]
    return pd.Series(k["_i"].map(last).values, index=range(len(k)))


def ledger(T: dict, pe: pd.DataFrame) -> pd.DataFrame:
    use = pe[(pe["status"] != "CANCELLED") & (~pe["is_duplicate"]) & (~pe["factor_missing"])].copy()
    use["week_start_date"] = week_start_str(use["order_date"])
    g = use.groupby(["supplier_id", "product_family", "week_start_date"], as_index=False)["qty_eff"].sum()
    g = g.rename(columns={"qty_eff": "committed_qty"})
    g["capacity_qty"] = capacity_for(T["SupplierCapacity"], g[["supplier_id", "product_family", "week_start_date"]]).fillna(0).astype("int64").values
    g["utilisation_pct"] = np.where(g["capacity_qty"] > 0, 100.0 * g["committed_qty"] / g["capacity_qty"].replace(0, 1), 999.0)
    g["remaining_qty"] = np.maximum(0, g["capacity_qty"] - g["committed_qty"]).astype("int64")
    g["status"] = np.where(g["committed_qty"] > g["capacity_qty"], "EXCEEDED", "OK")
    return g.sort_values(["supplier_id", "product_family", "week_start_date"]).reset_index(drop=True)


def missing_lead_times(T: dict) -> pd.DataFrame:
    ss = T["SKUSupplier"][["supplier_id", "sku_id"]]
    lt = T["LeadTime"][["supplier_id", "sku_id"]].drop_duplicates()
    m = ss.merge(lt, on=["supplier_id", "sku_id"], how="left", indicator=True)
    return m[m["_merge"] == "left_only"][["supplier_id", "sku_id"]].reset_index(drop=True)


def unapproved_substitutes(T: dict, as_of: str) -> pd.DataFrame:
    s = T["SKUSubstitute"]
    bad = (s["approval_status"] != "APPROVED") | (s["effective_from"] > as_of) | (s["effective_to"].notna() & (s["effective_to"] <= as_of))
    return s[bad].reset_index(drop=True)
