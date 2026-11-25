"""Independent audit of an exported dataset (reads files from disk; does NOT reuse the validator's rules).
Usage: python scripts/audit.py data/full docs/audit_evidence_full.json"""
import gzip
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(sys.argv[1])
OUT = Path(sys.argv[2])
ev = {}


def rd(name):
    p = D / "csv" / f"{name}.csv"
    if not p.exists():
        p = D / "csv" / f"{name}.csv.gz"
    return pd.read_csv(p, keep_default_na=False, na_values=[""])


man = json.loads((D / "manifest.json").read_text())
P = man["parameters"]
tabs = list(man["table_row_counts"])
T = {t: rd(t) for t in tabs}
gt = pd.read_csv(D / "ground_truth" / "ground_truth.csv", keep_default_na=False, na_values=[""])
base_d = pd.Timestamp("2025-12-29")

# 7. volumes -------------------------------------------------------------------------------
ev["volumes"] = {"SKU": len(T["SKU"]), "Location": len(T["Location"]), "Supplier": len(T["Supplier"]),
                 "PurchaseOrder": len(T["PurchaseOrder"]), "demand_weeks": int(T["ForecastDemand"]["iso_week"].nunique()),
                 "ForecastDemand_rows": len(T["ForecastDemand"]),
                 "csv_rows_equal_manifest": all(len(T[t]) == man["table_row_counts"][t] for t in tabs)}
act = T["SKULocation"].query("stocking_status=='ACTIVE'")
cnt = T["ForecastDemand"].groupby(["sku_id", "location_id"]).size()
ev["assortment"] = {"pairs_total": len(T["SKULocation"]), "density": round(len(T["SKULocation"]) / (len(T["SKU"]) * len(T["Location"])), 4),
                    "active_pairs": len(act), "all_skus_active_somewhere": set(act.sku_id) == set(T["SKU"].sku_id),
                    "all_locations_active_somewhere": set(act.location_id) == set(T["Location"].location_id),
                    "active_pairs_with_exactly_52_weeks": bool((cnt == 52).all() and len(cnt) == len(act))}
ev["entity_volumes_present"] = {t: len(T[t]) for t in ["SKU", "Location", "ForecastDemand", "Inventory", "Supplier", "SupplierCapacity", "LeadTime", "PurchaseOrder", "ProductionPlan", "Shortage", "MitigationOption"]}

# 3. PK / FK via SQLite loaded from the SQL seed ---------------------------------------------
con = sqlite3.connect(":memory:")
con.executescript((D / "sql" / "schema.sql").read_text())
for t in tabs:
    p = D / "sql" / f"seed_{t}.sql"
    sql = p.read_text(encoding="utf-8") if p.exists() else gzip.open(str(p) + ".gz", "rt", encoding="utf-8").read()
    if sql.strip():
        con.executescript(sql)
fk_bad = con.execute("PRAGMA foreign_key_check").fetchall()
sql_counts = {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tabs}
ddl = (D / "sql" / "schema.sql").read_text()
ev["sql"] = {"load_ok": True, "foreign_key_violations": len(fk_bad), "row_counts_equal_csv": sql_counts == {t: len(T[t]) for t in tabs},
             "tables_with_primary_key": ddl.count("PRIMARY KEY"), "foreign_key_clauses": ddl.count("FOREIGN KEY"), "tables": len(tabs)}
tbl_of = {}
for m in re.finditer(r'CREATE TABLE "(\w+)" \((.*?)\n\);', ddl, re.S):
    for f in re.findall(r'FOREIGN KEY \("(\w+)"\) REFERENCES "(\w+)"\("(\w+)"\)', m.group(2)):
        tbl_of.setdefault(m.group(1), []).append(f)
fk_report = {}
for t, lst in tbl_of.items():
    for col, pt, pc in lst:
        v_ = T[t][col].dropna()
        fk_report[f"{t}.{col}->{pt}.{pc}"] = int((~v_.isin(T[pt][pc])).sum())
