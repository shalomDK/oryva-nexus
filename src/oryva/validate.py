"""Validation suite (PDF section 5 Step 8 + section 7 acceptance criteria).

Checks: PK uniqueness, FK integrity, allowed enums, date ordering, arithmetic reconciliation, lifecycle
transitions, duplicates, assortment coverage, acceptance criteria.  Five *labelled* data-quality checks
(`kind='labelled'`) are expected to fail only on injected ground-truth rows; every other check must pass.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import dq, ids, weeks as W
from .schema import T as SCH

PO_FLOW = {(None, "PLANNED"), ("PLANNED", "CONFIRMED"), ("PLANNED", "CANCELLED"), ("CONFIRMED", "IN_TRANSIT"),
           ("CONFIRMED", "CANCELLED"), ("IN_TRANSIT", "DELAYED"), ("IN_TRANSIT", "RECEIVED"), ("DELAYED", "DELAYED"),
           ("DELAYED", "RECEIVED")}
PP_FLOW = {(None, "PLANNED"), ("PLANNED", "FIRMED"), ("FIRMED", "RELEASED"), ("RELEASED", "COMPLETED"),
           ("PLANNED", "CANCELLED"), ("FIRMED", "CANCELLED")}
SH_FLOW = {(None, "DETECTED"), ("DETECTED", "ANALYZED"), ("ANALYZED", "MITIGATION_PROPOSED"), ("ANALYZED", "NEEDS_REVIEW"),
           ("NEEDS_REVIEW", "DETECTED"), ("MITIGATION_PROPOSED", "MITIGATION_APPROVED"),
           ("MITIGATION_PROPOSED", "ACCEPTED_BACKORDER"), ("MITIGATION_APPROVED", "RESOLVED")}
MIT_FLOW = {(None, "PROPOSED"), ("PROPOSED", "APPROVED"), ("PROPOSED", "REJECTED"), ("APPROVED", "EXECUTED")}
LABELLED = {"dq.duplicate_po": "INBOUND_DOUBLE_COUNT", "dq.uom_arithmetic": "UOM_MISMATCH",
            "dq.capacity_ledger": "SUPPLIER_CAPACITY_EXCEEDED", "dq.lead_time_defined": "SHORTAGE_MISSING_LEAD_TIME",
            "dq.substitute_approved": "SUBSTITUTE_NOT_APPROVED"}


class Report:
    def __init__(self):
        self.rows = []
        self.labelled = []

    def add(self, check, table, n, bad, category, kind="rule", issue=None, rids=None):
        bad = list(bad) if not isinstance(bad, (int, np.integer)) else bad
        nb = bad if isinstance(bad, (int, np.integer)) else len(bad)
        ex = "" if isinstance(bad, (int, np.integer)) or not bad else "; ".join(str(x) for x in bad[:3])
        self.rows.append({"category": category, "check": check, "table": table, "kind": kind, "checked": int(n),
                          "failed": int(nb), "status": "PASS" if nb == 0 else ("LABELLED" if kind == "labelled" else "FAIL"), "examples": ex})
        if kind == "labelled" and rids is not None:
            self.labelled += [{"issue_type": issue, "record_id": x} for x in rids]

    def frame(self):
        return pd.DataFrame(self.rows)

    @property
    def unexpected_failures(self):
        return int(sum(r["failed"] for r in self.rows if r["kind"] != "labelled"))


def _flow(events, id_col, flow, header, hid, rep, name):
    e = events.sort_values("event_id", kind="mergesort").reset_index(drop=True)
    prev_to = e.groupby(id_col)["to_status"].shift(1)
    prev_dt = e.groupby(id_col)["event_date"].shift(1)
    cur_from = e["from_status"].where(e["from_status"].notna(), None)
    pairs = list(zip(cur_from, e["to_status"]))
    bad_flow = [e[id_col].iat[i] for i, pr in enumerate(pairs) if pr not in flow]
    rep.add(f"{name}.transitions_allowed", name, len(e), bad_flow, "lifecycle")
    chain_bad = e[(prev_to.notna() & (e["from_status"] != prev_to)) | (prev_to.isna() & e["from_status"].notna())][id_col].tolist()
    rep.add(f"{name}.from_status_matches_previous", name, len(e), chain_bad, "lifecycle")
    rep.add(f"{name}.dates_non_decreasing", name, len(e), e[prev_dt.notna() & (e["event_date"] < prev_dt)][id_col].tolist(), "date_order")
    last = e.groupby(id_col)["to_status"].last()
    h = header.set_index(hid)["status"]
    mism = [i for i in h.index if last.get(i) != h[i]]
    rep.add(f"{name}.header_status_equals_last_event", name, len(h), mism, "lifecycle")
    rep.add(f"{name}.every_entity_has_events", name, len(h), [i for i in h.index if i not in last.index], "lifecycle")


def validate(T: dict, P: dict | None = None) -> Report:
    rep = Report()
    as_of = str(T["Inventory"]["as_of_date"].iloc[0])

    # ---------------------------------------------------------------- generic schema checks
    for name, df in T.items():
        t = SCH[name]
        rep.add("schema.columns_match", name, len(t.cols), [c for c in t.cols if c not in df.columns] + [c for c in df.columns if c not in t.cols], "schema")
        dup = df.duplicated(t.pk, keep=False)
        rep.add("pk.unique", name, len(df), df.loc[dup, t.pk[0]].tolist(), "primary_key")
        for f in t.fields:
            col = df[f.name]
            nn = col.notna()
            if f.req:
                rep.add(f"required.{f.name}", name, len(df), np.nonzero(~nn.to_numpy())[0].tolist(), "required")
            if f.uniq and len(t.pk) == 1 and f.name != t.pk[0]:
                rep.add(f"unique.{f.name}", name, len(df), df.loc[col.duplicated(keep=False) & nn, t.pk[0]].tolist(), "unique")
            if f.allowed is not None:
                allowed = set(f.allowed)
                rep.add(f"enum.{f.name}", name, int(nn.sum()), df.loc[nn & ~col.isin(allowed), t.pk[0]].tolist(), "enum")
            if f.pat and f.typ in ("str", "date"):
                rx = re.compile(f.pat)
                bad = [i for i, v in zip(df[t.pk[0]], col) if v is not None and not (isinstance(v, float)) and rx.match(str(v)) is None] if len(df) < 200000 \
                    else df.loc[nn & ~col.astype(str).str.match(f.pat), t.pk[0]].tolist()
                rep.add(f"pattern.{f.name}", name, int(nn.sum()), bad, "id_pattern" if f.name.endswith("_id") else "format")
            if f.mn is not None and f.typ in ("int", "float"):
                rep.add(f"min.{f.name}", name, int(nn.sum()), df.loc[nn & (col < f.mn), t.pk[0]].tolist(), "range")
            if f.mx is not None and f.typ in ("int", "float"):
                rep.add(f"max.{f.name}", name, int(nn.sum()), df.loc[nn & (col > f.mx), t.pk[0]].tolist(), "range")
            if f.fk:
                pt, pc = f.fk.split(".")
                if pt in T:
                    parent = set(T[pt][pc])
                    rep.add(f"fk.{f.name}->{f.fk}", name, int(nn.sum()), df.loc[nn & ~col.isin(parent), t.pk[0]].tolist(), "foreign_key")

    # later checks use lookups keyed by PK: continue on de-duplicated copies so a PK failure is reported, not fatal
    T = {n: (df.drop_duplicates(SCH[n].pk, keep="first").reset_index(drop=True) if df.duplicated(SCH[n].pk).any() else df) for n, df in T.items()}
    sku, loc, sl = T["SKU"], T["Location"], T["SKULocation"]
    fd, inv, po = T["ForecastDemand"], T["Inventory"], T["PurchaseOrder"]

    # ---------------------------------------------------------------- IDs recomputed from FKs
    rep.add("id.demand_id_from_fks", "ForecastDemand", len(fd),
            fd.loc[fd["demand_id"] != "DEM-" + fd["sku_id"] + "-" + fd["location_id"] + "-" + fd["iso_week"], "demand_id"].tolist(), "id_pattern")
    rep.add("id.inventory_id_from_fks", "Inventory", len(inv), inv.loc[inv["inventory_id"] != "INV-" + inv["sku_id"] + "-" + inv["location_id"], "inventory_id"].tolist(), "id_pattern")
    wk_ok = fd["iso_week"] == [W.label(int(w)) for w in W.weeks_of(fd["week_start_date"])]
    rep.add("id.iso_week_matches_date", "ForecastDemand", len(fd), fd.loc[~wk_ok, "demand_id"].tolist(), "date_order")
    if "MitigationOption" in T and len(T["MitigationOption"]):
        m = T["MitigationOption"]
        rep.add("id.mitigation_id_from_shortage", "MitigationOption", len(m),
                m.loc[m["mitigation_id"].str.replace(r"-\d{2}$", "", regex=True).str.replace("MIT-", "") != m["shortage_id"], "mitigation_id"].tolist(), "id_pattern")

    # ---------------------------------------------------------------- assortment / coverage (SKU x Location x 52 weeks)
    active = sl[sl["stocking_status"] == "ACTIVE"]
    inactive = sl[sl["stocking_status"] == "INACTIVE"]
    cnt = fd.groupby(["sku_id", "location_id"]).agg(n=("iso_week", "nunique"), rows=("iso_week", "size"))
    akeys = set(zip(active["sku_id"], active["location_id"]))
    cmap = {k: (n_, r_) for k, n_, r_ in zip(cnt.index, cnt["n"], cnt["rows"])}
    bad = [k for k in akeys if cmap.get(k) != (52, 52)]
    rep.add("coverage.active_pair_has_52_weeks", "ForecastDemand", len(akeys), [f"{a}/{b}" for a, b in bad], "coverage")
    rep.add("coverage.demand_only_for_active_pairs", "ForecastDemand", len(cnt), [f"{a}/{b}" for a, b in cnt.index if (a, b) not in akeys], "coverage")
    ikeys = set(zip(inv["sku_id"], inv["location_id"]))
    rep.add("coverage.inventory_pairs_equal_active_pairs", "Inventory", len(akeys), [f"{a}/{b}" for a, b in (akeys ^ ikeys)], "coverage")
    rep.add("coverage.every_sku_in_master_has_active_location", "SKU", len(sku), sorted(set(sku["sku_id"]) - set(active["sku_id"])), "coverage")
    rep.add("coverage.every_location_has_active_sku", "Location", len(loc), sorted(set(loc["location_id"]) - set(active["location_id"])), "coverage")
    rep.add("coverage.inactive_pairs_have_no_demand", "SKULocation", len(inactive), [f"{a}/{b}" for a, b in zip(inactive["sku_id"], inactive["location_id"]) if (a, b) in cnt.index], "coverage")
    if P:
        rep.add("volume.sku_count", "SKU", 1, [] if len(sku) == P["n_skus"] else [f"{len(sku)}!={P['n_skus']}"], "volume")
        rep.add("volume.location_count", "Location", 1, [] if len(loc) == P["n_locations"] else [f"{len(loc)}!={P['n_locations']}"], "volume")
        rep.add("volume.supplier_count", "Supplier", 1, [] if len(T["Supplier"]) == P["n_suppliers"] else ["supplier count"], "volume")
        rep.add("volume.purchase_order_count", "PurchaseOrder", 1, [] if len(po) == P["n_purchase_orders"] else [f"{len(po)}!={P['n_purchase_orders']}"], "volume")
        rep.add("volume.demand_weeks", "ForecastDemand", 1, [] if fd["iso_week"].nunique() == P["n_weeks"] else ["weeks"], "volume")

    # ---------------------------------------------------------------- foreign-key pair integrity (composite)
    slkeys = set(zip(sl["sku_id"], sl["location_id"]))
    rep.add("fk.demand_pair_in_SKULocation", "ForecastDemand", len(cnt), [f"{a}/{b}" for a, b in cnt.index if (a, b) not in slkeys], "foreign_key")
    ssk = set(zip(T["SKUSupplier"]["sku_id"], T["SKUSupplier"]["supplier_id"]))
    rep.add("fk.PO_supplier_sku_in_SKUSupplier", "PurchaseOrder", len(po), po.loc[[(a, b) not in ssk for a, b in zip(po["sku_id"], po["supplier_id"])], "po_id"].tolist(), "foreign_key")
    rep.add("fk.PO_ship_to_pair_in_SKULocation", "PurchaseOrder", len(po),
            po.loc[[(a, b) not in akeys for a, b in zip(po["sku_id"], po["ship_to_location_id"])], "po_id"].tolist(), "foreign_key")
    pp = T["ProductionPlan"]
    plants = set(loc.loc[loc["location_type"] == "PLANT", "location_id"])
    skutype = sku.set_index("sku_id")["sku_type"]
    rep.add("fk.ProductionPlan_at_plant_for_make_sku", "ProductionPlan", len(pp),
            pp.loc[[(l not in plants) or skutype[s] != "FINISHED_MAKE" for s, l in zip(pp["sku_id"], pp["location_id"])], "production_plan_id"].tolist(), "foreign_key")

    # ---------------------------------------------------------------- date ordering
    eff_tabs = [n for n, t in SCH.items() if "effective_to" in t.cols and n in T]
    for n in eff_tabs:
        df = T[n]
        bad = df[df["effective_to"].notna() & (df["effective_from"] >= df["effective_to"])]
        rep.add("dates.effective_from_before_to", n, len(df), bad[SCH[n].pk[0]].tolist(), "date_order")
    d = po
    for a, b in (("created_date", "order_date"), ("order_date", "requested_date"), ("requested_date", "promised_date"), ("promised_date", "eta_date")):
        rep.add(f"dates.PO.{a}<={b}", "PurchaseOrder", len(d), d.loc[d[a] > d[b], "po_id"].tolist(), "date_order")
    rep.add("dates.PO.created<=as_of", "PurchaseOrder", len(d), d.loc[d["created_date"] > as_of, "po_id"].tolist(), "date_order")
    rep.add("dates.PO.receipt_only_when_received_and_equals_eta", "PurchaseOrder", len(d),
            d.loc[(d["actual_receipt_date"].notna() != (d["status"] == "RECEIVED")) | (d["actual_receipt_date"].notna() & (d["actual_receipt_date"] != d["eta_date"])), "po_id"].tolist(), "date_order")
    rep.add("dates.PO.received_before_as_of_open_not", "PurchaseOrder", len(d),
            d.loc[((d["status"] == "RECEIVED") & (d["eta_date"] >= as_of)) | (d["status"].isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"]) & (d["eta_date"] < as_of)), "po_id"].tolist(), "date_order")
    for n in ("PurchaseOrderEvent", "TransportEvent", "InventoryEvent", "ProductionPlanEvent"):
        e = T[n]
        rep.add(f"dates.{n}.not_after_as_of", n, len(e), e.loc[e["event_date"] > as_of, "event_id"].tolist(), "date_order")
    lt = T["LeadTime"]
    rep.add("dates.LeadTime.p90>=total", "LeadTime", len(lt), lt.loc[lt["p90_lead_days"] < lt["total_lead_days"], "lead_time_id"].tolist(), "range")
    su = T["SKUSubstitute"]
    rep.add("dates.SKUSubstitute.approved_date<=as_of", "SKUSubstitute", len(su), su.loc[su["approved_date"].notna() & (su["approved_date"] > as_of), "sku_id"].tolist(), "date_order")
    rep.add("rules.SKUSubstitute.approved_has_role_and_date", "SKUSubstitute", len(su),
            su.loc[(su["approval_status"] == "APPROVED") & (su["approved_by_role"].isna() | su["approved_date"].isna()), "sku_id"].tolist(), "required")
    rep.add("rules.SKUSubstitute.not_self", "SKUSubstitute", len(su), su.loc[su["sku_id"] == su["substitute_sku_id"], "sku_id"].tolist(), "range")
    rep.add("rules.SKU.price>=cost", "SKU", len(sku), sku.loc[sku["unit_price"] < sku["unit_cost"], "sku_id"].tolist(), "range")

    # ---------------------------------------------------------------- arithmetic reconciliation
    rep.add("arith.Inventory.available", "Inventory", len(inv), inv.loc[inv["available_qty"] != inv["on_hand_qty"] - inv["allocated_qty"] - inv["quality_hold_qty"], "inventory_id"].tolist(), "arithmetic")
    rep.add("arith.LeadTime.total", "LeadTime", len(lt), lt.loc[lt["total_lead_days"] != lt["production_days"] + lt["transit_days"], "lead_time_id"].tolist(), "arithmetic")
    rep.add("arith.PO.total_cost", "PurchaseOrder", len(po), po.loc[(po["total_cost"] - (po["qty_base"] * po["unit_price"]).round(2)).abs() > 0.011, "po_id"].tolist(), "arithmetic")
    dl = T["PurchaseOrderEvent"]
    dsum = dl[dl["event_type"] == "DELAYED"].groupby("po_id")["delay_days"].sum()
    exp_eta = pd.to_datetime(po["promised_date"]) + pd.to_timedelta(po["po_id"].map(dsum).fillna(0).astype(int), unit="D")
    rep.add("arith.PO.eta=promised+delays", "PurchaseOrder", len(po), po.loc[exp_eta.dt.strftime("%Y-%m-%d") != po["eta_date"], "po_id"].tolist(), "arithmetic")
    bom = T["BillOfMaterial"].set_index("bom_id")
    rt = pp["bom_id"].map(bom["run_time_hours_per_unit"])
    lot = pp["bom_id"].map(bom["lot_size"])
    rep.add("arith.ProductionPlan.required_hours", "ProductionPlan", len(pp), pp.loc[(pp["required_hours"] - pp["planned_qty"] * rt).abs() > 0.01, "production_plan_id"].tolist(), "arithmetic")
    rep.add("arith.ProductionPlan.multiple_of_lot", "ProductionPlan", len(pp), pp.loc[pp["planned_qty"] % lot != 0, "production_plan_id"].tolist(), "arithmetic")
    pe = dq.po_effective(T)
    rep.add("arith.PO.factor_exists_for_order_uom", "PurchaseOrder", len(po), pe.loc[pe["factor_missing"], "po_id"].tolist(), "arithmetic")
    rep.add("arith.PO.moq_and_multiple", "PurchaseOrder", len(po), _moq_multiple_bad(T, pe), "arithmetic")

    # ---------------------------------------------------------------- lifecycle
    _flow(T["PurchaseOrderEvent"], "po_id", PO_FLOW, po, "po_id", rep, "PurchaseOrderEvent")
    _flow(T["ProductionPlanEvent"], "production_plan_id", PP_FLOW, pp, "production_plan_id", rep, "ProductionPlanEvent")
    if "Shortage" in T and len(T["ShortageEvent"]):
        _flow(T["ShortageEvent"], "shortage_id", SH_FLOW, T["Shortage"], "shortage_id", rep, "ShortageEvent")
        _flow(T["MitigationEvent"], "mitigation_id", MIT_FLOW, T["MitigationOption"], "mitigation_id", rep, "MitigationEvent")
    tr = T["TransportEvent"]
    rep.add("lifecycle.TransportEvent.delay_matches_PO_event", "TransportEvent", len(tr),
            [x for x in (tr[tr["event_type"] == "DELAYED"].groupby("po_id")["delay_days"].sum() - dsum.reindex(tr[tr["event_type"] == "DELAYED"]["po_id"].unique()).fillna(0)).loc[lambda s: s != 0].index], "lifecycle")

    # ---------------------------------------------------------------- duplicates (natural keys)
    rep.add("dup.ForecastDemand.sku_loc_week", "ForecastDemand", len(fd), fd.loc[fd.duplicated(["sku_id", "location_id", "iso_week"]), "demand_id"].tolist(), "duplicate")
    rep.add("dup.LeadTime.supplier_sku_loc_from", "LeadTime", len(lt), lt.loc[lt.duplicated(["supplier_id", "sku_id", "ship_to_location_id", "effective_from"]), "lead_time_id"].tolist(), "duplicate")
    sc = T["SupplierCapacity"]
    rep.add("dup.SupplierCapacity.supplier_family_from", "SupplierCapacity", len(sc), sc.loc[sc.duplicated(["supplier_id", "product_family", "effective_from"]), "capacity_id"].tolist(), "duplicate")

    # ---------------------------------------------------------------- the five labelled data-quality checks
    dups = pe.loc[pe["is_duplicate"], "po_id"].tolist()
    rep.add("dq.duplicate_po", "PurchaseOrder", len(po), dups, "edge_case", "labelled", "INBOUND_DOUBLE_COUNT", dups)
    um = pe.loc[pe["uom_mismatch"], "po_id"].tolist()
    rep.add("dq.uom_arithmetic", "PurchaseOrder", len(po), um, "edge_case", "labelled", "UOM_MISMATCH", um)
    led = dq.ledger(T, pe)
    ex = led[led["status"] == "EXCEEDED"]
    keys = [dq.cap_key(a, b, c) for a, b, c in zip(ex["supplier_id"], ex["product_family"], ex["week_start_date"])]
    rep.add("dq.capacity_ledger", "SupplierCapacityLedger", len(led), keys, "edge_case", "labelled", "SUPPLIER_CAPACITY_EXCEEDED", keys)
    ml = dq.missing_lead_times(T)
    mk = [dq.lt_key(a, b) for a, b in zip(ml["supplier_id"], ml["sku_id"])]
    rep.add("dq.lead_time_defined", "LeadTime", len(T["SKUSupplier"]), mk, "edge_case", "labelled", "SHORTAGE_MISSING_LEAD_TIME", mk)
    ua = dq.unapproved_substitutes(T, as_of)
    uk = [dq.sub_key(a, b, c) for a, b, c in zip(ua["sku_id"], ua["substitute_sku_id"], ua["effective_from"])]
    rep.add("dq.substitute_approved", "SKUSubstitute", len(su), uk, "edge_case", "labelled", "SUBSTITUTE_NOT_APPROVED", uk)

    if "Shortage" in T and len(T.get("ProjectedBalance", [])):
        _validate_outputs(T, rep, as_of, pe)
    return rep


def _moq_multiple_bad(T, pe):
    cap = T["SupplierCapacity"]
    base = cap.sort_values("effective_from").groupby(["supplier_id", "product_family"]).first()
    m = pe.merge(base[["min_order_qty", "order_multiple"]], left_on=["supplier_id", "product_family"], right_index=True, how="left")
    bad = m[(m["status"] != "CANCELLED") & ((m["qty_eff"] < m["min_order_qty"]) | (m["qty_eff"] % m["order_multiple"] != 0))]
    return bad["po_id"].tolist()


def _validate_outputs(T, rep, as_of, pe):
    pb, sh, cs, mo = T["ProjectedBalance"], T["Shortage"], T["ShortageCause"], T["MitigationOption"]
    fd, inv = T["ForecastDemand"], T["Inventory"]
    # R-041: week-by-week reconciliation
    resid = pb["closing_qty"] - (pb["opening_qty"] + pb["scheduled_receipts_qty"] + pb["production_receipts_qty"] - pb["gross_demand_qty"] - pb["dependent_demand_qty"])
    rep.add("accept.PAB_identity_each_week", "ProjectedBalance", len(pb), (pb.loc[resid != 0, "sku_id"] + "/" + pb.loc[resid != 0, "location_id"] + "/" + pb.loc[resid != 0, "iso_week"]).tolist(), "acceptance")
    pb = pb.sort_values(["sku_id", "location_id", "week_start_date"])
    prev = pb.groupby(["sku_id", "location_id"])["closing_qty"].shift(1)
    brk = pb[prev.notna() & (pb["opening_qty"] != prev)]
    rep.add("accept.PAB_opening_equals_previous_closing", "ProjectedBalance", len(pb), (brk["sku_id"] + "/" + brk["location_id"] + "/" + brk["iso_week"]).tolist(), "acceptance")
    first = pb.groupby(["sku_id", "location_id"]).head(1).merge(inv[["sku_id", "location_id", "available_qty"]], on=["sku_id", "location_id"])
    rep.add("accept.PAB_week1_opening_equals_inventory_available", "ProjectedBalance", len(first), first.loc[first["opening_qty"] != first["available_qty"], "sku_id"].tolist(), "acceptance")
    gd = fd.groupby(["sku_id", "location_id"])["forecast_qty"].sum()
    gp = pb.groupby(["sku_id", "location_id"])["gross_demand_qty"].sum()
    rep.add("accept.PAB_gross_demand_equals_forecast", "ProjectedBalance", len(gd), [f"{a}/{b}" for (a, b), v in gd.items() if gp.get((a, b)) != v], "acceptance")
    # receipts reconcile to POs (independent recomputation)
    op = pe[pe["status"].isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"]) & ~pe["is_duplicate"] & ~pe["factor_missing"]]
    op = op[(op["eta_date"] >= W.week_start_s(1)) & (op["eta_date"] < W.week_start_s(53))]
    exp = op.groupby(["sku_id", "ship_to_location_id"])["qty_eff"].sum()
    got = pb.groupby(["sku_id", "location_id"])["scheduled_receipts_qty"].sum()
    rep.add("accept.PAB_receipts_equal_open_PO_quantities", "ProjectedBalance", len(got), [f"{a}/{b}" for (a, b), v in got.items() if v != exp.get((a, b), 0)], "acceptance")
    # shortage derivation
    rep.add("arith.Shortage.value_at_risk", "Shortage", len(sh), sh.loc[(sh["value_at_risk"] - sh["shortage_qty"] * sh["sku_id"].map(T["SKU"].set_index("sku_id")["unit_price"])).abs() > 0.011, "shortage_id"].tolist(), "arithmetic")
    pbi = pb.set_index(["sku_id", "location_id", "iso_week"])
    peak = pbi.loc[list(zip(sh["sku_id"], sh["location_id"], sh["peak_short_week"]))]
    rep.add("arith.Shortage.qty=safety-closing_at_peak", "Shortage", len(sh), sh.loc[(peak["shortfall_qty"].to_numpy() != sh["shortage_qty"].to_numpy()), "shortage_id"].tolist(), "arithmetic")
    # R-042
    sums = cs.groupby("shortage_id")["contribution_qty"].sum()
    rep.add("accept.every_shortage_has_a_cause", "Shortage", len(sh), sh.loc[~sh["shortage_id"].isin(cs["shortage_id"]), "shortage_id"].tolist(), "acceptance")
    rep.add("accept.causes_reconcile_to_shortage_qty", "ShortageCause", len(sh), [s for s, q in zip(sh["shortage_id"], sh["shortage_qty"]) if sums.get(s, 0) != q], "acceptance")
    rep.add("accept.cause_has_source_record", "ShortageCause", len(cs), cs.loc[cs["source_id"].isna() | (cs["source_id"] == ""), "shortage_id"].tolist(), "acceptance")
    # source records must exist
    src_ok = {"PurchaseOrder": set(T["PurchaseOrder"]["po_id"]), "ForecastDemand": set(fd["demand_id"]), "ProductionPlan": set(T["ProductionPlan"]["production_plan_id"]),
              "Inventory": set(inv["inventory_id"])}
    rep.add("accept.cause_source_ids_exist", "ShortageCause", len(cs), [f"{a}:{b}" for a, b in zip(cs["source_table"], cs["source_id"]) if b not in src_ok.get(a, set())], "foreign_key")
    pc = cs.sort_values(["shortage_id", "contribution_qty"], ascending=[True, False], kind="mergesort").groupby("shortage_id").head(1).set_index("shortage_id")["cause_code"]
    rep.add("arith.Shortage.primary_cause=largest_contribution", "Shortage", len(sh), sh.loc[sh["shortage_id"].map(pc) != sh["primary_cause_code"], "shortage_id"].tolist(), "arithmetic")
    # R-043 / R-044
    n_opt = mo.groupby("shortage_id").size()
    rep.add("accept.at_least_2_alternatives_per_shortage", "MitigationOption", len(sh), [s for s in sh["shortage_id"] if n_opt.get(s, 0) < 2], "acceptance")
    rep.add("accept.alternatives_show_cost_and_service", "MitigationOption", len(mo), mo.loc[mo[["total_cost", "fill_rate_pct", "cost_delta_vs_baseline"]].isna().any(axis=1), "mitigation_id"].tolist(), "acceptance")
    rec = mo[mo["is_recommendable"] == 1]
    rep.add("accept.recommendable_options_pass_policy_and_capacity", "MitigationOption", len(rec),
            rec.loc[(rec["policy_check"] != "PASS") | (rec["capacity_check"] == "FAIL") | (rec["lead_time_check"] == "MISSING"), "mitigation_id"].tolist(), "acceptance")
    rep.add("accept.recommendable_qty_within_capacity", "MitigationOption", len(rec),
            rec.loc[rec["capacity_available_qty"].notna() & (rec["option_type"].isin(["NEW_PO", "ALT_SUPPLIER_PO", "LOCATION_TRANSFER", "SUBSTITUTE_SKU", "PRODUCTION_REPLAN"]))
                    & (rec["qty"] > rec["capacity_available_qty"]), "mitigation_id"].tolist(), "acceptance")
    rep.add("accept.non_recommendable_options_explain_why", "MitigationOption", len(mo),
            mo.loc[(mo["is_recommendable"] == 0) & mo["policy_reason"].isna() & (mo["capacity_check"] != "FAIL"), "mitigation_id"].tolist(), "acceptance")
    rep.add("accept.exactly_one_recommended_per_shortage", "Shortage", len(sh),
            [s for s, n in zip(sh["shortage_id"], sh["shortage_id"].map(mo[mo["is_recommended"] == 1].groupby("shortage_id").size()).fillna(0)) if n != 1], "acceptance")
    # substitutes: recommendable options must use approved substitutes only
    subs = T["SKUSubstitute"]
    ok_pairs = set(zip(subs.loc[subs["approval_status"] == "APPROVED", "sku_id"], subs.loc[subs["approval_status"] == "APPROVED", "substitute_sku_id"]))
    s2 = rec[rec["option_type"] == "SUBSTITUTE_SKU"].merge(sh[["shortage_id", "sku_id"]], on="shortage_id")
    rep.add("accept.recommendable_substitutes_are_approved", "MitigationOption", len(s2),
            s2.loc[[(a, b) not in ok_pairs for a, b in zip(s2["sku_id"], s2["alt_sku_id"])], "mitigation_id"].tolist(), "acceptance")
    # aggregate capacity: Σ recommended new-PO quantity per supplier-family-week <= remaining capacity
    top = mo[(mo["is_recommended"] == 1) & mo["option_type"].isin(["NEW_PO", "ALT_SUPPLIER_PO"])].merge(sh[["shortage_id", "sku_id"]], on="shortage_id")
    if len(top):
        top["product_family"] = top["sku_id"].map(T["SKU"].set_index("sku_id")["product_family"])
        agg = top.groupby(["supplier_id", "product_family"], as_index=False)["qty"].sum()
        ws = dq.week_start_str(pd.Series([as_of])).iloc[0]
        agg["week_start_date"] = ws
        capq = dq.capacity_for(T["SupplierCapacity"], agg[["supplier_id", "product_family", "week_start_date"]]).fillna(0).values
        led = T["SupplierCapacityLedger"]
        com = agg.merge(led[["supplier_id", "product_family", "week_start_date", "committed_qty"]], how="left", on=["supplier_id", "product_family", "week_start_date"])["committed_qty"].fillna(0).values
        bad = agg.loc[agg["qty"] > np.maximum(0, capq - com), ["supplier_id", "product_family"]]
        rep.add("accept.recommended_PO_qty_sum_within_supplier_capacity", "MitigationOption", len(agg), (bad["supplier_id"] + "/" + bad["product_family"]).tolist(), "acceptance")
    # transfers: donors stay above safety stock after all recommended transfers
    tr = mo[(mo["is_recommended"] == 1) & (mo["option_type"] == "LOCATION_TRANSFER")].merge(sh[["shortage_id", "sku_id"]], on="shortage_id")
    if len(tr):
        pbm = T["ProjectedBalance"].assign(sur=lambda x: x["closing_qty"] - x["safety_stock_qty"]).groupby(["sku_id", "location_id"])["sur"].min()
        agg = tr.groupby(["sku_id", "source_location_id"])["qty"].sum()
        rep.add("accept.transfer_donors_stay_above_safety_stock", "MitigationOption", len(agg), [f"{a}/{b}" for (a, b), q in agg.items() if q > max(0, pbm.get((a, b), 0))], "acceptance")
    rep.add("accept.DQ_findings_reference_run", "DataQualityFinding", len(T["DataQualityFinding"]), [], "acceptance")
