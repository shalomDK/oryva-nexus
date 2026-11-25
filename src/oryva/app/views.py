"""Application pages.  Each page is `page_xxx(c)` where `c` is the AppContext (dataset, user, state).
Pages only READ the dataset; every state-changing action goes through `State` (permissioned + audited)."""
from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st

from .. import weeks as W
from ..advanced import decision, optimize, recovery, replenish, risk, supplier_intel
from ..advanced.assistant import CAPS, ask, llm_available, validate_option
from ..advanced.kpi import plan_kpis
from ..advanced.scenario import Scenario, simulate
from ..report import build_report
from . import cache, ui

log = logging.getLogger("oryva.app")


def _own_supplier(c):
    return c.user.get("supplier_id") if c.user["role"] == "SUPPLIER" else None


def _extra_load(c) -> dict:
    """Supplier-family-week load already taken by approved draft orders (approvals cannot jointly exceed capacity)."""
    from .. import dq
    fam = c.ds["T"]["SKU"].set_index("sku_id")["product_family"]
    out = {}
    for d in c.state.approved_load(c.key):
        k = (d["supplier_id"], fam[d["sku_id"]], dq.week_start_str(pd.Series([d["order_date"]])).iloc[0])
        out[k] = out.get(k, 0) + d["qty_base"]
    return out


def _kp(c):
    k = st.session_state.setdefault("_kpis", {})
    if c.key not in k:
        k[c.key] = plan_kpis(c.ds["out"])
    return k[c.key]


# ======================================================================== Overview
def page_overview(c):
    ds, out, T = c.ds, c.ds["out"], c.ds["T"]
    k = _kp(c)
    ui.title("Executive overview", f"Planning snapshot as of {ds['as_of']} - dataset <b>{c.key}</b> ({len(T['SKU']):,} SKUs, {len(T['Location'])} locations, {len(T['Supplier'])} suppliers)")
    po, card = T["PurchaseOrder"], cache.get_card(c.path)
    sl_tone = "good" if k["service_level_pct"] >= 98 else ("warn" if k["service_level_pct"] >= 95 else "bad")
    ui.kpis([
        {"label": "Service level", "value": f"{k['service_level_pct']:.2f}%", "note": f"{k['unmet_units']:,.0f} units unmet of {k['demand_units']:,.0f}", "tone": sl_tone},
        {"label": "Shortages", "value": f"{k['shortages']:,}", "note": f"{k['stockouts']:,} stock-outs - {k['pairs_with_shortage_pct']}% of SKU-locations", "tone": "warn"},
        {"label": "Value at risk", "value": ui.money(k["value_at_risk"]), "note": f"{k['shortage_units']:,} units short", "tone": "bad"},
        {"label": "Recommended plan cost", "value": ui.money(k["recommended_cost"]), "note": f"vs {ui.money(k['do_nothing_cost'])} if we do nothing", "tone": "good"},
        {"label": "Mean fill rate", "value": f"{k['mean_fill_rate_pct']:.1f}%", "note": "of recommended mitigations", "tone": "info"},
        {"label": "Needs data review", "value": f"{k['needs_review']:,}", "note": "shortages blocked by missing lead time", "tone": "warn" if k["needs_review"] else "good"}])
    ui.kpis([
        {"label": "Open purchase orders", "value": f"{int(po['status'].isin(['PLANNED', 'CONFIRMED', 'IN_TRANSIT', 'DELAYED']).sum()):,}", "note": f"{int((po['status'] == 'DELAYED').sum())} delayed - {int((po['status'] == 'IN_TRANSIT').sum())} in transit"},
        {"label": "Low-tier suppliers", "value": f"{int((card['tier'] == 'D').sum()):,}", "note": f"tier D of {len(card)} suppliers", "tone": "warn"},
        {"label": "Data-quality findings", "value": f"{len(out['DataQualityFinding']):,}", "note": "raised by the planning gate", "tone": "info"},
        {"label": "Pending proposals", "value": f"{int((cache.get_proposals(c.path)['valid']).sum()) if len(cache.get_proposals(c.path)) else 0:,}", "note": "validated replenishment orders", "tone": "info"}])
    st_ = cache.get_stats(c.path)
    left, right = st.columns(2)
    sh = out["Shortage"]
    with left:
        if len(sh):
            by = sh.groupby("primary_cause_code").agg(shortages=("shortage_id", "size"), value_at_risk=("value_at_risk", "sum")).reset_index().sort_values("shortages", ascending=False)
            ui.show_chart(ui.bar(by, "shortages", "primary_cause_code", title="Shortages by primary cause", height=300))
        else:
            ui.empty("No shortages in this plan.")
    with right:
        w = st_["weekly"]
        ui.show_chart(ui.line(w[["iso_week", "service_level_pct"]], "iso_week", "service_level_pct", title="Service level by week (%)", area=True, height=300))
    left, right = st.columns(2)
    with left:
        if len(sh):
            loc = sh.groupby("location_id")["value_at_risk"].sum().sort_values(ascending=False).head(10).reset_index()
            ui.show_chart(ui.bar(loc, "value_at_risk", "location_id", title="Top locations by value at risk", height=300))
    with right:
        w = st_["weekly"]
        long = w.melt(id_vars="iso_week", value_vars=["demand", "receipts", "production"], var_name="flow", value_name="units")
        ui.show_chart(ui.line(long, "iso_week", "units", color="flow", title="Weekly demand vs. supply flows (units)", height=300))
    st.subheader("Needs attention")
    top = sh.sort_values("priority_rank").head(8)
    mo = out["MitigationOption"]
    rec = mo[mo["is_recommended"] == 1].set_index("shortage_id")
    top = top.assign(recommended_action=top["shortage_id"].map(rec["option_type"]), fill_rate_pct=top["shortage_id"].map(rec["fill_rate_pct"]))
    ui.show_df(top[["priority_rank", "shortage_id", "sku_id", "location_id", "first_short_week", "shortage_qty", "value_at_risk", "primary_cause_code", "recommended_action", "fill_rate_pct", "status"]])


# ======================================================================== Inventory
def page_inventory(c):
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Inventory management", "On-hand, available and projected balance versus safety stock")
    inv = T["Inventory"].merge(T["SKU"][["sku_id", "sku_name", "product_family", "sku_type", "criticality", "unit_cost"]], on="sku_id").merge(
        cache.get_stats(c.path)["avg_demand"], on=["sku_id", "location_id"], how="left")
    inv["weeks_of_cover"] = (inv["available_qty"] / inv["avg_weekly_demand"].replace(0, np.nan)).round(1)
    inv["stock_value"] = (inv["on_hand_qty"] * inv["unit_cost"]).round(2)
    inv["position"] = np.where(inv["available_qty"] < inv["safety_stock_qty"], "BELOW SAFETY STOCK", np.where(inv["weeks_of_cover"] > 26, "EXCESS (>26 wks)", "HEALTHY"))
    short_pairs = set(zip(out["Shortage"]["sku_id"], out["Shortage"]["location_id"]))
    inv["projected_shortage"] = [(a, b) in short_pairs for a, b in zip(inv["sku_id"], inv["location_id"])]
    f1, f2, f3, f4 = st.columns([2, 2, 2, 3])
    loc = f1.multiselect("Location", sorted(inv["location_id"].unique()))
    fam = f2.multiselect("Product family", sorted(inv["product_family"].unique()))
    pos = f3.multiselect("Position", ["BELOW SAFETY STOCK", "HEALTHY", "EXCESS (>26 wks)"])
    q = f4.text_input("Search SKU / name", placeholder="e.g. SKU-000012")
    v = inv
    if loc: v = v[v["location_id"].isin(loc)]
    if fam: v = v[v["product_family"].isin(fam)]
    if pos: v = v[v["position"].isin(pos)]
    if q: v = v[v["sku_id"].str.contains(q, case=False) | v["sku_name"].str.contains(q, case=False)]
    ui.kpis([{"label": "Stock value", "value": ui.money(v["stock_value"].sum()), "note": f"{len(v):,} SKU-locations"},
             {"label": "Below safety stock", "value": f"{int((v['position'] == 'BELOW SAFETY STOCK').sum()):,}", "tone": "bad" if (v["position"] == "BELOW SAFETY STOCK").any() else "good"},
             {"label": "Projected shortages", "value": f"{int(v['projected_shortage'].sum()):,}", "tone": "warn"},
             {"label": "Median weeks of cover", "value": f"{v['weeks_of_cover'].median():.1f}" if len(v) else "n/a", "tone": "info"}])
    a, b = st.columns(2)
    with a:
        g = v.groupby("location_id")["stock_value"].sum().sort_values(ascending=False).head(12).reset_index()
        if len(g): ui.show_chart(ui.bar(g, "stock_value", "location_id", title="Stock value by location"))
    with b:
        g = v.groupby("position").size().rename("pairs").reset_index()
        if len(g): ui.show_chart(ui.bar(g, "pairs", "position", title="Inventory position"))
    ui.show_df(v[["inventory_id", "sku_name", "location_id", "product_family", "on_hand_qty", "allocated_qty", "quality_hold_qty", "available_qty", "safety_stock_qty", "avg_weekly_demand", "weeks_of_cover", "position", "projected_shortage", "stock_value"]].sort_values("weeks_of_cover"), height=360)
    st.subheader("Projected balance for one SKU-location")
    if len(v):
        sel = st.selectbox("SKU-location", list(zip(v["sku_id"], v["location_id"])), format_func=lambda x: f"{x[0]} @ {x[1]}", key="inv_sel")
        pb = out["ProjectedBalance"]
        d = pb[(pb["sku_id"] == sel[0]) & (pb["location_id"] == sel[1])].sort_values("week_start_date")
        ui.show_chart(ui.line(d[["iso_week", "closing_qty", "safety_stock_qty"]].melt("iso_week", var_name="series", value_name="units"), "iso_week", "units", color="series", title="Projected available balance vs safety stock", height=300))
        ui.show_df(d[["iso_week", "opening_qty", "scheduled_receipts_qty", "production_receipts_qty", "gross_demand_qty", "dependent_demand_qty", "closing_qty", "shortfall_qty"]], height=260)