ev["fk_pandas"] = {"relationships_checked": len(fk_report), "orphans_total": sum(fk_report.values()), "nonzero": {k: v for k, v in fk_report.items() if v}}
pk = {}
for m in re.finditer(r'CREATE TABLE "(\w+)" \(.*?PRIMARY KEY \((.*?)\)', ddl, re.S):
    cols = [c.strip('" ') for c in m.group(2).split(",")]
    pk[m.group(1)] = int(T[m.group(1)].duplicated(cols).sum())
ev["pk_duplicates"] = {"tables": len(pk), "total_duplicates": sum(pk.values())}
sl = set(zip(T["SKULocation"].sku_id, T["SKULocation"].location_id))
ssk = set(zip(T["SKUSupplier"].sku_id, T["SKUSupplier"].supplier_id))
ev["composite_fk"] = {"demand_pair_not_in_SKULocation": int(sum(k not in sl for k in cnt.index)),
                      "PO_pair_not_in_SKULocation": int(sum((a, b) not in sl for a, b in zip(T["PurchaseOrder"].sku_id, T["PurchaseOrder"].ship_to_location_id))),
                      "PO_supplier_sku_not_in_SKUSupplier": int(sum((a, b) not in ssk for a, b in zip(T["PurchaseOrder"].sku_id, T["PurchaseOrder"].supplier_id)))}
pat = {"SKU.sku_id": r"SKU-\d{6}", "PurchaseOrder.po_id": r"PO-2026-\d{6}", "Shortage.shortage_id": r"SHORT-2026-\d{6}",
       "ForecastDemand.demand_id": r"DEM-SKU-\d{6}-LOC-\d{3}-2026W\d{2}", "MitigationOption.mitigation_id": r"MIT-SHORT-2026-\d{6}-\d{2}"}
ev["id_patterns_nonmatching"] = {k: int((~T[k.split(".")[0]][k.split(".")[1]].str.fullmatch(v_)).sum()) for k, v_ in pat.items()}
fd = T["ForecastDemand"]
ev["id_patterns_nonmatching"]["demand_id_equals_sku_loc_week"] = int((fd.demand_id != "DEM-" + fd.sku_id + "-" + fd.location_id + "-" + fd.iso_week).sum())
mo, sh = T["MitigationOption"], T["Shortage"]
ev["id_patterns_nonmatching"]["mitigation_id_prefix_equals_shortage_id"] = int((mo.mitigation_id.str[4:-3] != mo.shortage_id).sum())

