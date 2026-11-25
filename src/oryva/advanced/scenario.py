"""What-if scenario simulator.

A scenario is a parameter overlay applied to COPIES of the input tables; the same planning engine is re-run and
compared with the baseline.  The baseline dataset (in memory and on disk) is never modified."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import weeks as W
from ..planning import run_plan
from .kpi import plan_kpis


@dataclass
class Scenario:
    name: str = "Scenario"
    demand_multiplier: float = 1.0
    demand_family: str | None = None          # product family filter (None = all)
    demand_location: str | None = None        # location filter
    week_from: int = 1
    week_to: int = 52
    lead_time_delta_days: int = 0             # added to lead time of not-yet-shipped orders and to LeadTime rows
    lead_time_supplier: str | None = None
    capacity_factor: float = 1.0              # multiplies supplier weekly capacity
    capacity_supplier: str | None = None
    transport_delay_days: int = 0             # added to ETA of orders already shipped (IN_TRANSIT / DELAYED)
    transport_supplier: str | None = None
    transport_scope: str = "shipped"          # "shipped" or "all_open"
    disabled_suppliers: list = field(default_factory=list)

    def is_noop(self) -> bool:
        return (self.demand_multiplier == 1.0 and self.lead_time_delta_days == 0 and self.capacity_factor == 1.0
                and self.transport_delay_days == 0 and not self.disabled_suppliers)

    def describe(self) -> list[str]:
        d = []
        if self.demand_multiplier != 1.0:
            d.append(f"demand x{self.demand_multiplier:g} (family={self.demand_family or 'all'}, location={self.demand_location or 'all'}, weeks {self.week_from}-{self.week_to})")
        if self.lead_time_delta_days:
            d.append(f"lead time {self.lead_time_delta_days:+d} d (supplier={self.lead_time_supplier or 'all'})")
        if self.capacity_factor != 1.0:
            d.append(f"supplier capacity x{self.capacity_factor:g} (supplier={self.capacity_supplier or 'all'})")
        if self.transport_delay_days:
            d.append(f"transport delay {self.transport_delay_days:+d} d on {self.transport_scope} orders (supplier={self.transport_supplier or 'all'})")
        if self.disabled_suppliers:
            d.append("suppliers disabled: " + ", ".join(self.disabled_suppliers))
        return d or ["no change"]


def _shift(col: pd.Series, days: int) -> pd.Series:
    return (pd.to_datetime(col) + pd.to_timedelta(days, unit="D")).dt.strftime("%Y-%m-%d")


def apply_scenario(T: dict, sc: Scenario) -> dict:
    """Return a NEW dict of tables; only changed tables are copied, the input frames are never mutated."""
    T2 = dict(T)
    if sc.demand_multiplier != 1.0:
        fd = T["ForecastDemand"].copy()
        m = pd.Series(True, index=fd.index)
        if sc.demand_family:
            fam = T["SKU"].set_index("sku_id")["product_family"]
            m &= fd["sku_id"].map(fam) == sc.demand_family
        if sc.demand_location:
            m &= fd["location_id"] == sc.demand_location
        w = W.weeks_of(fd["week_start_date"])
        m &= (w >= sc.week_from) & (w <= sc.week_to)
        fd.loc[m, "forecast_qty"] = np.ceil(fd.loc[m, "forecast_qty"] * sc.demand_multiplier - 1e-9).astype("int64")
        T2["ForecastDemand"] = fd
    po = None
    if sc.lead_time_delta_days:
        lt = T["LeadTime"].copy()
        sm = (lt["supplier_id"] == sc.lead_time_supplier) if sc.lead_time_supplier else pd.Series(True, index=lt.index)
        d = sc.lead_time_delta_days
        lt.loc[sm, "transit_days"] = np.maximum(0, lt.loc[sm, "transit_days"] + d)
        lt["total_lead_days"] = lt["production_days"] + lt["transit_days"]
        lt.loc[sm, "p90_lead_days"] = np.maximum(lt.loc[sm, "total_lead_days"], lt.loc[sm, "p90_lead_days"] + d)
        T2["LeadTime"] = lt
        po = T["PurchaseOrder"].copy()
        pm = po["status"].isin(["PLANNED", "CONFIRMED"]) & ((po["supplier_id"] == sc.lead_time_supplier) if sc.lead_time_supplier else True)
        for c in ("promised_date", "eta_date"):
            po.loc[pm, c] = _shift(po.loc[pm, c], d)
    if sc.transport_delay_days:
        po = T["PurchaseOrder"].copy() if po is None else po
        st = ["IN_TRANSIT", "DELAYED"] if sc.transport_scope == "shipped" else ["IN_TRANSIT", "DELAYED", "CONFIRMED", "PLANNED"]
        pm = po["status"].isin(st) & ((po["supplier_id"] == sc.transport_supplier) if sc.transport_supplier else True)
        po.loc[pm, "eta_date"] = _shift(po.loc[pm, "eta_date"], sc.transport_delay_days)
        po.loc[pm & po["status"].isin(["IN_TRANSIT"]), "status"] = "DELAYED"
    if sc.capacity_factor != 1.0:
        cap = T["SupplierCapacity"].copy()
        sm = (cap["supplier_id"] == sc.capacity_supplier) if sc.capacity_supplier else pd.Series(True, index=cap.index)
        cap.loc[sm, "weekly_capacity_qty"] = np.maximum(1, np.floor(cap.loc[sm, "weekly_capacity_qty"] * sc.capacity_factor)).astype("int64")
        T2["SupplierCapacity"] = cap
    if sc.disabled_suppliers:
        po = T["PurchaseOrder"].copy() if po is None else po
        pm = po["supplier_id"].isin(sc.disabled_suppliers) & po["status"].isin(["PLANNED", "CONFIRMED"])
        po.loc[pm, "status"] = "CANCELLED"
        sup = T["Supplier"].copy()
        sup.loc[sup["supplier_id"].isin(sc.disabled_suppliers), "status"] = "ON_HOLD"
        T2["Supplier"] = sup
    if po is not None:
        T2["PurchaseOrder"] = po
    return T2


def _key(sh: pd.DataFrame) -> pd.Series:
    return sh["sku_id"] + "|" + sh["location_id"] + "|" + sh["first_short_week"]


def compare(base_out: dict, scn_out: dict) -> dict:
    kb, ks = plan_kpis(base_out), plan_kpis(scn_out)
    sb, ss = base_out["Shortage"].assign(k=_key(base_out["Shortage"])), scn_out["Shortage"].assign(k=_key(scn_out["Shortage"]))
    bq, sq = sb.set_index("k")["shortage_qty"], ss.set_index("k")["shortage_qty"]
    new = sorted(set(sq.index) - set(bq.index))
    resolved = sorted(set(bq.index) - set(sq.index))
    common = bq.index.intersection(sq.index)
    worse = [k for k in common if sq[k] > bq[k]]
    better = [k for k in common if sq[k] < bq[k]]
    rows = []
    for name in ("shortages", "shortage_units", "stockouts", "value_at_risk", "service_level_pct", "unmet_units", "mean_fill_rate_pct",
                 "recommended_cost", "do_nothing_cost", "pairs_with_shortage_pct"):
        rows.append({"metric": name, "baseline": kb[name], "scenario": ks[name], "delta": round(ks[name] - kb[name], 3)})
    detail = pd.concat([
        ss[ss["k"].isin(new)].assign(change="NEW")[["k", "sku_id", "location_id", "first_short_week", "shortage_qty", "primary_cause_code", "change"]],
        sb[sb["k"].isin(resolved)].assign(change="RESOLVED")[["k", "sku_id", "location_id", "first_short_week", "shortage_qty", "primary_cause_code", "change"]],
        ss[ss["k"].isin(worse)].assign(change="WORSE")[["k", "sku_id", "location_id", "first_short_week", "shortage_qty", "primary_cause_code", "change"]],
        ss[ss["k"].isin(better)].assign(change="BETTER")[["k", "sku_id", "location_id", "first_short_week", "shortage_qty", "primary_cause_code", "change"]],
    ], ignore_index=True)
    return {"kpis": pd.DataFrame(rows), "baseline": kb, "scenario": ks, "detail": detail,
            "counts": {"new": len(new), "resolved": len(resolved), "worse": len(worse), "better": len(better), "unchanged": len(common) - len(worse) - len(better)}}


def simulate(T: dict, base_out: dict, sc: Scenario, policy: dict, seed: int = 0) -> dict:
    """Recalculate under the scenario and compare with the baseline plan.  Inputs are never mutated."""
    T2 = apply_scenario(T, sc)
    out2, _ = run_plan(T2, policy, seed, f"scenario:{sc.name}", run_id="RUN-0001")
    res = compare(base_out, out2)
    res.update({"params": asdict(sc), "out": out2, "description": sc.describe()})
    return res