# ======================================================================== Demand
def page_demand(c):
    T = c.ds["T"]
    ui.title("Demand forecasting", "52-week SKU-location forecast, drivers and variability")
    fd = T["ForecastDemand"].merge(T["SKU"][["sku_id", "product_family", "unit_price"]], on="sku_id")
    f1, f2, f3 = st.columns(3)
    fam = f1.multiselect("Product family", sorted(fd["product_family"].unique()))
    loc = f2.multiselect("Location", sorted(fd["location_id"].unique()))
    drv = f3.multiselect("Demand driver", ["BASELINE", "SEASONAL", "PROMO", "SPIKE"])
    v = fd
    if fam: v = v[v["product_family"].isin(fam)]
    if loc: v = v[v["location_id"].isin(loc)]
    if drv: v = v[v["demand_driver"].isin(drv)]
    if v.empty:
        ui.empty("No forecast rows for this selection.")
        return
    tot = v["forecast_qty"].sum()
    ui.kpis([{"label": "Forecast units (52 wks)", "value": f"{tot:,.0f}"}, {"label": "Forecast revenue", "value": ui.money((v['forecast_qty'] * v['unit_price']).sum()), "tone": "info"},
             {"label": "Spike weeks", "value": f"{int((v['demand_driver'] == 'SPIKE').sum()):,}", "tone": "warn"}, {"label": "Promo weeks", "value": f"{int((v['demand_driver'] == 'PROMO').sum()):,}"},
             {"label": "SKU-locations", "value": f"{v[['sku_id', 'location_id']].drop_duplicates().shape[0]:,}"}])
    wk = v.groupby(["iso_week"])["forecast_qty"].sum().reset_index()
    a, b = st.columns(2)
    with a:
        ui.show_chart(ui.line(wk, "iso_week", "forecast_qty", title="Total weekly forecast (units)", area=True))
    with b:
        fw = v.groupby(["iso_week", "product_family"])["forecast_qty"].sum().reset_index()
        top = fw.groupby("product_family")["forecast_qty"].sum().sort_values(ascending=False).head(6).index
        ui.show_chart(ui.line(fw[fw["product_family"].isin(top)], "iso_week", "forecast_qty", color="product_family", title="Top families"))
    a, b = st.columns(2)
    with a:
        mix = v.groupby("demand_driver")["forecast_qty"].sum().reset_index()
        ui.show_chart(ui.bar(mix, "forecast_qty", "demand_driver", title="Forecast by driver"))
    with b:
        top_s = v.groupby("sku_id")["forecast_qty"].sum().sort_values(ascending=False).head(10).reset_index()
        ui.show_chart(ui.bar(top_s, "forecast_qty", "sku_id", title="Top SKUs by volume"))
    st.subheader("Spike and promotion weeks")
    sp = v[v["demand_driver"].isin(["SPIKE", "PROMO"])].sort_values("forecast_qty", ascending=False).head(200)
    ui.show_df(sp[["demand_id", "iso_week", "demand_driver", "forecast_qty", "forecast_stdev"]], height=300)


# ======================================================================== Suppliers
def page_suppliers(c):
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Supplier management & performance intelligence", "Scorecards derived from purchase orders, transport events and the capacity ledger")
    card = cache.get_card(c.path)
    own = _own_supplier(c)
    if own:
        card = card[card["supplier_id"] == own]
        st.info(f"Supplier portal: you can only see {own}.")
    f1, f2, f3 = st.columns(3)
    tier = f1.multiselect("Tier", ["A", "B", "C", "D"])
    reg = f2.multiselect("Region", sorted(card["region"].unique()))
    q = f3.text_input("Search supplier", placeholder="SUP-0001 or name")
    v = card
    if tier: v = v[v["tier"].isin(tier)]
    if reg: v = v[v["region"].isin(reg)]
    if q: v = v[v["supplier_id"].str.contains(q, case=False) | v["supplier_name"].str.contains(q, case=False)]
    ui.kpis([{"label": "Suppliers", "value": f"{len(v):,}"}, {"label": "Average score", "value": f"{v['score'].mean():.1f}" if len(v) else "n/a", "tone": "info"},
             {"label": "On-time (committed orders)", "value": f"{v['on_time_pct'].mean():.1f}%" if len(v) else "n/a", "tone": "good"},
             {"label": "Delay incidents", "value": f"{int(v['delay_incidents'].sum()):,}", "tone": "warn"},
             {"label": "Capacity-constrained (peak >=90%)", "value": f"{int((v['peak_util_pct'] >= 90).sum()):,}", "tone": "warn"}])
    a, b = st.columns(2)
    with a:
        if len(v): ui.show_chart(ui.bar(v.groupby("tier").size().rename("suppliers").reset_index(), "suppliers", "tier", title="Suppliers by tier", sort="x"))
    with b:
        if len(v): ui.show_chart(ui.scatter(v.assign(label=v["supplier_id"]), "peak_util_pct", "score", "tier", "orders", title="Score vs. peak capacity utilisation"))
    cols = ["supplier_id", "supplier_name", "region", "supplier_status", "score", "tier", "orders", "on_time_pct", "fulfilment_pct", "delay_incidents", "avg_delay_days", "avg_slip_days", "peak_util_pct", "weeks_over_90", "shortages_exposed", "confidence"]
    ui.show_df(v[cols].sort_values("score"), height=330)
    if len(v):
        sid = st.selectbox("Supplier detail", list(v.sort_values("score")["supplier_id"]), key="sup_sel")
        e = supplier_intel.explain_score(cache.get_card(c.path), sid)
        a, b = st.columns(2)
        with a:
            ui.show_chart(ui.bar(e, "contribution", "component", title=f"Score breakdown - {sid}", sort=None))
            ui.show_df(e)
        with b:
            led = out["SupplierCapacityLedger"].query("supplier_id == @sid").sort_values("week_start_date")
            if len(led):
                ui.show_chart(ui.line(led[["week_start_date", "utilisation_pct"]], "week_start_date", "utilisation_pct", title="Capacity utilisation by order week (%)", rule=100))
            dl = T["TransportEvent"].merge(T["PurchaseOrder"][["po_id", "supplier_id"]], on="po_id").query("supplier_id == @sid and event_type == 'DELAYED'")
            st.markdown(f"**Historical delays:** {len(dl)} incident(s)")
            if len(dl): ui.show_df(dl[["po_id", "event_date", "delay_days", "reason_code"]], height=180)
    st.subheader("Disruption risk")
    dr = risk.supplier_disruption_risk(T, cache.get_card(c.path))
    if own: dr = dr[dr["supplier_id"] == own]
    ui.show_df(dr.head(25)[["supplier_id", "supplier_name", "supplier_status", "score", "base", "status_adj", "single_source_adj", "open_delay_adj", "disruption_risk", "band"]], height=300)


# ======================================================================== Shortages
def page_shortages(c):
    out, T = c.ds["out"], c.ds["T"]
    ui.title("Shortage detection & prioritisation", "Every shortage is explained by evidence-linked causes and ranked by urgency, value and criticality")
    sh = out["Shortage"].merge(T["SKU"][["sku_id", "sku_name", "product_family", "criticality"]], on="sku_id")
    if sh.empty:
        ui.empty("No shortages detected.", "The plan covers all demand plus safety stock.")
        return
    f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 2, 3])
    typ = f1.multiselect("Type", sorted(sh["shortage_type"].unique()))
    cause = f2.multiselect("Primary cause", sorted(sh["primary_cause_code"].unique()))
    stat = f3.multiselect("Status", sorted(sh["status"].unique()))
    loc = f4.multiselect("Location", sorted(sh["location_id"].unique()))
    q = f5.text_input("Search", placeholder="SHORT-…, SKU-…")
    v = sh
    if typ: v = v[v["shortage_type"].isin(typ)]
    if cause: v = v[v["primary_cause_code"].isin(cause)]
    if stat: v = v[v["status"].isin(stat)]
    if loc: v = v[v["location_id"].isin(loc)]
    if q: v = v[v["shortage_id"].str.contains(q, case=False) | v["sku_id"].str.contains(q, case=False)]
    ui.kpis([{"label": "Shortages", "value": f"{len(v):,}", "tone": "warn"}, {"label": "Units short", "value": f"{v['shortage_qty'].sum():,}"},
             {"label": "Value at risk", "value": ui.money(v["value_at_risk"].sum()), "tone": "bad"}, {"label": "Stock-outs", "value": f"{int((v['shortage_type'] == 'STOCKOUT').sum()):,}", "tone": "bad"}])
    a, b = st.columns(2)
    with a:
        if len(v): ui.show_chart(ui.bar(v.groupby("first_short_week").size().rename("shortages").reset_index(), "first_short_week", "shortages", horizontal=False, title="Shortages by first short week", sort=None))
    with b:
        if len(v): ui.show_chart(ui.scatter(v, "shortage_qty", "value_at_risk", "primary_cause_code", title="Size vs. value at risk"))
    ui.show_df(v.sort_values("priority_rank")[["priority_rank", "priority_score", "shortage_id", "sku_id", "sku_name", "location_id", "first_short_week", "episode_weeks", "shortage_type", "shortage_qty", "value_at_risk", "primary_cause_code", "criticality", "data_quality_flag", "status"]], height=340)
    if v.empty:
        return
    st.subheader("Shortage detail")
    sid = st.selectbox("Shortage", list(v.sort_values("priority_rank")["shortage_id"]), key="short_sel")
    s = sh.set_index("shortage_id").loc[sid]
    cs = out["ShortageCause"].query("shortage_id == @sid")
    a, b = st.columns([3, 2])
    with a:
        pb = out["ProjectedBalance"]
        d = pb[(pb["sku_id"] == s["sku_id"]) & (pb["location_id"] == s["location_id"])].sort_values("week_start_date")
        ui.show_chart(ui.line(d[["iso_week", "closing_qty", "safety_stock_qty"]].melt("iso_week", var_name="series", value_name="units"), "iso_week", "units", color="series", title=f"{s['sku_id']} @ {s['location_id']}", rule=0))
    with b:
        st.markdown(f"**{sid}** - {s['shortage_type']}, {s['shortage_qty']:,} units, status {ui.badge(s['status'], 'warn')}", unsafe_allow_html=True)
        st.markdown("**Why (evidence):**")
        ui.show_df(cs[["cause_code", "contribution_qty", "source_table", "source_id", "explanation"]], height=220)
    ev = out["ShortageEvent"].query("shortage_id == @sid")
    st.markdown("**History**")
    ui.show_df(ev[["event_date", "from_status", "to_status", "actor_role", "comment"]], height=150)


