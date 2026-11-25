"""Evaluation: the ONLY module that reads ground truth.  Scores engine findings + validator results against
labels (precision / recall per issue type), checks the expected decisions, and computes planning KPIs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import ISSUES


def _sets(gt):
    a = gt[gt["label_class"] == "ANOMALY"]
    b = gt[gt["label_class"] == "BOUNDARY"]
    return a, b


def evaluate(T: dict, gt: pd.DataFrame, report) -> dict:
    a, b = _sets(gt)
    fnd = T["DataQualityFinding"]
    res = {"detection": [], "validator_reconciliation": [], "decisions": []}
    lab = pd.DataFrame(report.labelled) if report.labelled else pd.DataFrame(columns=["issue_type", "record_id"])
    for it in ISSUES:
        exp = set(a.loc[a["issue_type"] == it, "record_id"])
        bnd = set(b.loc[b["issue_type"] == it, "record_id"])
        got = set(fnd.loc[fnd["issue_type"] == it, "record_id"])
        tp, fp, fn = len(exp & got), len(got - exp), len(exp - got)
        res["detection"].append({"issue_type": it, "labelled": len(exp), "boundary_cases": len(bnd), "engine_flagged": len(got),
                                 "true_positive": tp, "false_positive": fp, "false_negative": fn,
                                 "boundary_wrongly_flagged": len(bnd & got),
                                 "precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
                                 "recall": round(tp / (tp + fn), 4) if tp + fn else 1.0})
        vg = set(lab.loc[lab["issue_type"] == it, "record_id"])
        res["validator_reconciliation"].append({"issue_type": it, "labelled": len(exp), "validator_flagged": len(vg),
                                                "exact_match": bool(vg == exp), "missing": len(exp - vg), "unexpected": len(vg - exp)})
    # expected decisions
    sh, mo = T["Shortage"], T["MitigationOption"]
    lt = a[a["issue_type"] == "SHORTAGE_MISSING_LEAD_TIME"]
    ok = True
    for sku in set(lt["related_record_ids"]):
        s = sh[sh["sku_id"] == sku]
        ids_ = set(s["shortage_id"])
        supp = mo[mo["shortage_id"].isin(ids_) & mo["option_type"].isin(["NEW_PO", "ALT_SUPPLIER_PO"])]
        ok &= bool((s["status"] == "NEEDS_REVIEW").all() and (supp["is_recommendable"] == 0).all() and (supp["lead_time_check"] == "MISSING").all())
    res["decisions"].append({"issue_type": "SHORTAGE_MISSING_LEAD_TIME", "decision": "FLAG_AND_BLOCK_MITIGATION", "all_as_expected": bool(ok), "cases": len(set(lt["related_record_ids"]))})
    sb = a[a["issue_type"] == "SUBSTITUTE_NOT_APPROVED"]
    ok, n = True, 0
    for rid, sku in zip(sb["record_id"], sb["related_record_ids"]):
        alt = rid.split(">")[1].split("@")[0]
        o = mo[mo["shortage_id"].isin(set(sh.loc[sh["sku_id"] == sku, "shortage_id"])) & (mo["alt_sku_id"] == alt)]
        n += 1
        ok &= bool(len(o) > 0 and (o["is_recommendable"] == 0).all() and o["policy_reason"].str.contains("SUBSTITUTE").all())
    res["decisions"].append({"issue_type": "SUBSTITUTE_NOT_APPROVED", "decision": "REJECT_OPTION_NEVER_RECOMMEND", "all_as_expected": bool(ok), "cases": n})
    dp = a[a["issue_type"] == "INBOUND_DOUBLE_COUNT"]
    res["decisions"].append({"issue_type": "INBOUND_DOUBLE_COUNT", "decision": "EXCLUDE_DUPLICATE",
                             "all_as_expected": bool(set(dp["record_id"]) <= set(fnd.loc[fnd["issue_type"] == "INBOUND_DOUBLE_COUNT", "record_id"])), "cases": len(dp)})
    um = a[a["issue_type"] == "UOM_MISMATCH"]
    res["decisions"].append({"issue_type": "UOM_MISMATCH", "decision": "USE_CONVERTED_QUANTITY",
                             "all_as_expected": bool(set(um["record_id"]) <= set(fnd.loc[fnd["issue_type"] == "UOM_MISMATCH", "record_id"])), "cases": len(um)})
    cp = a[a["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED"]
    led = T["SupplierCapacityLedger"]
    flagged = set(f"{x}|{y}|{z}" for x, y, z in zip(led.loc[led["status"] == "EXCEEDED", "supplier_id"], led.loc[led["status"] == "EXCEEDED", "product_family"], led.loc[led["status"] == "EXCEEDED", "week_start_date"]))
    res["decisions"].append({"issue_type": "SUPPLIER_CAPACITY_EXCEEDED", "decision": "FLAG_AND_LIMIT_MITIGATION_CAPACITY",
                             "all_as_expected": bool(set(cp["record_id"]) <= flagged), "cases": len(cp)})
    # KPIs
    cs = T["ShortageCause"]
    rec = mo[mo["is_recommended"] == 1]
    n_opt = mo.groupby("shortage_id").size()
    k = {
        "shortages": int(len(sh)), "by_type": sh["shortage_type"].value_counts().to_dict(), "by_status": sh["status"].value_counts().to_dict(),
        "by_primary_cause": sh["primary_cause_code"].value_counts().to_dict(),
        "pct_shortages_with_cause": 100.0 if len(sh) == 0 else round(100.0 * sh["shortage_id"].isin(cs["shortage_id"]).mean(), 2),
        "pct_shortages_with_2plus_options": 100.0 if len(sh) == 0 else round(100.0 * (n_opt.reindex(sh["shortage_id"]).fillna(0) >= 2).mean(), 2),
        "value_at_risk_usd": round(float(sh["value_at_risk"].sum()), 2),
        "mean_recommended_fill_rate_pct": round(float(rec["fill_rate_pct"].mean()), 2) if len(rec) else None,
        "recommended_incremental_cost_usd": round(float(rec["total_cost"].sum()), 2),
        "do_nothing_backorder_cost_usd": round(float(mo.loc[mo["option_type"] == "PARTIAL_FILL_BACKORDER", "total_cost"].sum()), 2),
        "recommended_option_mix": rec["option_type"].value_counts().to_dict(),
        "data_quality_findings": T["DataQualityFinding"]["issue_type"].value_counts().to_dict(),
    }
    res["kpis"] = k
    res["all_detection_perfect"] = bool(all(d["precision"] == 1.0 and d["recall"] == 1.0 and d["boundary_wrongly_flagged"] == 0 for d in res["detection"]))
    res["all_validator_reconciled"] = bool(all(v["exact_match"] for v in res["validator_reconciliation"]))
    res["all_decisions_ok"] = bool(all(d["all_as_expected"] for d in res["decisions"]))
    return res


def distribution_report(T: dict) -> dict:
    fd, lt, po, inv = T["ForecastDemand"], T["LeadTime"], T["PurchaseOrder"], T["Inventory"]
    wk = fd.groupby(["sku_id", "location_id"])["forecast_qty"].mean()
    q = lambda s: {k: round(float(v), 2) for k, v in s.quantile([0.1, 0.5, 0.9, 0.99]).to_dict().items()}  # noqa: E731
    top = wk.groupby(level=0).sum().sort_values(ascending=False)
    share20 = float(top.iloc[: max(1, len(top) // 5)].sum() / top.sum()) if top.sum() else 0.0
    return {"weekly_demand_per_pair": q(wk), "top_20pct_skus_demand_share": round(share20, 3),
            "zero_demand_weeks_pct": round(float((fd["forecast_qty"] == 0).mean() * 100), 2),
            "demand_driver_mix_pct": (fd["demand_driver"].value_counts(normalize=True) * 100).round(2).to_dict(),
            "lead_time_days": q(lt["total_lead_days"]), "po_status_mix": po["status"].value_counts().to_dict(),
            "po_order_uom_mix": po["order_uom"].value_counts().to_dict(),
            "weeks_of_cover_at_as_of": q(inv["available_qty"] / (wk.reindex(pd.MultiIndex.from_frame(inv[["sku_id", "location_id"]])).values + 1e-9))}
