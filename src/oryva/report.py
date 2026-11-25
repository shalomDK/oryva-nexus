"""Role-based exception & decision report (primary actors: Supplier, Planner, Carrier/warehouse operator,
Logistics analyst, Operations manager).  Reads exported CSVs only."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .pipeline import load_export


def _t(df, n=10):
    return df.head(n).to_markdown(index=False) if hasattr(df, "to_markdown") else df.head(n).to_string(index=False)


def build_report(data_dir: Path) -> str:
    try:
        import tabulate  # noqa: F401
        md = lambda df, n=10: df.head(n).to_markdown(index=False)  # noqa: E731
    except Exception:
        md = lambda df, n=10: "```\n" + df.head(n).to_string(index=False) + "\n```"  # noqa: E731
    T = load_export(Path(data_dir))
    sh, mo, cs, fnd = T["Shortage"], T["MitigationOption"], T["ShortageCause"], T["DataQualityFinding"]
    L = ["# Role-based decision & exception report", "", "Generated from the exported tables only. Each section is what that actor needs to act.", ""]
    rec = mo[mo["is_recommended"] == 1].merge(sh[["shortage_id", "sku_id", "location_id", "priority_rank", "shortage_qty", "first_short_week", "primary_cause_code", "status"]], on="shortage_id", suffixes=("", "_s"))
    L += ["## Planner - top 15 shortages with the recommended mitigation", ""]
    top = rec.sort_values("priority_rank")[["priority_rank", "shortage_id", "sku_id", "location_id", "first_short_week", "shortage_qty", "primary_cause_code", "option_type", "supplier_id", "fill_rate_pct", "total_cost", "cost_delta_vs_baseline", "status"]]
    L += [md(top, 15), "", f"Shortages needing review (missing lead time): **{int((sh['status'] == 'NEEDS_REVIEW').sum())}**", ""]
    L += ["## Supplier - capacity exceedances and constrained supplier-weeks", ""]
    led = T["SupplierCapacityLedger"]
    L += [md(led[led["status"] == "EXCEEDED"][["supplier_id", "product_family", "week_start_date", "committed_qty", "capacity_qty", "utilisation_pct"]], 15), "",
          f"Supplier-weeks at >= 90 % utilisation: **{int((led['utilisation_pct'] >= 90).sum())}** of {len(led)}", ""]
    L += ["## Carrier / warehouse operator - delayed inbound and receipts", ""]
    po, tre = T["PurchaseOrder"], T["TransportEvent"]
    dl = tre[tre["event_type"] == "DELAYED"]
    L += [md(po[po["status"].isin(["DELAYED", "IN_TRANSIT"])][["po_id", "supplier_id", "sku_id", "ship_to_location_id", "carrier_id", "promised_date", "eta_date", "status"]].sort_values("eta_date"), 15), "",
          f"Delayed shipments: **{len(dl)}**; receipts posted: **{int((T['InventoryEvent']['event_type'] == 'RECEIPT').sum())}**", ""]
    L += ["## Logistics analyst - transport delays and lead-time exceptions", ""]
    L += [md(dl.groupby("reason_code")["delay_days"].agg(["count", "mean", "max"]).round(1).reset_index(), 10), "",
          md(fnd[fnd["issue_type"] == "SHORTAGE_MISSING_LEAD_TIME"][["record_id", "related_record_ids", "detail"]], 10), ""]
    L += ["## Operations manager - KPIs and approvals", ""]
    kp = pd.DataFrame({"kpi": ["shortages", "value at risk (USD)", "mean recommended fill rate %", "recommended incremental cost (USD)", "do-nothing backorder cost (USD)"],
                       "value": [len(sh), round(sh["value_at_risk"].sum(), 2), round(rec["fill_rate_pct"].mean(), 2), round(rec["total_cost"].sum(), 2),
                                 round(mo.loc[mo["option_type"] == "PARTIAL_FILL_BACKORDER", "total_cost"].sum(), 2)]})
    L += [md(kp, 10), "", "Recommended options requiring OPS_MANAGER approval (spend above threshold):", "",
          md(rec[rec["approval_required_role"] == "OPS_MANAGER"][["shortage_id", "option_type", "supplier_id", "qty", "total_cost"]], 10), "",
          "### Data-quality exceptions raised by the engine", "", md(fnd["issue_type"].value_counts().rename_axis("issue_type").reset_index(name="count"), 10), ""]
    return "\n".join(L) + "\n"