# ======================================================================== Mitigation
def page_mitigation(c):
    out, T = c.ds["out"], c.ds["T"]
    ui.title("Mitigation recommendations", "Candidate actions with cost / service trade-offs, validated against policy, lead time and capacity")
    sh, mo = out["Shortage"], out["MitigationOption"]
    if sh.empty:
        ui.empty("Nothing to mitigate.")
        return
    rec = mo[mo["is_recommended"] == 1]
    mix = rec["option_type"].value_counts().rename_axis("option_type").reset_index(name="shortages")
    ui.kpis([{"label": "Recommended actions", "value": f"{len(rec):,}"}, {"label": "Total incremental cost", "value": ui.money(rec["total_cost"].sum()), "tone": "info"},
             {"label": "Average fill rate", "value": f"{rec['fill_rate_pct'].mean():.1f}%", "tone": "good"},
             {"label": "Options evaluated", "value": f"{len(mo):,}"}, {"label": "Rejected by policy/capacity", "value": f"{int((mo['is_recommendable'] == 0).sum()):,}", "tone": "warn"}])
    a, b = st.columns(2)
    with a:
        ui.show_chart(ui.bar(mix, "shortages", "option_type", title="Recommended action mix"))
    with b:
        ui.show_chart(ui.scatter(mo[mo["is_recommendable"] == 1].head(3000).assign(total_cost=lambda d: d["total_cost"].clip(lower=0.01)), "total_cost", "fill_rate_pct", "option_type", title="Cost vs. service (recommendable options)"))
    sid = st.selectbox("Shortage", list(sh.sort_values("priority_rank")["shortage_id"]), key="mit_sel")
    opts = mo[mo["shortage_id"] == sid].sort_values("rank")
    ui.show_df(opts[["rank", "mitigation_id", "option_type", "supplier_id", "alt_sku_id", "source_location_id", "qty", "covered_qty", "fill_rate_pct", "total_cost", "cost_delta_vs_baseline", "weeks_late", "lead_days", "capacity_check", "policy_check", "policy_reason", "lead_time_check", "is_recommendable", "is_recommended", "approval_required_role"]], height=300)
    top = opts[opts["is_recommended"] == 1].iloc[0]
    chk = validate_option(cache.get_ctx(c.path), top["mitigation_id"])
    st.markdown(f"**Recommended: {top['option_type']}** ({top['mitigation_id']}) - independent validation " + ui.badge("PASSED" if all(x["ok"] for x in chk) else "FAILED", "ok" if all(x["ok"] for x in chk) else "bad"), unsafe_allow_html=True)
    ui.show_df(pd.DataFrame(chk), height=200)
    cur = c.state.status_of(c.key, "mitigation", top["mitigation_id"])
    st.caption(f"Decision status: {cur or 'not yet decided'}")
    can = c.state.can(c.user, "decide_mitigation")
    b1, b2, b3 = st.columns([1, 1, 3])
    note = b3.text_input("Decision note", key="mit_note", placeholder="Required for rejection")
    if b1.button("Approve", disabled=not can or cur in ("APPROVED",), key="mit_ok"):
        try:
            if cur is None: c.state.transition(c.user, c.key, "mitigation", top["mitigation_id"], "PROPOSED", "", "decide_mitigation")
            c.state.transition(c.user, c.key, "mitigation", top["mitigation_id"], "APPROVED", note, "decide_mitigation")
            st.success("Approved and logged to the audit trail.")
        except Exception as e:
            st.error(str(e))
    if b2.button("Reject", disabled=not can or cur in ("APPROVED", "REJECTED"), key="mit_no"):
        try:
            if cur is None: c.state.transition(c.user, c.key, "mitigation", top["mitigation_id"], "PROPOSED", "", "decide_mitigation")
            c.state.transition(c.user, c.key, "mitigation", top["mitigation_id"], "REJECTED", note, "decide_mitigation")
            st.warning("Rejected and logged.")
        except Exception as e:
            st.error(str(e))
    if not can:
        st.caption("Your role cannot approve or reject mitigations.")