# 4. independent recomputation of projected balance for buy-pairs, and shortages ----------------
sku = T["SKU"].set_index("sku_id")
inv = T["Inventory"].set_index(["sku_id", "location_id"])
po = T["PurchaseOrder"].copy()
conv = T["UoMConversion"].set_index(["sku_id", "from_uom"])["factor"]
basecol = po.sku_id.map(sku.base_uom)
fac = np.where(po.order_uom == basecol, 1.0, [conv.get((s, u), np.nan) for s, u in zip(po.sku_id, po.order_uom)])
po["q"] = np.rint(po.order_qty * fac)
po["dup"] = po.duplicated(["supplier_id", "sku_id", "ship_to_location_id", "promised_date", "supplier_ref_no"], keep="first")
k4 = ["supplier_id", "sku_id", "ship_to_location_id", "supplier_ref_no"]
rcv = set(map(tuple, po[po.status == "RECEIVED"][k4].values))
po["dup"] |= po.status.isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"]) & pd.Series([tuple(x) in rcv for x in po[k4].values], index=po.index)
openpo = po[po.status.isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"]) & ~po.dup]
openpo = openpo.assign(w=((pd.to_datetime(openpo.eta_date) - base_d).dt.days // 7 + 1))
rec = openpo[(openpo.w >= 1) & (openpo.w <= 52)].groupby(["sku_id", "ship_to_location_id", "w"]).q.sum()
pb = T["ProjectedBalance"].copy()
pb["w"] = (pd.to_datetime(pb.week_start_date) - base_d).dt.days // 7 + 1
buy = pb[pb.sku_id.map(sku.sku_type) == "FINISHED_BUY"].sort_values(["sku_id", "location_id", "w"])
dem = buy.pivot(index=["sku_id", "location_id"], columns="w", values="gross_demand_qty")
R = np.zeros(dem.shape)
idx = {k: i for i, k in enumerate(dem.index)}
for (s, l, w), q in rec.items():
    if (s, l) in idx:
        R[idx[(s, l)], w - 1] += q
av = np.array([inv.at[k, "available_qty"] for k in dem.index])
close = av[:, None] + np.cumsum(R - dem.values, axis=1)
exp = buy.pivot(index=["sku_id", "location_id"], columns="w", values="closing_qty").values
ss = np.array([inv.at[k, "safety_stock_qty"] for k in dem.index])
ev["balance_independent_recompute"] = {"buy_pairs_checked": int(len(dem)), "cells_checked": int(exp.size), "cells_mismatching": int((close != exp).sum())}
eps = {}
for i, k in enumerate(dem.index):
    m = close[i] < ss[i]
    if m.any():
        d = np.diff(np.concatenate([[0], m.astype(int), [0]]))
        for st, en in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1):
            eps[(k[0], k[1], int(st) + 1)] = int((ss[i] - close[i, st:en + 1]).max())
shb = sh[sh.sku_id.map(sku.sku_type) == "FINISHED_BUY"].copy()
shb["st"] = (pd.to_datetime(shb.need_by_date) - base_d).dt.days // 7 + 1
got = {(a, b, int(c)): int(q) for a, b, c, q in zip(shb.sku_id, shb.location_id, shb.st, shb.shortage_qty)}
ev["shortage_independent_recompute"] = {"episodes_recomputed": len(eps), "episodes_in_table": len(got), "identical": eps == got}
res = pb.closing_qty - (pb.opening_qty + pb.scheduled_receipts_qty + pb.production_receipts_qty - pb.gross_demand_qty - pb.dependent_demand_qty)
ev["pab_identity_all_pairs"] = {"rows": len(pb), "nonzero_residual": int((res != 0).sum())}
cs = T["ShortageCause"].groupby("shortage_id").contribution_qty.sum()
ev["cause_reconciliation"] = {"shortages": len(sh), "without_cause": int((~sh.shortage_id.isin(cs.index)).sum()),
                              "cause_sum_ne_qty": int((cs.reindex(sh.shortage_id).values != sh.shortage_qty.values).sum())}

# 5. supplier-order mitigation constraints (independent) --------------------------------------
cap = T["SupplierCapacity"].sort_values("effective_from")
basecap = cap.groupby(["supplier_id", "product_family"]).first()
lt = T["LeadTime"]
sup = T["Supplier"].set_index("supplier_id")
rec_m = mo[(mo.is_recommendable == 1) & mo.option_type.isin(["NEW_PO", "ALT_SUPPLIER_PO"])].merge(sh[["shortage_id", "sku_id", "location_id"]], on="shortage_id")
rec_m["fam"] = rec_m.sku_id.map(sku.product_family)
bad = {"qty_below_MOQ": 0, "qty_not_multiple": 0, "qty_over_remaining_capacity": 0, "lead_days_ne_LeadTime": 0, "supplier_not_active": 0, "arrival_ne_asof_plus_lead": 0}
ledger = T["SupplierCapacityLedger"]
led_c = {(a, b, c): q for a, b, c, q in zip(ledger.supplier_id, ledger.product_family, ledger.week_start_date, ledger.committed_qty)}
for r in rec_m.itertuples():
    b = basecap.loc[(r.supplier_id, r.fam)]
    bad["qty_below_MOQ"] += int(r.qty < b.min_order_qty)
    bad["qty_not_multiple"] += int(r.qty % b.order_multiple != 0)
    bad["qty_over_remaining_capacity"] += int(r.qty > r.capacity_available_qty)
    rows = lt[(lt.supplier_id == r.supplier_id) & (lt.sku_id == r.sku_id)]
    o = rows[rows.ship_to_location_id == r.location_id]
    rows = o if len(o) else rows[rows.ship_to_location_id.isna()]
    bad["lead_days_ne_LeadTime"] += int(len(rows) == 0 or int(rows.total_lead_days.max()) != r.lead_days)
    bad["supplier_not_active"] += int(sup.at[r.supplier_id, "status"] != "ACTIVE")
    bad["arrival_ne_asof_plus_lead"] += int((base_d + pd.Timedelta(days=int(r.lead_days))).strftime("%Y-%m-%d") != r.earliest_arrival_date)
top = rec_m[rec_m.is_recommended == 1].groupby(["supplier_id", "fam"]).qty.sum()
over = 0
for (s, f), q in top.items():
    c = cap[(cap.supplier_id == s) & (cap.product_family == f) & (cap.effective_from <= "2025-12-29")].iloc[-1].weekly_capacity_qty
    over += int(q > max(0, c - led_c.get((s, f, "2025-12-29"), 0)))
ev["mitigation_constraints"] = {"recommendable_supplier_PO_options_checked": len(rec_m), **bad, "recommended_aggregate_over_capacity": over,
                                "missing_leadtime_options_recommendable": int(((mo.lead_time_check == "MISSING") & (mo.is_recommendable == 1)).sum()),
                                "failed_policy_recommendable": int(((mo.policy_check == "FAIL") & (mo.is_recommendable == 1)).sum()),
                                "shortages_with_lt2_options": int((mo.groupby("shortage_id").size() < 2).sum()),
                                "options_missing_cost_or_service": int(mo[["total_cost", "fill_rate_pct"]].isna().any(axis=1).sum())}
subs = T["SKUSubstitute"]
ok = set(zip(subs[subs.approval_status == "APPROVED"].sku_id, subs[subs.approval_status == "APPROVED"].substitute_sku_id))
s2 = mo[(mo.option_type == "SUBSTITUTE_SKU") & (mo.is_recommendable == 1)].merge(sh[["shortage_id", "sku_id"]], on="shortage_id")
ev["mitigation_constraints"]["recommended_substitutes_not_approved"] = int(sum((a, b) not in ok for a, b in zip(s2.sku_id, s2.alt_sku_id)))

# R-043: independent checks for every other mitigation type (uses only exported tables) --------
closing = {k: g.sort_values("w").closing_qty.values for k, g in pb.groupby(["sku_id", "location_id"])}
sst = inv.safety_stock_qty.to_dict()
locreg = T["Location"].set_index("location_id").region
shw = sh.assign(p0=(pd.to_datetime(sh.need_by_date) - base_d).dt.days // 7 + 1).set_index("shortage_id")
recm = mo[mo.is_recommendable == 1].merge(shw[["sku_id", "location_id", "p0", "episode_weeks", "shortage_qty"]], left_on="shortage_id", right_index=True)
v = {"transfer_over_donor_surplus": 0, "transfer_aggregate_over_surplus": 0, "transfer_lead_days_wrong": 0, "substitute_over_surplus": 0,
     "substitute_aggregate_over_surplus": 0, "substitute_not_stocked": 0, "substitute_qty_lt_needed": 0, "production_frozen_or_late": 0,
     "production_not_lot_multiple": 0, "production_hours_over_available_conservative": 0, "expedite_bad": 0, "weeks_late_wrong": 0, "fill_rate_wrong": 0}
n = {"transfer": 0, "substitute": 0, "production": 0, "expedite": 0}
agg_t, agg_s = {}, {}
actset = set(zip(act.sku_id, act.location_id))
pp = T["ProductionPlan"]
wc_of = pp.groupby(["sku_id", "location_id"]).work_center_id.first().to_dict()
phr = T["ProductionCapacity"].set_index(["work_center_id", "week_start_date"]).available_hours
req_h = pp.groupby(["work_center_id", "week_start_date"]).required_hours.sum()
bomm = T["BillOfMaterial"].set_index("parent_sku_id")
subm = T["SKUSubstitute"].query("approval_status=='APPROVED'").set_index(["sku_id", "substitute_sku_id"]).substitution_ratio
poi2 = po.set_index("po_id")
for r in recm.itertuples():
    if r.option_type == "LOCATION_TRANSFER":
        n["transfer"] += 1
        sur = max(0, int((closing[(r.sku_id, r.source_location_id)] - sst[(r.sku_id, r.source_location_id)]).min()))
        v["transfer_over_donor_surplus"] += int(r.qty > sur)
        lead = 4 if locreg[r.source_location_id] == locreg[r.location_id] else 9
        v["transfer_lead_days_wrong"] += int(r.lead_days != lead)
        if r.is_recommended:
            agg_t[(r.sku_id, r.source_location_id)] = agg_t.get((r.sku_id, r.source_location_id), 0) + r.qty
    elif r.option_type == "SUBSTITUTE_SKU":
        n["substitute"] += 1
        a2 = r.alt_sku_id
        if (a2, r.location_id) not in actset:
            v["substitute_not_stocked"] += 1
            continue
        ratio = float(subm.get((r.sku_id, a2), np.nan))
        v["substitute_qty_lt_needed"] += int(r.qty < np.ceil(r.covered_qty * ratio - 1e-9))
        sur = max(0, int((closing[(a2, r.location_id)][r.p0 - 1:] - sst[(a2, r.location_id)]).min()))
        v["substitute_over_surplus"] += int(r.qty > sur)
        if r.is_recommended:
            q0, p00 = agg_s.get((a2, r.location_id), (0, 99))
            agg_s[(a2, r.location_id)] = (q0 + r.qty, min(p00, r.p0))
    elif r.option_type == "PRODUCTION_REPLAN":
        n["production"] += 1
        w = int((pd.Timestamp(r.earliest_arrival_date) - base_d).days // 7 + 1)
        v["production_frozen_or_late"] += int(not (2 < w <= r.p0))
        lot = int(bomm.at[r.sku_id, "lot_size"])
        rt = float(bomm.at[r.sku_id, "run_time_hours_per_unit"])
        v["production_not_lot_multiple"] += int(r.qty % lot != 0)
        wc = wc_of.get((r.sku_id, r.location_id))
        ws_ = r.earliest_arrival_date
        spare_cons = phr.get((wc, ws_), 0) - req_h.get((wc, ws_), 0)  # conservative: ignores lots the engine already cut
        v["production_hours_over_available_conservative"] += int(r.qty * rt > max(spare_cons, 0) + 1e-6)
    elif r.option_type == "EXPEDITE_PO":
        n["expedite"] += 1
        p_ = poi2.loc[r.ref_po_id]
        gain = (pd.Timestamp(p_.eta_date) - pd.Timestamp(r.earliest_arrival_date)).days
        bad_ = (p_.status not in ("CONFIRMED", "IN_TRANSIT", "DELAYED") or gain <= 0 or gain > 14
                or pd.Timestamp(r.earliest_arrival_date) < base_d + pd.Timedelta(days=2) or r.covered_qty > p_.q
                or abs(r.expedite_premium - round(r.covered_qty * p_.unit_price * 0.12, 2)) > 0.011)
        v["expedite_bad"] += int(bad_)
v["transfer_aggregate_over_surplus"] = int(sum(q > max(0, int((closing[k] - sst[k]).min())) for k, q in agg_t.items()))
v["substitute_aggregate_over_surplus"] = int(sum(q > max(0, int((closing[k][p0 - 1:] - sst[k]).min())) for k, (q, p0) in agg_s.items()))
tim = recm[recm.earliest_arrival_date.notna()]
arr_w = (pd.to_datetime(tim.earliest_arrival_date) - base_d).dt.days // 7 + 1
v["weeks_late_wrong"] = int((tim.weeks_late != np.maximum(0, arr_w - tim.p0)).sum())
cal = np.round(100 * np.minimum(1, recm.covered_qty / recm.shortage_qty) * (1 - np.minimum(1, recm.weeks_late / recm.episode_weeks)), 2)
nb = recm.option_type != "PARTIAL_FILL_BACKORDER"
v["fill_rate_wrong"] = int((np.abs(cal[nb] - recm.fill_rate_pct[nb]) > 0.011).sum())
ev["mitigation_all_types_independent"] = {"checked": n, **{k: int(x) for k, x in v.items()}}

# 2/6. ground truth: labels, leakage -------------------------------------------------------------
forb = {"issue_type", "ground_truth", "label", "is_anomaly", "anomaly", "label_class", "expected_detection"}
outputs = {"PlanRun", "ProjectedBalance", "SupplierCapacityLedger", "Shortage", "ShortageCause", "MitigationOption", "ShortageEvent", "MitigationEvent", "DataQualityFinding"}
ev["ground_truth"] = {"rows": len(gt), "by_issue_and_class": gt.groupby(["issue_type", "label_class"]).size().rename("n").reset_index().to_dict("records"),
                      "input_tables_with_label_columns": [t for t in tabs if t not in outputs and set(T[t].columns) & forb],
                      "output_tables_with_issue_type_column": [t for t in tabs if t in outputs and set(T[t].columns) & forb],
                      "gt_files_inside_csv_dir": [p.name for p in (D / "csv").iterdir() if "ground" in p.name]}
a = gt[gt.label_class == "ANOMALY"]
po_ids = set(T["PurchaseOrder"].po_id)
ev["ground_truth"]["gt_record_ids_exist"] = {"INBOUND_DOUBLE_COUNT": bool(a[a.issue_type == "INBOUND_DOUBLE_COUNT"].record_id.isin(po_ids).all()),
                                              "UOM_MISMATCH": bool(a[a.issue_type == "UOM_MISMATCH"].record_id.isin(po_ids).all())}
src = Path("src/oryva")
ev["ground_truth"]["engine_sources_referencing_ground_truth"] = [m_ for m_ in ("planning.py", "dq.py", "datagen.py", "validate.py", "frames.py")
                                                                 if re.search(r"ground_truth|GROUND_TRUTH|\bgt\b", (src / m_).read_text(encoding="utf-8"))]
sys.path.insert(0, "src")
from oryva import schema  # noqa: E402
from oryva.config import load_policy  # noqa: E402
from oryva.frames import read_csv  # noqa: E402
from oryva.planning import run_plan  # noqa: E402


def _p(t):
    return next(p for p in [(D / "csv" / f"{t}.csv"), (D / "csv" / f"{t}.csv.gz")] if p.exists())


Tin = {t: read_csv(t, _p(t)) for t in schema.INPUT_TABLES}
out, _ = run_plan(Tin, load_policy(), P["seed"], P["name"])
ev["engine_rerun_from_inputs_only_equals_export"] = {
    t: bool(out[t].reset_index(drop=True).round(4).equals(read_csv(t, _p(t)).reset_index(drop=True).round(4)))
    for t in ("Shortage", "ShortageCause", "MitigationOption", "DataQualityFinding", "ProjectedBalance", "SupplierCapacityLedger")}
fnd = T["DataQualityFinding"]
det = []
for it in sorted(a.issue_type.unique()):
    e = set(a[a.issue_type == it].record_id)
    g = set(fnd[fnd.issue_type == it].record_id)
    bnd = set(gt[(gt.label_class == "BOUNDARY") & (gt.issue_type == it)].record_id)
    det.append({"issue_type": it, "labelled": len(e), "flagged": len(g), "tp": len(e & g), "fp": len(g - e), "fn": len(e - g), "boundary_flagged": len(bnd & g)})
ev["edge_case_detection"] = det

# 9. JSON vs CSV parity --------------------------------------------------------------------------
par = {}
for t in tabs:
    p = D / "json" / f"{t}.json"
    pg = D / "json" / f"{t}.json.gz"
    if p.exists() or pg.exists():
        j = pd.DataFrame(json.loads(p.read_text() if p.exists() else gzip.open(pg, "rt").read()))
        par[t] = bool(len(j) == len(T[t]) and list(j.columns) == list(T[t].columns))
    else:
        par[t] = "no_json"
ev["json_vs_csv"] = {"tables_with_json": sum(x is True for x in par.values()), "mismatch": [k for k, x in par.items() if x is False],
                     "missing": [k for k, x in par.items() if isinstance(x, str)]}

# 8. checksum verification ------------------------------------------------------------------------
badsum = [f for f, m_ in man["files"].items() if hashlib.sha256((D / f).read_bytes()).hexdigest() != m_["sha256"]]
ev["manifest"] = {"files": len(man["files"]), "checksum_mismatch": badsum, "seed": man["seed"], "command": man["generator_command"]}
OUT.write_text(json.dumps(ev, indent=2, default=str))
print(json.dumps(ev, indent=2, default=str))