# ======================================================================== Purchase orders & replenishment
def page_orders(c):
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Purchase order management", "Inbound orders, replenishment proposals with approval workflow, and draft orders")
    tab1, tab2, tab3 = st.tabs(["Purchase orders", "Replenishment proposals", "Draft orders (approved)"])
    po = T["PurchaseOrder"].merge(T["SKU"][["sku_id", "product_family"]], on="sku_id")
    own = _own_supplier(c)
    if own:
        po = po[po["supplier_id"] == own]
    with tab1:
        f1, f2, f3, f4 = st.columns(4)
        stt = f1.multiselect("Status", sorted(po["status"].unique()))
        sup = f2.multiselect("Supplier", sorted(po["supplier_id"].unique()))
        loc = f3.multiselect("Ship-to", sorted(po["ship_to_location_id"].unique()))
        q = f4.text_input("Search PO / SKU", key="po_q")
        v = po
        if stt: v = v[v["status"].isin(stt)]
        if sup: v = v[v["supplier_id"].isin(sup)]
        if loc: v = v[v["ship_to_location_id"].isin(loc)]
        if q: v = v[v["po_id"].str.contains(q, case=False) | v["sku_id"].str.contains(q, case=False)]
        ui.kpis([{"label": "Orders", "value": f"{len(v):,}"}, {"label": "Order value", "value": ui.money(v["total_cost"].sum()), "tone": "info"},
                 {"label": "Delayed", "value": f"{int((v['status'] == 'DELAYED').sum()):,}", "tone": "warn"}, {"label": "In transit", "value": f"{int((v['status'] == 'IN_TRANSIT').sum()):,}"},
                 {"label": "Late vs requested", "value": f"{int((v['eta_date'] > v['requested_date']).sum()):,}", "tone": "warn"}])
        a, b = st.columns(2)
        with a:
            if len(v): ui.show_chart(ui.bar(v.groupby("status").size().rename("orders").reset_index(), "orders", "status", title="Orders by status"))
        with b:
            if len(v):
                wk = v.assign(eta_week=pd.to_datetime(v["eta_date"]).dt.strftime("%G-W%V")).groupby("eta_week")["qty_base"].sum().reset_index()
                ui.show_chart(ui.line(wk, "eta_week", "qty_base", title="Inbound quantity by ETA week", area=True))
        ui.show_df(v[["po_id", "supplier_id", "sku_id", "ship_to_location_id", "status", "order_date", "requested_date", "promised_date", "eta_date", "order_qty", "order_uom", "qty_base", "total_cost", "carrier_id"]], height=320)
        if len(v):
            pid = st.selectbox("PO detail", list(v["po_id"]), key="po_sel")
            a, b = st.columns(2)
            with a:
                st.markdown("**Order events**")
                ui.show_df(T["PurchaseOrderEvent"].query("po_id == @pid")[["event_date", "event_type", "from_status", "to_status", "actor_role", "delay_days", "reason_code"]], height=200)
            with b:
                st.markdown("**Transport events**")
                te = T["TransportEvent"].query("po_id == @pid")
                ui.show_df(te[["event_date", "event_type", "carrier_id", "delay_days", "reason_code"]], height=200) if len(te) else ui.empty("No carrier events yet.", "The order has not shipped.")
    with tab2:
        props = cache.get_proposals(c.path)
        if own:
            props = props[props["supplier_id"] == own]
        if props.empty:
            ui.empty("No replenishment proposals.", "The recommended plan has no supplier orders.")
        else:
            stat = c.state.statuses(c.key, "proposal")
            props = props.assign(decision=props["proposal_id"].map(stat).fillna("PROPOSED"))
            ui.kpis([{"label": "Proposals", "value": f"{len(props):,}"}, {"label": "Valid (all checks pass)", "value": f"{int(props['valid'].sum()):,}", "tone": "good"},
                     {"label": "Proposed value", "value": ui.money(props.loc[props['valid'], 'order_value'].sum()), "tone": "info"},
                     {"label": "Approved", "value": f"{int((props['decision'] == 'APPROVED').sum()):,}", "tone": "good"}, {"label": "Rejected", "value": f"{int((props['decision'] == 'REJECTED').sum()):,}", "tone": "warn"}])
            ui.show_df(props[["proposal_id", "decision", "valid", "priority_rank", "sku_id", "location_id", "supplier_id", "qty_base", "order_uom", "order_qty", "order_value", "order_date", "lead_days", "expected_arrival", "need_by_date", "on_time", "approval_role", "failed_checks"]].sort_values("priority_rank"), height=300)
            pid = st.selectbox("Proposal", list(props.sort_values("priority_rank")["proposal_id"]), key="prop_sel")
            p = props.set_index("proposal_id").loc[pid].to_dict() | {"proposal_id": pid}
            chk = replenish.validate_proposal(p, T, out, _extra_load(c))
            ui.show_df(pd.DataFrame(chk), height=220)
            cur = p["decision"]
            thr = c.ds["policy"]["approval_spend_threshold"]
            can = c.state.can(c.user, "decide_proposal") and (p["order_value"] <= thr or c.state.can(c.user, "decide_high_value"))
            if p["order_value"] > thr:
                st.caption(f"Order value {ui.money(p['order_value'])} exceeds the {ui.money(thr)} threshold: Ops manager / Admin approval required.")
            note = st.text_input("Decision note", key="prop_note", placeholder="Required for rejection")
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("Approve", disabled=not (can and cur == "PROPOSED"), key="prop_ok"):
                try:
                    if not all(x["ok"] for x in chk):
                        raise ValueError("proposal fails validation: " + ", ".join(x["check"] for x in chk if not x["ok"]))
                    oid = c.state.approve_proposal(c.user, c.key, p, thr, note)
                    st.success(f"Approved - draft order {oid} created (baseline untouched).")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if b2.button("Reject", disabled=not (c.state.can(c.user, "decide_proposal") and cur in ("PROPOSED",)), key="prop_no"):
                try:
                    c.state.reject_proposal(c.user, c.key, pid, note)
                    st.warning("Rejected.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    with tab3:
        d = pd.DataFrame(c.state.draft_orders(c.key))
        if d.empty:
            ui.empty("No approved orders yet.", "Approve a replenishment proposal to create a draft order.")
        else:
            ui.show_df(d)


# ======================================================================== Data quality
def page_quality(c):
    out, T = c.ds["out"], c.ds["T"]
    ui.title("Data quality & anomaly monitoring", "Exceptions raised by the planning engine's data-quality gate; source rows are never silently altered")
    f = out["DataQualityFinding"]
    led = out["SupplierCapacityLedger"]
    ui.kpis([{"label": "Findings", "value": f"{len(f):,}", "tone": "warn" if len(f) else "good"}, {"label": "Capacity-exceeded supplier-weeks", "value": f"{int((led['status'] == 'EXCEEDED').sum()):,}", "tone": "bad" if (led['status'] == 'EXCEEDED').any() else "good"},
             {"label": "Shortages needing review", "value": f"{int((out['Shortage']['status'] == 'NEEDS_REVIEW').sum()):,}", "tone": "warn"},
             {"label": "Non-approved substitutes", "value": f"{int((T['SKUSubstitute']['approval_status'] != 'APPROVED').sum()):,}", "tone": "info"}])
    if f.empty:
        ui.empty("No data-quality findings.", "All inputs passed the gate.")
    else:
        a, b = st.columns(2)
        with a:
            ui.show_chart(ui.bar(f.groupby("issue_type").size().rename("findings").reset_index(), "findings", "issue_type", title="Findings by type"))
        with b:
            ui.show_chart(ui.bar(f.groupby("issue_type")["impact_qty"].sum().fillna(0).rename("impact_units").reset_index(), "impact_units", "issue_type", title="Impact (units)"))
        typ = st.multiselect("Issue type", sorted(f["issue_type"].unique()))
        v = f[f["issue_type"].isin(typ)] if typ else f
        ui.show_df(v[["finding_id", "issue_type", "entity", "record_id", "related_record_ids", "impact_qty", "detail"]], height=340)
    st.subheader("Supplier capacity ledger - exceedances")
    ex = led[led["status"] == "EXCEEDED"]
    ui.show_df(ex[["supplier_id", "product_family", "week_start_date", "committed_qty", "capacity_qty", "utilisation_pct"]]) if len(ex) else ui.empty("No supplier is over capacity.")
    st.subheader("Validation suite results")
    p = c.ds["dir"] / "docs" / "validation_checks.csv"
    if p.exists():
        vc = pd.read_csv(p)
        g = vc.groupby(["category", "status"]).size().unstack(fill_value=0).reset_index()
        ui.show_df(g)
        st.caption(f"{len(vc)} automated checks; unexpected failures: {int((vc['status'] == 'FAIL').sum())}. Labelled checks fail only on injected, ground-truth-labelled rows (ground truth itself is not loaded by this application).")
    else:
        ui.empty("Validation results not found for this dataset.")


# ======================================================================== Scenarios
def page_scenarios(c):
    out, T = c.ds["out"], c.ds["T"]
    ui.title("What-if scenario simulator", "Change demand, lead times, supplier capacity and transport delays, then recompute with the planning engine. The baseline is never modified.")
    size = len(T["ForecastDemand"])
    if size > 300_000:
        st.warning("Full dataset: each scenario run recomputes ~765k projected-balance rows and takes roughly 20-40 seconds.")
    with st.form("scn"):
        a, b, d = st.columns(3)
        name = a.text_input("Scenario name", "My scenario")
        dm = a.slider("Demand change (%)", -50, 100, 0, 5)
        fam = a.selectbox("Demand family", ["All"] + sorted(T["SKU"]["product_family"].unique()))
        lt = b.slider("Lead-time change (days)", -14, 60, 0)
        lts = b.selectbox("Lead-time supplier", ["All"] + sorted(T["Supplier"]["supplier_id"]))
        cf = b.slider("Supplier capacity change (%)", -80, 100, 0, 5)
        td = d.slider("Transport delay on shipped orders (days)", 0, 30, 0)
        scope = d.selectbox("Delay applies to", ["shipped", "all_open"])
        dis = d.multiselect("Disable suppliers", sorted(T["Supplier"]["supplier_id"]))
        go = st.form_submit_button("Run scenario", type="primary")
    if go:
        sc = Scenario(name=name, demand_multiplier=1 + dm / 100, demand_family=None if fam == "All" else fam, lead_time_delta_days=lt,
                      lead_time_supplier=None if lts == "All" else lts, capacity_factor=1 + cf / 100, transport_delay_days=td, transport_scope=scope, disabled_suppliers=dis)
        with st.spinner("Recomputing plan..."):
            res = simulate(T, out, sc, c.ds["policy"], c.ds["manifest"]["seed"])
        st.session_state["scn_res"] = {"key": c.key, "res": res}
        c.state.audit(c.user, "scenario.run", "scenario", name, {"dataset": c.key, "params": res["params"]})
    cur = st.session_state.get("scn_res")
    if not cur or cur["key"] != c.key:
        ui.empty("Configure a scenario above and press Run.", "Results appear here; saved scenarios are listed below.")
    else:
        res = cur["res"]
        st.markdown("**Scenario:** " + "; ".join(res["description"]) + "  " + ui.badge("baseline unchanged", "ok"), unsafe_allow_html=True)
        kp = res["kpis"]
        g = {r.metric: r for r in kp.itertuples()}
        ui.kpis([{"label": "Service level", "value": f"{g['service_level_pct'].scenario:.2f}%", "note": f"{g['service_level_pct'].delta:+.2f} pts vs baseline", "tone": "good" if g["service_level_pct"].delta >= 0 else "bad"},
                 {"label": "Shortages", "value": f"{g['shortages'].scenario:,.0f}", "note": f"{g['shortages'].delta:+,.0f}", "tone": "warn" if g["shortages"].delta > 0 else "good"},
                 {"label": "Units short", "value": f"{g['shortage_units'].scenario:,.0f}", "note": f"{g['shortage_units'].delta:+,.0f}"},
                 {"label": "Value at risk", "value": ui.money(g["value_at_risk"].scenario), "note": f"{g['value_at_risk'].delta:+,.0f}"},
                 {"label": "Recommended cost", "value": ui.money(g["recommended_cost"].scenario), "note": f"{g['recommended_cost'].delta:+,.0f}"}])
        a, b = st.columns(2)
        with a:
            ui.show_df(kp)
        with b:
            cnt = pd.DataFrame({"change": list(res["counts"]), "shortages": list(res["counts"].values())})
            ui.show_chart(ui.bar(cnt, "shortages", "change", title="Shortage changes vs baseline", sort=None))
        st.markdown("**Shortage-level differences**")
        ui.show_df(res["detail"].drop(columns=["k"]) if len(res["detail"]) else res["detail"], height=300)
        if c.state.can(c.user, "save_scenario") and st.button("Save scenario to audit history"):
            c.state.save_scenario(c.user, c.key, res["params"]["name"], res["params"], {"baseline": res["baseline"], "scenario": res["scenario"]})
            st.success("Saved.")
    sv = c.state.scenarios(c.key)
    if sv:
        st.subheader("Saved scenarios")
        ui.show_df(pd.DataFrame([{"id": s["id"], "saved": s["ts_utc"], "by": s["username"], "name": s["name"], "service_level_pct": json.loads(s["kpis"])["scenario"].get("service_level_pct"),
                                  "shortages": json.loads(s["kpis"])["scenario"].get("shortages")} for s in sv]))


# ======================================================================== Risk
def page_risk(c):
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Risk prediction", "Early-warning scores for shortages and supplier disruptions, with the factors behind every score")
    r = cache.get_risk(c.path)
    ui.kpis([{"label": "High risk (not yet short)", "value": f"{int(((r['band'] == 'HIGH') & ~r['already_short']).sum()):,}", "tone": "bad"},
             {"label": "Medium risk", "value": f"{int(((r['band'] == 'MEDIUM') & ~r['already_short']).sum()):,}", "tone": "warn"},
             {"label": "Already short (next 8 wks)", "value": f"{int(r['already_short'].sum()):,}", "tone": "info"}, {"label": "Scored SKU-locations", "value": f"{len(r):,}"}])
    f1, f2 = st.columns(2)
    band = f1.multiselect("Risk band", ["HIGH", "MEDIUM", "LOW"], default=["HIGH"])
    hide = f2.checkbox("Hide pairs that are already short", value=True)
    v = r[r["band"].isin(band)] if band else r
    if hide: v = v[~v["already_short"]]
    ui.show_df(v.head(500)[["sku_id", "location_id", "risk_score", "band", "top_factors", "already_short"]], height=300)
    if len(v):
        sel = st.selectbox("Explain a score", list(zip(v["sku_id"], v["location_id"]))[:500], format_func=lambda x: f"{x[0]} @ {x[1]}", key="risk_sel")
        row = r[(r["sku_id"] == sel[0]) & (r["location_id"] == sel[1])].iloc[0]
        ex = pd.DataFrame([{"factor": k, "value (0-1)": row[f"f_{k}"], "weight": w, "points": row[f"c_{k}"]} for k, w in risk.WEIGHTS.items()])
        a, b = st.columns(2)
        with a: ui.show_chart(ui.bar(ex, "points", "factor", title=f"Risk score {row['risk_score']:.1f} = sum of factor points", sort="-x"))
        with b: ui.show_df(ex)
    st.subheader("Supplier disruption risk")
    ui.show_df(risk.supplier_disruption_risk(T, cache.get_card(c.path)).head(20)[["supplier_id", "supplier_name", "supplier_status", "score", "base", "status_adj", "single_source_adj", "open_delay_adj", "disruption_risk", "band"]], height=300)
    st.subheader("Backtest")
    st.caption("Does the score rank the SKU-locations that become short under a stress scenario (demand +15% and +7 days transport delay in the first 8 weeks)? The score is never computed from the stress run.")
    if st.button("Run stress backtest"):
        with st.spinner("Re-running the planning engine under stress..."):
            bt = risk.stress_backtest(T, out, r, c.ds["policy"])
        st.json(bt)
        c.state.audit(c.user, "risk.backtest", "dataset", c.key, bt)


# ======================================================================== Optimizer
def page_optimizer(c):
    ui.title("Optimization engine", "Pick one mitigation per shortage to minimise cost under shared supplier, donor, substitute and production-hours capacity")
    floor = st.slider("Minimum service level for the cost-optimal plan (%)", 50, 100, 95)
    if st.button("Optimise", type="primary") or st.session_state.get("opt_key") == (c.key, floor):
        if st.session_state.get("opt_key") != (c.key, floor):
            with st.spinner("Solving..."):
                st.session_state["opt_res"] = optimize.run_strategies(c.ds["T"], c.ds["out"], c.ds["policy"], float(floor))
                st.session_state["opt_key"] = (c.key, floor)
            c.state.audit(c.user, "optimizer.run", "dataset", c.key, {"floor": floor})
        r = st.session_state["opt_res"]
        t = r["table"]
        if t.empty:
            ui.empty("No shortages to optimise.")
            return
        ui.show_df(t.drop(columns=["option_mix", "note"]), height=200)
        for n_ in t["note"][t["note"] != ""]:
            st.warning(n_)
        a, b = st.columns(2)
        with a: ui.show_chart(ui.bar(t, "total_cost", "strategy", title="Total cost (action + uncovered demand)"))
        with b: ui.show_chart(ui.bar(t, "service_pct", "strategy", title="Service level (%)", sort=None))
        st.markdown("**Constraint check:** every strategy except the engine ranking is verified to respect all shared-capacity constraints (violations column = 0).")
        pick = st.selectbox("Inspect plan", list(r["selections"]))
        sel = r["candidates"].iloc[r["selections"][pick]]
        ui.show_df(sel[["shortage_id", "mitigation_id", "option_type", "supplier_id", "qty", "covered_qty", "fill_rate_pct", "total_cost", "unmet_cost", "J"]].rename(columns={"J": "objective"}), height=300)
        st.download_button("Download selected plan (CSV)", sel[["shortage_id", "mitigation_id", "option_type", "supplier_id", "qty", "covered_qty", "fill_rate_pct", "total_cost"]].to_csv(index=False), "optimised_plan.csv", "text/csv")
    else:
        ui.empty("Press Optimise to compare strategies.", "Engine ranking (service first) vs. minimum cost vs. cost-optimal with a service floor vs. maximum service.")


# ======================================================================== AI assistant
def page_assistant(c):
    ui.title("AI planning assistant", "Answers are built from the loaded data and checked: unknown IDs are refused, every number must come from a data lookup, recommendations are re-validated")
    ctx = cache.get_ctx(c.path)
    use_llm = False
    if llm_available():
        use_llm = st.toggle("Rephrase with the LLM (grounding-checked)", value=False)
    else:
        st.caption("Deterministic grounded mode (no LLM key configured). Set ANTHROPIC_API_KEY and install `anthropic` to enable optional rephrasing.")
    hist = st.session_state.setdefault("chat", [])
    sugg = ["Give me an overview of the plan", "Which suppliers are problematic?", "Which locations have the most shortage problems?", "Which SKU-locations are at risk of shortage?",
            "What if demand increases by 20%?"]
    top = c.ds["out"]["Shortage"].sort_values("priority_rank")["shortage_id"]
    if len(top):
        sugg += [f"Why does {top.iloc[0]} happen?", f"What should we do about {top.iloc[0]}?"]
    cols = st.columns(3)
    for i, s in enumerate(sugg):
        if cols[i % 3].button(s, key=f"sg{i}"):
            st.session_state["pending_q"] = s
    q = st.chat_input("Ask about shortages, suppliers, locations, risks or what-if scenarios")
    q = q or st.session_state.pop("pending_q", None)
    if q:
        with st.spinner("Checking the data..."):
            a = ask(ctx, q, use_llm, history=[m["a"] for m in hist if m.get("key") == c.key])  # follow-ups resolve against earlier answers
        hist.append({"q": q, "a": a, "key": c.key})
        c.state.audit(c.user, "assistant.question", "assistant", a.kind, {"q": q[:300], "grounded": a.grounded, "not_covered": len(a.not_covered)})
    for m in hist[-12:]:
        with st.chat_message("user"):
            st.write(m["q"])
        with st.chat_message("assistant"):
            st.markdown(m["a"].text)
            tag = ui.badge("grounded", "ok") if m["a"].grounded else ui.badge("ungrounded: " + ", ".join(m["a"].ungrounded[:4]), "bad")
            extra = ui.badge(f"{len(m['a'].not_covered)} part(s) not answered", "warn") if getattr(m["a"], "not_covered", None) else ""
            st.markdown(f"{tag} {ui.badge(m['a'].kind, 'info')} {extra}", unsafe_allow_html=True)
            if m["a"].checks:
                with st.expander(f"Verification checks ({sum(1 for x in m['a'].checks if x['ok'])}/{len(m['a'].checks)} passed)"):
                    st.dataframe(pd.DataFrame(m["a"].checks), hide_index=True)
    if not hist:
        st.info(CAPS)


# ======================================================================== Decision room
VERDICT_TONE = {"RESOLVED": "ok", "NO GAP": "ok", "REDUCED": "warn", "UNCHANGED": "bad", "WORSE": "bad"}


def page_decision(c):
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Decision room", "From a shortage to a verified, approved decision. Every option is applied to a copy of the data and the planning engine is "
             "re-run, so you see what really happens - not just the engine's estimate.")
    sh = out["Shortage"].sort_values("priority_rank")
    if sh.empty:
        ui.empty("No shortages to decide on.")
        return
    ids = list(sh["shortage_id"])
    sid = st.selectbox("Shortage (highest priority first)", ids, key="dr_sid",
                       format_func=lambda x: (lambda r: f"#{r['priority_rank']}  {x}  -  {r['sku_id']} @ {r['location_id']}  -  {r['shortage_qty']:,} units from {r['first_short_week']}")(sh.set_index("shortage_id").loc[x]))
    s = sh.set_index("shortage_id").loc[sid]
    ev = decision.evidence(T, out, sid)

    st.markdown("#### 1 - The problem")
    ui.kpis([{"label": "Gap below safety stock", "value": f"{s['shortage_qty']:,}", "note": f"units, {s['shortage_type'].replace('_', ' ').lower()}", "tone": "bad"},
             {"label": "Needed by", "value": s["first_short_week"], "note": f"{s['need_by_date']} - lasts {s['episode_weeks']} week(s)", "tone": "warn"},
             {"label": "Value at risk", "value": ui.money(s["value_at_risk"]), "note": f"priority #{s['priority_rank']} (score {s['priority_score']:.1f})", "tone": "warn"},
             {"label": "Status", "value": s["status"].replace("_", " ").title(), "note": f"data-quality flag: {s['data_quality_flag']}", "tone": "info"}])
    pb = out["ProjectedBalance"]
    d = pb[(pb["sku_id"] == s["sku_id"]) & (pb["location_id"] == s["location_id"])].sort_values("week_start_date")
    ui.show_chart(ui.line(d[["iso_week", "closing_qty", "safety_stock_qty"]].melt("iso_week", var_name="series", value_name="units"), "iso_week", "units",
                          color="series", title=f"Projected balance today - {s['sku_id']} @ {s['location_id']}", rule=0, height=260))

    st.markdown("#### 2 - Why it happens")
    ui.show_df(ev["causes"][["cause_code", "contribution_qty", "source_table", "source_id", "explanation"]], height=180)
    with st.expander("Source records behind these causes"):
        for label, key, cols in (("Purchase orders", "purchase_orders", ["po_id", "supplier_id", "status", "requested_date", "promised_date", "eta_date", "qty_base"]),
                                 ("Order events", "po_events", ["po_id", "event_type", "event_date", "to_status", "delay_days", "reason_code"]),
                                 ("Transport events", "transport_events", ["po_id", "carrier_id", "event_type", "event_date", "delay_days", "reason_code"]),
                                 ("Forecast rows", "forecast_rows", ["demand_id", "forecast_qty", "demand_driver"]),
                                 ("Production plans", "production_plans", ["production_plan_id", "iso_week", "planned_qty", "status"]),
                                 ("Inventory snapshot", "inventory", ["inventory_id", "on_hand_qty", "allocated_qty", "available_qty", "safety_stock_qty"]),
                                 ("Data-quality findings", "findings", ["finding_id", "issue_type", "record_id", "detail"])):
            if len(ev[key]):
                st.markdown(f"**{label}**")
                ui.show_df(ev[key][cols])

    st.markdown("#### 3 - Verify the options with the planning engine")
    big = len(T["ForecastDemand"]) > 300_000
    n = st.slider("Options to verify (engine rank order, plus the do-nothing backorder)", 1, 6, 3 if big else 4, key="dr_n")
    if big:
        st.caption("Full dataset: each option re-runs the whole plan (about 15 seconds per option).")
    key = ("dr", c.key, sid, n)
    if st.button("Verify options", type="primary", key="dr_run"):
        with st.spinner("Applying each option to a copy of the data and re-running the planning engine..."):
            st.session_state[key] = decision.decision_matrix(T, out, c.ds["policy"], sid, n, c.ds["manifest"]["seed"])
        m = st.session_state[key]
        c.state.audit(c.user, "decision.verified", "shortage", sid, {"dataset": c.key, "best": m["best"], "engine_pick": m["engine_pick"],
                                                                    "options": list(m["table"]["mitigation_id"]) if len(m["table"]) else []})
    m = st.session_state.get(key)
    if not m:
        ui.empty("Press Verify options.", "Each option is applied to a copy of the data and the plan is recomputed; the baseline never changes.")
        return
    t = m["table"]
    if t.empty:
        ui.empty("This shortage has no recommendable options to verify.")
        return
    agree = ui.badge("engine recommendation confirmed", "ok") if m["agrees"] else ui.badge(f"verified best differs from the engine pick ({m['engine_pick']})", "warn")
    st.markdown(f"Verified best: **{m['best']}** {agree}", unsafe_allow_html=True)
    ui.show_df(t[["verified_rank", "mitigation_id", "option_type", "verdict", "gap_before", "gap_after", "gap_closed_pct", "engine_fill_pct", "engine_cost",
                  "side_effect_shortages", "side_effect_units", "service_level_delta", "approval_role", "action"]], height=230)
    st.caption("Engine estimate = fill rate and incremental cost computed when the plan was made. Verified = outcome after re-running the plan with the option applied. "
               "Ranking: gap closed, then fewest side-effect shortage units, then lowest cost.")

    st.markdown("#### 4 - Before vs. after")
    opts = list(t["mitigation_id"])
    mid = st.selectbox("Option", opts, index=opts.index(m["best"]), key="dr_mid",
                       format_func=lambda x: f"{x}  -  {t.set_index('mitigation_id').at[x, 'option_type']}  -  {t.set_index('mitigation_id').at[x, 'verdict']}")
    r = m["results"][mid]
    ui.kpis([{"label": "Gap over the shortage weeks", "value": f"{r['gap_before']:,} -> {r['gap_after']:,}", "note": f"{r['window'][0]}-{r['window'][1]} - {r['gap_closed_pct']:.1f}% closed",
              "tone": VERDICT_TONE.get(r["verdict"], "info").replace("ok", "good")},
             {"label": "Verdict", "value": r["verdict"].title(), "note": f"stock-out weeks {r['stockout_weeks_before']} -> {r['stockout_weeks_after']}", "tone": "info"},
             {"label": "Side effects elsewhere", "value": f"{len(r['side_effects'])}", "note": f"new/worse shortages, {r['side_effect_units']:,} units", "tone": "bad" if len(r["side_effects"]) else "good"},
             {"label": "Network change", "value": f"{r['shortage_units_delta']:+,} units", "note": f"service level {r['service_level_delta']:+.3f} pts", "tone": "info"},
             {"label": "Incremental cost", "value": ui.money(r["engine_cost"]), "note": f"approval by {r['approval_role'].replace('_', ' ').title()}", "tone": "info"}])
    import altair as alt
    a, b = r["series_before"].assign(plan="before"), r["series_after"].assign(plan="after")
    last = min(52, W.week_of(s["need_by_date"]) + int(s["episode_weeks"]) + 6)
    both = pd.concat([a.head(last), b.head(last)])[["iso_week", "closing_qty", "plan"]]
    ss_v = float(a["safety_stock_qty"].iloc[0])
    lines = alt.Chart(both, title=f"Projected balance, weeks 1-{last}: {r['description']}").mark_line(point=True, strokeWidth=2.4).encode(
        x=alt.X("iso_week:N", title=None), y=alt.Y("closing_qty:Q", title="projected balance (units)"),
        color=alt.Color("plan:N", scale=alt.Scale(domain=["before", "after"], range=["#94A3B8", ui.PALETTE["primary"]]), legend=alt.Legend(orient="bottom")),
        strokeDash=alt.StrokeDash("plan:N", scale=alt.Scale(domain=["before", "after"], range=[[6, 4], [1, 0]]), legend=None),
        tooltip=["iso_week", "plan", "closing_qty"])
    rule = alt.Chart(pd.DataFrame({"y": [ss_v]})).mark_rule(color=ui.PALETTE["red"], strokeDash=[5, 4]).encode(y="y:Q")
    ui.show_chart((lines + rule).properties(height=280))
    st.caption("Grey dashed = before, solid = after re-planning, red dashed = safety stock.")
    if r["capacity"]:
        cb, ca = r["capacity"]["before"], r["capacity"]["after"]
        st.markdown(f"**Supplier capacity** - {r['capacity']['supplier_id']} / {r['capacity']['product_family']}, order week {r['capacity']['week']}: "
                    f"{cb[1]:,} -> {ca[1]:,} units committed of {ca[2] if ca[2] is not None else 'n/a'} ({cb[0]:.1f}% -> {ca[0]:.1f}%).")
    if len(r["side_effects"]):
        st.markdown("**Side effects elsewhere in the network**")
        ui.show_df(r["side_effects"])
    st.markdown("**Assumptions:** " + "; ".join(r["assumptions"]) + ".")

    st.markdown("#### 5 - Decide")
    ctx = cache.get_ctx(c.path)
    checks = validate_option(ctx, mid) + [{"check": "re-plan: target gap not made worse", "ok": r["gap_after"] <= r["gap_before"], "detail": f"{r['gap_before']} -> {r['gap_after']}"},
                                          {"check": "re-plan: no new shortages elsewhere", "ok": len(r["side_effects"]) == 0, "detail": f"{len(r['side_effects'])} side effect(s)"}]
    ui.show_df(pd.DataFrame(checks), height=200)
    passed = all(x["ok"] for x in checks)
    cur = c.state.status_of(c.key, "mitigation", mid)
    st.caption(f"Decision status: {cur or 'not yet decided'}")
    can = c.state.can(c.user, "decide_mitigation") and (r["approval_role"] != "OPS_MANAGER" or c.state.can(c.user, "decide_high_value"))
    note = st.text_input("Decision note", key="dr_note", placeholder="Required for rejection")
    b1, b2, b3 = st.columns([1, 1, 2])
    summary = {"dataset": c.key, "shortage": sid, "verdict": r["verdict"], "gap_before": r["gap_before"], "gap_after": r["gap_after"],
               "side_effects": len(r["side_effects"]), "service_level_delta": r["service_level_delta"], "checks_passed": passed}
    if b1.button("Approve", key="dr_ok", disabled=not (can and passed and cur not in ("APPROVED",))):
        try:
            c.state.audit(c.user, "decision.evidence", "mitigation", mid, summary)
            if cur is None:
                c.state.transition(c.user, c.key, "mitigation", mid, "PROPOSED", "", "decide_mitigation")
            c.state.transition(c.user, c.key, "mitigation", mid, "APPROVED", note, "decide_mitigation")
            st.success("Approved. The verified evidence and the decision are in the audit history.")
        except Exception as e:
            st.error(str(e))
    if b2.button("Reject", key="dr_no", disabled=not (c.state.can(c.user, "decide_mitigation") and cur not in ("APPROVED", "REJECTED"))):
        try:
            if cur is None:
                c.state.transition(c.user, c.key, "mitigation", mid, "PROPOSED", "", "decide_mitigation")
            c.state.transition(c.user, c.key, "mitigation", mid, "REJECTED", note, "decide_mitigation")
            st.warning("Rejected and logged.")
        except Exception as e:
            st.error(str(e))
    if not passed:
        st.caption("Approval is disabled because at least one check failed.")
    elif not can:
        st.caption("Your role cannot approve this option" + (" (above the spend threshold: Ops manager approval required)." if r["approval_role"] == "OPS_MANAGER" else "."))
    md = decision.case_file(T, out, c.ds["policy"], sid, m, mid, checks, c.ds["as_of"])
    b3.download_button("Download case file (Markdown)", md, f"case_{sid}_{mid}.md", "text/markdown", key="dr_dl",
                       on_click=lambda: c.state.audit(c.user, "export.download", "file", f"case_{sid}_{mid}.md", {"dataset": c.key}))


# ======================================================================== Multi-shortage recovery planner
def _recovery_md(res: dict, sids: list, key: str, as_of: str) -> str:
    t = res["comparison"]
    co = res["results"]["Coordinated plan"]
    ex = res["explanation"]
    L = [f"# Coordinated recovery plan - {key}", "", f"As of {as_of}. Shortages: {', '.join(sids)}.", "",
         "## Plans compared (each verified by re-running the planning engine)", decision._md(t, list(t.columns)), "",
         "## Coordinated plan - verified outcome per shortage", decision._md(co["per_shortage"], ["shortage_id", "mitigation_id", "option_type", "gap_before", "gap_after", "verdict", "action_cost"]), "",
         "## Actions", "\n".join(f"- {a}" for a in co["actions"]), "",
         "## Shared resources used", decision._md(res["usage"]["Coordinated plan"], ["resource", "used", "capacity", "shortages", "over"]), "",
         "## Why each action was selected / rejected", decision._md(ex, ["shortage_id", "mitigation_id", "option_type", "decision", "objective", "reason"]), "",
         "## Side effects of the coordinated plan", decision._md(co["side_effects"], ["sku_id", "location_id", "first_short_week", "shortage_qty", "change"]) if len(co["side_effects"]) else "_none_", ""]
    return "\n".join(L) + "\n"


def page_recovery(c):
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Multi-shortage recovery planner", "Pick several shortages; ORYVA chooses one action per shortage so that, together, they respect shared supplier capacity, "
             "donor stock, substitute stock and production hours - then re-runs the planning engine on the combined plan to verify it.")
    sh = out["Shortage"].sort_values("priority_rank")
    if sh.empty:
        ui.empty("No shortages to recover.")
        return
    conf = cache.get_conflicts(c.path)
    st.markdown("#### 1 - Choose shortages")
    if len(conf):
        st.caption("Groups whose individually-best actions compete for the same resource (computed from the data):")
        ui.show_df(conf.assign(shortages=conf["shortages"].map(lambda x: ", ".join(x)))[["resource", "n", "demand", "capacity", "shortages"]], height=180)
        g = st.selectbox("Start from a conflict group", list(range(len(conf))), format_func=lambda i: f"{conf.at[i, 'n']} shortages - {conf.at[i, 'resource']}", key="rp_group")
        default = list(conf.at[g, "shortages"])
    else:
        st.caption("No shortages in this plan compete for the same resource; you can still coordinate any selection.")
        default = list(sh["shortage_id"].head(5))
    picks = st.multiselect("Shortages to recover together", list(sh["shortage_id"]), default=default, key=f"rp_sel_{'-'.join(default)}", max_selections=25)
    big = len(T["ForecastDemand"]) > 300_000
    compare_all = st.checkbox("Also verify the independent and engine one-by-one plans for comparison", value=True, key="rp_cmp")
    st.caption(f"Each plan is verified by one full re-plan ({'about 15 s each on the full dataset' if big else 'about half a second each'}).")
    key = ("rp", c.key, tuple(sorted(picks)), compare_all)
    if st.button("Build & verify recovery plan", type="primary", key="rp_run", disabled=len(picks) < 1):
        try:
            with st.spinner("Selecting a jointly-feasible set of actions and re-running the planning engine..."):
                st.session_state[key] = recovery.plan_recovery(T, out, c.ds["policy"], picks, c.ds["manifest"]["seed"], compare_all)
            r0 = st.session_state[key]
            c.state.audit(c.user, "recovery.verified", "recovery_plan", ",".join(sorted(picks))[:200], {"dataset": c.key, "summary": r0["results"]["Coordinated plan"]["summary"],
                                                                                                        "plan": r0["plans"]["Coordinated plan"]})
        except ValueError as e:
            st.error(str(e))
    res = st.session_state.get(key)
    if not res:
        ui.empty("Choose shortages and press Build & verify.", "Results come from re-running the plan, not from adding up per-option estimates.")
        return
    co = res["results"]["Coordinated plan"]["summary"]
    t = res["comparison"]
    cur = t.iloc[0]
    st.markdown("#### 2 - Verified result")
    ui.kpis([{"label": "Shortages resolved", "value": f"{co['resolved']} / {co['targets']}", "note": f"{co['reduced']} reduced, {co['unchanged'] + co['worse']} not improved", "tone": "good" if co["resolved"] == co["targets"] else "warn"},
             {"label": "Gap below safety stock", "value": f"{co['gap_before']:,} -> {co['gap_after']:,}", "note": "units across the selected shortages", "tone": "info"},
             {"label": "Total cost", "value": ui.money(co["total_cost"]), "note": f"vs {ui.money(cur['total_cost'])} doing nothing (action + remaining backorder)", "tone": "good"},
             {"label": "Side effects elsewhere", "value": f"{co['side_effect_shortages']}", "note": f"new/worse shortages, {co['side_effect_units']:,} units", "tone": "bad" if co["side_effect_shortages"] else "good"},
             {"label": "Service level", "value": f"{co['service_level_delta']:+.3f} pts", "note": f"network shortage units {co['network_shortage_units_delta']:+,}", "tone": "info"}])
    st.markdown("**Plans compared** (all verified by recalculation; shared-resource violations = actions that individually fit but together exceed a limit)")
    ui.show_df(t[["plan", "resolved", "reduced", "unchanged", "worse", "gap_after", "action_cost", "residual_backorder_cost", "total_cost", "side_effect_shortages",
                  "side_effect_units", "new_capacity_exceedances", "shared_resource_violations", "service_level_delta"]], height=210)
    a, b = st.columns(2)
    with a:
        ui.show_chart(ui.bar(t.dropna(subset=["total_cost"]), "total_cost", "plan", title="Total cost (action + remaining backorder)", sort=None))
    with b:
        ui.show_chart(ui.bar(t, "side_effect_units", "plan", title="Units of new/worse shortages elsewhere", sort=None))
    ind = res["results"].get("Independent best picks")
    if ind is not None:
        u = res["usage"]["Independent best picks"]
        if len(u) and u["over"].any():
            st.warning("Picking each shortage's best action on its own over-uses: " + "; ".join(f"{r.resource} ({r.used:,.0f} needed, {r.capacity:,.0f} available)" for r in u[u["over"]].itertuples())
                       + (f". Re-planning shows {ind['summary']['side_effect_shortages']} new/worse shortage(s) elsewhere ({ind['summary']['side_effect_units']:,} units)." if ind["summary"]["side_effect_shortages"] else "."))
    st.markdown("#### 3 - The coordinated actions and why")
    per = res["results"]["Coordinated plan"]["per_shortage"]
    ex = res["explanation"]
    sel = ex[ex["decision"] == "SELECTED"].set_index("shortage_id")["reason"]
    ui.show_df(per.assign(reason=per["shortage_id"].map(sel))[["shortage_id", "sku_id", "location_id", "option_type", "mitigation_id", "gap_before", "gap_after", "verdict", "action_cost", "reason"]], height=260)
    st.markdown("**Actions applied in the verification run:**\n" + "\n".join(f"- {x}" for x in res["results"]["Coordinated plan"]["actions"]))
    with st.expander("Rejected alternatives and why"):
        ui.show_df(ex[ex["decision"] != "SELECTED"][["shortage_id", "mitigation_id", "option_type", "objective", "reason"]], height=300)
    with st.expander("Shared resources used by each plan"):
        for name, u in res["usage"].items():
            st.markdown(f"**{name}**")
            ui.show_df(u.drop(columns=["res_key"]) if len(u) else u)
    se = res["results"]["Coordinated plan"]["side_effects"]
    if len(se):
        st.markdown("**Side effects of the coordinated plan** (found by the verification run)")
        ui.show_df(se)
    st.markdown("#### 4 - Decide")
    mo = out["MitigationOption"].set_index("mitigation_id")
    chosen = list(res["plans"]["Coordinated plan"].values())
    need_ops = any(mo.at[m, "approval_required_role"] == "OPS_MANAGER" for m in chosen)
    can = c.state.can(c.user, "decide_mitigation") and (not need_ops or c.state.can(c.user, "decide_high_value"))
    violations = int(t[t["plan"] == "Coordinated plan"]["shared_resource_violations"].iloc[0])
    note = st.text_input("Decision note", key="rp_note", placeholder="Required when the verification found side effects")
    ok_note = co["side_effect_shortages"] == 0 or bool(note.strip())
    b1, b2 = st.columns([1, 2])
    if b1.button("Approve coordinated plan", key="rp_ok", disabled=not (can and violations == 0 and ok_note)):
        try:
            c.state.audit(c.user, "recovery.approved", "recovery_plan", ",".join(sorted(picks))[:200], {"dataset": c.key, "summary": co, "plan": res["plans"]["Coordinated plan"], "note": note})
            for m in chosen:
                s_ = c.state.status_of(c.key, "mitigation", m)
                if s_ == "APPROVED":
                    continue
                if s_ in (None, "REJECTED"):
                    c.state.transition(c.user, c.key, "mitigation", m, "PROPOSED", "", "decide_mitigation")
                c.state.transition(c.user, c.key, "mitigation", m, "APPROVED", note or "coordinated recovery plan", "decide_mitigation")
            st.success(f"Approved {len(chosen)} action(s); each decision and the verified plan summary are in the audit history.")
        except Exception as e:
            st.error(str(e))
    if not can:
        b2.caption("Your role cannot approve this plan" + (" (contains actions above the spend threshold: Ops manager approval required)." if need_ops else "."))
    elif not ok_note:
        b2.caption("Add a note: the verification found side effects elsewhere.")
    md = _recovery_md(res, sorted(picks), c.key, c.ds["as_of"])
    st.download_button("Download recovery plan (Markdown)", md, "recovery_plan.md", "text/markdown", key="rp_dl",
                       on_click=lambda: c.state.audit(c.user, "export.download", "file", "recovery_plan.md", {"dataset": c.key}))


# ======================================================================== Supplier failure stress test
def page_stress(c):
    from ..advanced import stress
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Supplier failure stress test", "Which single supplier failure would hurt us most, how soon, and are we prepared? Each failure is simulated "
             "on a copy of the data and the planning engine is re-run - the ranking comes from verified impact, not from a risk score.")
    big = len(T["ForecastDemand"]) > 300_000
    a, b = st.columns(2)
    ow = a.selectbox("Outage length", [4, 8, 13, 26, "rest of horizon"], index=1, key="st_ow",
                     format_func=lambda x: f"{x} weeks" if isinstance(x, int) else "rest of the horizon (supplier lost)")
    k = b.slider("Suppliers to test (largest unshipped order volume first)", 3, min(50, len(T["Supplier"])), 4 if big else 15, key="st_k")
    st.caption("A failed supplier loses its unshipped orders (planned / confirmed) due in the outage window and cannot be used for mitigation; "
               f"shipments already in transit still arrive. {'About 15 s per supplier on the full dataset.' if big else 'About half a second per supplier.'}")
    key = ("st", c.key, ow, k)
    if st.button("Run stress test", type="primary", key="st_run"):
        with st.spinner("Failing each supplier in turn and re-running the planning engine..."):
            st.session_state[key] = stress.stress_test(T, out, c.ds["policy"], k, None if ow == "rest of horizon" else ow, c.ds["manifest"]["seed"])
        r0 = st.session_state[key]
        c.state.audit(c.user, "stress.run", "dataset", c.key, {"outage_weeks": ow, "suppliers": r0["screened"], "rank_correlation": r0["rank_correlation"]})
    r = st.session_state.get(key)
    if not r:
        ui.empty("Press Run stress test.", "Nothing is changed: every failure is simulated on a copy of the data.")
        return
    t = r["table"]
    if t.empty:
        ui.empty("No supplier has unshipped orders to fail.")
        return
    w = t.iloc[0]
    ui.kpis([{"label": f"Most critical of {len(r['screened'])} tested (of {r['total_suppliers']})", "value": w["supplier_id"], "note": f"risk score calls it {w['heuristic_band']} (rank #{w['heuristic_risk_rank']})", "tone": "bad"},
             {"label": "If it fails", "value": f"{w['new_shortages'] + w['worse_shortages']} shortages", "note": f"{w['shortage_units_delta']:+,} units, first hit {w['first_impact_week']}", "tone": "bad"},
             {"label": "Added value at risk", "value": ui.money(w["value_at_risk_delta"]), "note": f"sales value of extra shortfall below safety stock (not a guaranteed loss); service level {w['service_level_delta']:+.2f} pts", "tone": "warn"},
             {"label": "Prepared?", "value": f"{w['fully_recoverable']} / {w['new_shortages'] + w['worse_shortages']}", "note": f"fully recoverable; {w['single_sourced_affected']} affected SKU(s) single-sourced", "tone": "warn"},
             {"label": "Risk score vs impact", "value": "n/a" if r["rank_correlation"] is None else f"{r['rank_correlation']:+.2f}", "note": "rank correlation (1 = risk score predicts impact)", "tone": "info"}])
    if len(r["blind_spots"]):
        st.warning("Blind spots: " + ", ".join(f"{x.supplier_id} (impact #{x.impact_rank}, risk score says {x.heuristic_band})" for x in r["blind_spots"].itertuples())
                   + " - high-impact suppliers that the heuristic risk score does not flag as HIGH.")
    ui.show_df(t[["impact_rank", "supplier_id", "orders_cancelled", "units_lost", "new_shortages", "worse_shortages", "shortage_units_delta", "value_at_risk_delta",
                  "service_level_delta", "first_impact_week", "fully_recoverable", "partly_recoverable", "unrecoverable", "single_sourced_affected",
                  "supplier_score", "heuristic_risk_rank", "heuristic_band"]], height=300)
    ui.show_chart(ui.scatter(t.assign(label=t["supplier_id"]), "heuristic_risk_rank", "shortage_units_delta", "heuristic_band", "value_at_risk_delta",
                             title="Heuristic risk rank (1 = riskiest) vs verified shortage impact"))
    st.markdown("#### Drill into a supplier")
    sid = st.selectbox("Supplier", list(t["supplier_id"]), key="st_sid")
    d = r["results"][sid]
    st.markdown(f"**Shortages created or worsened if {sid} fails** (from the re-planned outputs)")
    ui.show_df(d["affected"], height=240)
    sole = d["single_sourced_list"]
    if sole:
        st.markdown(f"**Hedge: {len(sole)} SKU(s) have no approved supplier other than {sid}.** Active suppliers already serving the same product family, "
                    "with spare capacity this week - candidates to qualify as a second source (not approved for these SKUs today):")
        ui.show_df(stress.hedge_candidates(T, out, sid, sole[:10]), height=240)
    else:
        st.caption(f"Every SKU sourced from {sid} has at least one other approved supplier.")


# ======================================================================== Reports & exports
def page_reports(c):
    out, T = c.ds["out"], c.ds["T"]
    ui.title("Reports & exports", "Download planning outputs; every export is recorded in the audit history")
    k = _kp(c)
    prop = cache.get_proposals(c.path)
    mo = out["MitigationOption"]
    exec_md = (f"# Executive summary - {c.key}\n\nAs of {c.ds['as_of']}.\n\n- Service level: **{k['service_level_pct']:.2f}%**\n- Shortages: **{k['shortages']:,}** ({k['stockouts']:,} stock-outs), "
               f"{k['shortage_units']:,} units, value at risk **{ui.money(k['value_at_risk'])}**\n- Recommended plan cost: **{ui.money(k['recommended_cost'])}** vs {ui.money(k['do_nothing_cost'])} if nothing is done; "
               f"mean fill rate {k['mean_fill_rate_pct']:.1f}%\n- Shortages needing data review: {k['needs_review']:,}\n- Data-quality findings: {len(out['DataQualityFinding']):,}\n")
    items = {
        "Executive summary (Markdown)": ("executive_summary.md", exec_md, "text/markdown"),
        "Shortages (CSV)": ("shortages.csv", out["Shortage"].to_csv(index=False), "text/csv"),
        "Recommended mitigations (CSV)": ("recommended_mitigations.csv", mo[mo["is_recommended"] == 1].to_csv(index=False), "text/csv"),
        "All mitigation options (CSV)": ("mitigation_options.csv", mo.to_csv(index=False), "text/csv"),
        "Supplier scorecard (CSV)": ("supplier_scorecard.csv", cache.get_card(c.path).to_csv(index=False), "text/csv"),
        "Replenishment proposals (CSV)": ("replenishment_proposals.csv", prop.to_csv(index=False), "text/csv"),
        "Data-quality findings (CSV)": ("data_quality_findings.csv", out["DataQualityFinding"].to_csv(index=False), "text/csv"),
        "Open purchase orders (CSV)": ("open_purchase_orders.csv", T["PurchaseOrder"][T["PurchaseOrder"]["status"].isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"])].to_csv(index=False), "text/csv"),
    }
    allowed = c.state.can(c.user, "export")
    if not allowed:
        st.warning("Your role cannot export data.")
    cols = st.columns(2)
    for i, (label, (fname, data, mime)) in enumerate(items.items()):
        with cols[i % 2]:
            st.download_button(f"Download {label}", data, fname, mime, disabled=not allowed, key=f"dl{i}",
                               on_click=lambda f=fname: c.state.audit(c.user, "export.download", "file", f, {"dataset": c.key}))
    st.subheader("Role-based decision & exception report")
    if st.button("Generate role report"):
        md = build_report(c.ds["dir"])
        st.session_state["role_report"] = md
    if "role_report" in st.session_state:
        st.markdown(st.session_state["role_report"])
        st.download_button("Download role report", st.session_state["role_report"], "role_report.md", "text/markdown", disabled=not allowed,
                           on_click=lambda: c.state.audit(c.user, "export.download", "file", "role_report.md", {"dataset": c.key}))
    st.subheader("Preview: executive summary")
    st.markdown(exec_md)


# ======================================================================== Audit history
def page_audit(c):
    T, out = c.ds["T"], c.ds["out"]
    ui.title("Audit history", "Application actions (tamper-evident hash chain), approval decisions, and the dataset's own event history")
    ok, n, bad = c.state.verify_chain()
    st.markdown(f"Audit-log integrity: {ui.badge('VERIFIED - ' + str(n) + ' entries', 'ok') if ok else ui.badge('TAMPERING DETECTED at entry ' + str(bad), 'bad')}", unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["Application audit log", "Approval decisions", "Dataset event history"])
    with t1:
        rows = pd.DataFrame(c.state.audit_rows(2000))
        if rows.empty:
            ui.empty("No application actions recorded yet.")
        else:
            a, b = st.columns(2)
            act = a.multiselect("Action", sorted(rows["action"].unique()))
            usr = b.multiselect("User", sorted(rows["username"].unique()))
            v = rows
            if act: v = v[v["action"].isin(act)]
            if usr: v = v[v["username"].isin(usr)]
            ui.show_df(v[["id", "ts_utc", "username", "role", "action", "entity_type", "entity_id", "details"]], height=340)
    with t2:
        d = pd.DataFrame(c.state.decision_history(c.key))
        ui.show_df(d) if len(d) else ui.empty("No approvals or rejections yet.")
    with t3:
        which = st.selectbox("Event table", ["ShortageEvent", "MitigationEvent", "PurchaseOrderEvent", "ProductionPlanEvent", "TransportEvent", "InventoryEvent"])
        ev = out[which] if which in out else T[which]
        q = st.text_input("Filter by ID contains", key="aud_q")
        idc = [col for col in ev.columns if col.endswith("_id") and col != "event_id"][0]
        v = ev[ev[idc].str.contains(q, case=False)] if q else ev
        st.caption(f"{len(v):,} of {len(ev):,} events (append-only history from the dataset)")
        ui.show_df(v.head(2000), height=380)


PAGES = [
    ("Overview", "Executive overview", page_overview), ("Inventory", "Inventory management", page_inventory), ("Demand", "Demand forecasting", page_demand),
    ("Suppliers", "Supplier intelligence", page_suppliers), ("Shortages", "Shortage detection", page_shortages), ("Decision room", "Decision room", page_decision), ("Recovery planner", "Multi-shortage recovery planner", page_recovery), ("Stress test", "Supplier failure stress test", page_stress), ("Mitigation", "Mitigation recommendations", page_mitigation),
    ("Purchase orders", "Purchase orders & replenishment", page_orders), ("Data quality", "Data quality & anomalies", page_quality), ("Scenarios", "What-if simulator", page_scenarios),
    ("Risk", "Risk prediction", page_risk), ("Optimizer", "Optimization engine", page_optimizer), ("AI assistant", "AI planning assistant", page_assistant),
    ("Reports", "Reports & exports", page_reports), ("Audit history", "Audit history", page_audit),
]
