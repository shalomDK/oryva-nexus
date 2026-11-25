"""Grounded planning assistant.

Every answer is assembled from tool results computed on the loaded tables (no free text facts).  Each answer is
post-checked by `verify_grounded`: every identifier must exist in the dataset and every number must come from the
facts registered by the tools.  Recommendations are re-validated against source tables (MOQ, multiples, capacity,
lead time, policy) with independent code paths before being presented.  An optional LLM can rephrase an answer
(`ANTHROPIC_API_KEY` + `anthropic` package) but its output is accepted only if it passes the same grounding check."""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import weeks as W
from . import replenish, risk, supplier_intel
from .scenario import Scenario, simulate

ID_RE = re.compile(r"(DQF-\d{6}|MIT-SHORT-2026-\d{6}-\d{2}|RPL-SHORT-2026-\d{6}-\d{2}|SHORT-2026-\d{6}|SKU-\d{6}|LOC-\d{3}|SUP-\d{4}|PO-2026-\d{6}|SCAP-\d{6}|WC-LOC-\d{3}-\d{2}|CAR-\d{2}|FAM-\d{2})")
NUM_RE = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*(?![\w])")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|20\d{2}W\d{2}")


@dataclass
class Answer:
    text: str
    kind: str = "info"
    facts: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    grounded: bool = True
    ungrounded: list = field(default_factory=list)
    nums: set = field(default_factory=set)
    not_covered: list = field(default_factory=list)


class Facts:
    """Registry: numbers can only enter an answer through `n()`, which records them."""
    def __init__(self):
        self.nums: set = set()

    def n(self, v, dec: int = 0) -> str:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "n/a"
        v = float(v)
        self.nums.add(round(v, dec))
        self.nums.add(round(v, 0))
        s = f"{v:,.{dec}f}"
        return s


def reg(f: Facts, text) -> None:
    """Register numbers contained in a data-derived string (names, engine explanations, validation details)."""
    for m in NUM_RE.findall(ID_RE.sub(" ", DATE_RE.sub(" ", str(text)))):
        try:
            v = float(m.replace(",", ""))
        except ValueError:
            continue
        f.nums.update({round(v, 0), round(v, 1), round(v, 2)})


def _tbl(df: pd.DataFrame, cols: list[str], f: Facts, dec: dict | None = None) -> str:
    dec = dec or {}
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    rows = []
    for r in df[cols].itertuples(index=False):
        cells = []
        for c, v in zip(cols, r):
            if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
                cells.append(f.n(v, dec.get(c, 0)))
            else:
                for m in NUM_RE.findall(ID_RE.sub(" ", DATE_RE.sub(" ", str(v)))):  # numbers inside data strings (e.g. names) are data
                    f.nums.add(round(float(m.replace(",", "")), 2))
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return head + "\n".join(rows)


def universe(ctx) -> set:
    T, out = ctx.T, ctx.out
    u = set()
    for t, c in (("SKU", "sku_id"), ("Location", "location_id"), ("Supplier", "supplier_id"), ("PurchaseOrder", "po_id"),
                 ("SupplierCapacity", "capacity_id"), ("WorkCenter", "work_center_id"), ("Carrier", "carrier_id")):
        u |= set(T[t][c])
    u |= set(T["SKU"]["product_family"])
    u |= set(out["Shortage"]["shortage_id"]) | set(out["MitigationOption"]["mitigation_id"])
    u |= {"RPL-" + m[4:] for m in out["MitigationOption"]["mitigation_id"]}
    u |= set(out["DataQualityFinding"]["finding_id"])
    return u


def verify_grounded(text: str, ctx, f: Facts) -> tuple[bool, list]:
    """Every id must exist in the data; every number must have been registered by a tool from the data."""
    bad = [i for i in ID_RE.findall(text) if i not in ctx.universe]
    scrubbed = ID_RE.sub(" ", DATE_RE.sub(" ", text))
    for m in NUM_RE.findall(scrubbed):
        try:
            v = float(m.replace(",", ""))
        except ValueError:
            continue
        if not any(abs(v - x) < 0.0051 or abs(round(v) - x) < 0.51 and float(m.replace(",", "")) == round(v) for x in f.nums):
            bad.append(m)
    return (not bad), bad


class Ctx:
    def __init__(self, T, out, policy, card=None):
        self.T, self.out, self.policy = T, out, policy
        self.as_of = str(T["Inventory"]["as_of_date"].iloc[0])
        self.card = card if card is not None else supplier_intel.scorecard(T, out)
        self._risk = None
        self.universe = universe(self)

    @property
    def risk(self):
        if self._risk is None:
            self._risk = risk.shortage_risk(self.T, self.out, self.card)
        return self._risk


# ------------------------------------------------------------------------------------ option validation
def validate_option(ctx: Ctx, mitigation_id: str) -> list[dict]:
    """Independent re-check of one mitigation against source tables (policy, lead time, capacity, MOQ/multiples)."""
    T, out, pol = ctx.T, ctx.out, ctx.policy
    mo = out["MitigationOption"].set_index("mitigation_id")
    o = mo.loc[mitigation_id]
    sh = out["Shortage"].set_index("shortage_id").loc[o["shortage_id"]]
    chk = []

    def add(name, ok, detail):
        chk.append({"check": name, "ok": bool(ok), "detail": detail})
    t = o["option_type"]
    pb = out["ProjectedBalance"]
    if t in ("NEW_PO", "ALT_SUPPLIER_PO"):
        p = {"sku_id": sh["sku_id"], "location_id": sh["location_id"], "supplier_id": o["supplier_id"], "qty_base": int(o["qty"]),
             "order_date": ctx.as_of, "lead_days": int(o["lead_days"]) if pd.notna(o["lead_days"]) else -1, "need_by_date": sh["need_by_date"]}
        chk += replenish.validate_proposal(p, T, out)
    elif t == "LOCATION_TRANSFER":
        d = pb[(pb["sku_id"] == sh["sku_id"]) & (pb["location_id"] == o["source_location_id"])]
        sur = int((d["closing_qty"] - d["safety_stock_qty"]).min())
        add("donor stays above safety stock", o["qty"] <= max(0, sur), f"transfer {int(o['qty'])} <= donor surplus {max(0, sur)}")
    elif t == "SUBSTITUTE_SKU":
        s = T["SKUSubstitute"]
        r = s[(s["sku_id"] == sh["sku_id"]) & (s["substitute_sku_id"] == o["alt_sku_id"])]
        ok = len(r) > 0 and (r["approval_status"] == "APPROVED").any() and (r["effective_from"] <= ctx.as_of).any()
        add("substitute approved and effective", ok, f"status={','.join(r['approval_status']) if len(r) else 'none'}")
    elif t == "EXPEDITE_PO":
        po = T["PurchaseOrder"].set_index("po_id").loc[o["ref_po_id"]]
        add("PO can be expedited", po["status"] in ("CONFIRMED", "IN_TRANSIT", "DELAYED"), f"PO status {po['status']}")
        add("premium within policy cap", pol["expedite_premium_pct"] <= pol["expedite_premium_cap_pct"], f"{pol['expedite_premium_pct']}% <= {pol['expedite_premium_cap_pct']}%")
    elif t == "PRODUCTION_REPLAN":
        w = W.week_of(o["earliest_arrival_date"])
        add("outside frozen horizon", w > pol["production_frozen_weeks"], f"week {w} > frozen {pol['production_frozen_weeks']}")
    add("engine policy check", o["policy_check"] == "PASS", str(o["policy_reason"] or "PASS"))
    add("lead time known", o["lead_time_check"] != "MISSING", str(o["lead_time_check"]))
    return chk


# ------------------------------------------------------------------------------------ tools / handlers
def explain_shortage(ctx: Ctx, sid: str) -> Answer:
    f = Facts()
    sh = ctx.out["Shortage"].set_index("shortage_id")
    if sid not in sh.index:
        return Answer(f"I could not find shortage {sid} in the loaded dataset.", "not_found")
    s = sh.loc[sid]
    cs = ctx.out["ShortageCause"].query("shortage_id == @sid")
    mo = ctx.out["MitigationOption"].query("shortage_id == @sid").sort_values("rank")
    pb = ctx.out["ProjectedBalance"].query("sku_id == @s.sku_id and location_id == @s.location_id").sort_values("week_start_date")
    w0 = W.week_of(s["need_by_date"])
    ctxrows = pb[(W.weeks_of(pb["week_start_date"]) >= max(1, w0 - 2)) & (W.weeks_of(pb["week_start_date"]) <= w0 + 2)]
    lines = [f"**{sid}** is a **{s['shortage_type']}** of **{f.n(s['shortage_qty'])}** units of {s['sku_id']} at {s['location_id']}, "
             f"starting {s['first_short_week']} and lasting {f.n(s['episode_weeks'])} week(s) (value at risk ${f.n(s['value_at_risk'], 2)}; "
             f"priority rank {f.n(s['priority_rank'])}, score {f.n(s['priority_score'], 2)}). Status: {s['status']}."]
    lines.append("\n**Why it happens (evidence from source records):**")
    for r in cs.itertuples():
        reg(f, r.explanation)  # engine-generated explanation strings embed data values (utilisation %, weeks, ...)
        lines.append(f"- {r.cause_code}: {f.n(r.contribution_qty)} units - {r.explanation} (source {r.source_table} {r.source_id})")
    lines.append("\n**Projected balance around the shortage:**\n" + _tbl(ctxrows.assign(week=ctxrows["iso_week"]), ["week", "opening_qty", "scheduled_receipts_qty", "production_receipts_qty", "gross_demand_qty", "closing_qty", "safety_stock_qty"], f))
    if s["data_quality_flag"] != "NONE":
        lines.append(f"\nData-quality flag: **{s['data_quality_flag']}**" + (" - mitigation requiring lead times is blocked until reviewed." if s["status"] == "NEEDS_REVIEW" else "."))
    rec = mo[mo["is_recommended"] == 1]
    if len(rec):
        r = rec.iloc[0]
        lines.append(f"\nRecommended action: **{r['option_type']}** ({r['mitigation_id']}) covering {f.n(r['covered_qty'])} units, fill {f.n(r['fill_rate_pct'], 2)}%, incremental cost ${f.n(r['total_cost'], 2)}.")
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "explain", {"shortage": sid}, [sid] + list(cs["source_id"]), [], ok, bad, f.nums)


def recommend(ctx: Ctx, sid: str) -> Answer:
    f = Facts()
    sh = ctx.out["Shortage"].set_index("shortage_id")
    if sid not in sh.index:
        return Answer(f"I could not find shortage {sid} in the loaded dataset.", "not_found")
    mo = ctx.out["MitigationOption"].query("shortage_id == @sid").sort_values("rank")
    rec = mo[mo["is_recommended"] == 1].iloc[0]
    chk = validate_option(ctx, rec["mitigation_id"])
    valid = all(c["ok"] for c in chk)
    alt = mo.head(5)
    lines = [f"Recommendation for **{sid}**: **{rec['option_type']}** ({rec['mitigation_id']})"
             + (f" via {rec['supplier_id']}" if pd.notna(rec["supplier_id"]) else "") + f" - quantity {f.n(rec['qty'])}, covers {f.n(rec['covered_qty'])} of {f.n(sh.at[sid, 'shortage_qty'])} units, "
             f"fill {f.n(rec['fill_rate_pct'], 2)}%, incremental cost ${f.n(rec['total_cost'], 2)}, approval by {rec['approval_required_role']}.",
             f"\n**Validation against the planning data: {'PASSED' if valid else 'FAILED'}**"]
    for c in chk:  # validation details are computed from the tables by validate_option -> their numbers are data-derived facts
        for m in NUM_RE.findall(ID_RE.sub(" ", DATE_RE.sub(" ", str(c["detail"])))):
            try:
                f.nums.add(round(float(m.replace(",", "")), 2))
            except ValueError:
                pass
    lines += [f"- {'OK' if c['ok'] else 'FAIL'} {c['check']}: {c['detail']}" for c in chk]
    lines.append("\n**Alternatives (cost vs. service trade-off):**\n" + _tbl(alt, ["rank", "option_type", "qty", "covered_qty", "fill_rate_pct", "total_cost", "weeks_late", "policy_check", "capacity_check"], f, {"fill_rate_pct": 2, "total_cost": 2}))
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "recommend", {"mitigation": rec["mitigation_id"], "valid": valid}, [sid, rec["mitigation_id"]], chk, ok, bad, f.nums)


def top_shortages(ctx: Ctx, n: int = 10) -> Answer:
    f = Facts()
    sh = ctx.out["Shortage"].sort_values("priority_rank").head(n)
    text = f"Top {f.n(len(sh))} shortages by priority:\n" + _tbl(sh, ["priority_rank", "shortage_id", "sku_id", "location_id", "first_short_week", "shortage_qty", "value_at_risk", "primary_cause_code", "status"], f, {"value_at_risk": 2})
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "top", {}, list(sh["shortage_id"]), [], ok, bad, f.nums)


def problematic_suppliers(ctx: Ctx, n: int = 5) -> Answer:
    f = Facts()
    c = ctx.card[ctx.card["committed_orders"] >= 3].sort_values(["score", "supplier_id"]).head(n)
    lines = [f"The {f.n(len(c))} lowest-scoring suppliers (score 0-100 from on-time, fulfilment, delays, capacity headroom and shortage exposure; only suppliers with at least {f.n(3)} committed orders):\n"
             + _tbl(c, ["supplier_id", "supplier_name", "score", "tier", "on_time_pct", "delay_incidents", "avg_delay_days", "peak_util_pct", "shortages_exposed"], f, {"score": 2, "on_time_pct": 2, "avg_delay_days": 2, "peak_util_pct": 1})]
    for sid in c["supplier_id"].head(3):
        e = supplier_intel.explain_score(ctx.card, sid)
        lines.append(f"\n{sid}: " + "; ".join(f"{r.component} {f.n(r.value, 1)} x {f.n(r.weight, 2)} = {f.n(r.contribution, 2)}" for r in e.itertuples()))
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "suppliers", {"suppliers": list(c["supplier_id"])}, list(c["supplier_id"]), [], ok, bad, f.nums)


def problematic_locations(ctx: Ctx, n: int = 5) -> Answer:
    f = Facts()
    sh, po = ctx.out["Shortage"], ctx.T["PurchaseOrder"]
    g = sh.groupby("location_id").agg(shortages=("shortage_id", "size"), units=("shortage_qty", "sum"), value_at_risk=("value_at_risk", "sum"))
    top_cause = sh.groupby("location_id")["primary_cause_code"].agg(lambda x: x.value_counts().index[0])
    g["top_cause"] = top_cause
    g["delayed_inbound"] = po[po["status"] == "DELAYED"].groupby("ship_to_location_id").size().reindex(g.index).fillna(0).astype(int)
    g = g.sort_values(["value_at_risk", "shortages"], ascending=False).head(n).reset_index()
    text = f"Locations with the highest value at risk:\n" + _tbl(g, ["location_id", "shortages", "units", "value_at_risk", "top_cause", "delayed_inbound"], f, {"value_at_risk": 2})
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "locations", {}, list(g["location_id"]), [], ok, bad, f.nums)


def supplier_info(ctx: Ctx, sid: str) -> Answer:
    f = Facts()
    c = ctx.card[ctx.card["supplier_id"] == sid]
    if c.empty:
        return Answer(f"Supplier {sid} is not in the dataset.", "not_found")
    r = c.iloc[0]
    e = supplier_intel.explain_score(ctx.card, sid)
    text = (f"**{sid}** ({r['supplier_name']}, {r['region']}, status {r['supplier_status']}): score {f.n(r['score'], 2)} (tier {r['tier']}); {f.n(r['orders'])} orders, "
            f"on-time {f.n(r['on_time_pct'], 2)}%, {f.n(r['delay_incidents'])} delay incident(s), peak capacity utilisation {f.n(r['peak_util_pct'], 1)}%, exposed to "
            f"{f.n(r['shortages_exposed'])} shortage(s).\n\nScore breakdown: " + "; ".join(f"{x.component} {f.n(x.value, 1)} x {f.n(x.weight, 2)} = {f.n(x.contribution, 2)}" for x in e.itertuples()))
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "supplier", {}, [sid], [], ok, bad, f.nums)


def risk_top(ctx: Ctx, n: int = 8) -> Answer:
    f = Facts()
    r = ctx.risk[~ctx.risk["already_short"]].head(n)
    text = f"Highest early-warning risk (not yet short in the next {f.n(8)} weeks):\n" + _tbl(r, ["sku_id", "location_id", "risk_score", "band", "top_factors"], f, {"risk_score": 1})
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "risk", {}, list(r["sku_id"]), [], ok, bad, f.nums)


def overview(ctx: Ctx) -> Answer:
    from .kpi import plan_kpis
    f = Facts()
    k = plan_kpis(ctx.out)
    text = (f"Plan summary: {f.n(k['shortages'])} shortages ({f.n(k['stockouts'])} stock-outs) on {f.n(k['pairs_with_shortage_pct'], 2)}% of {f.n(k['pairs'])} SKU-locations, "
            f"{f.n(k['shortage_units'])} units short, value at risk ${f.n(k['value_at_risk'], 2)}; service level {f.n(k['service_level_pct'], 2)}%; recommended plan costs "
            f"${f.n(k['recommended_cost'], 2)} versus ${f.n(k['do_nothing_cost'], 2)} for doing nothing; {f.n(k['needs_review'])} shortage(s) need data review.")
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "overview", {}, [], [], ok, bad, f.nums)


def whatif(ctx: Ctx, q: str) -> Answer:
    f = Facts()
    sc = Scenario(name="assistant")
    def signed(m, clause: str) -> float:
        v = float(m.group(1))
        down = re.search(r"decreas|drop|fall|reduc|lower|cut|less|down|shrink|loss", clause)
        return -abs(v) if down else v

    def clause_of(m) -> str:  # words around the match decide the direction
        return q[max(0, m.start() - 25): m.end() + 5]
    m = re.search(r"demand\D{0,30}?([+-]?\d+(?:\.\d+)?)\s*%", q)
    if m:
        sc.demand_multiplier = max(0.0, 1 + signed(m, clause_of(m)) / 100)
    m = re.search(r"lead\s*time\D{0,30}?([+-]?\d+)\s*d", q)
    if m:
        sc.lead_time_delta_days = int(signed(m, clause_of(m)))
    m = re.search(r"capacity\D{0,30}?([+-]?\d+(?:\.\d+)?)\s*%", q)
    if m:
        sc.capacity_factor = max(0.01, 1 + signed(m, clause_of(m)) / 100)
    m = re.search(r"(?:transport|shipping|delay)\D{0,30}?(\d+)\s*d", q)
    if m:
        sc.transport_delay_days = int(m.group(1))
    if sc.is_noop():
        return Answer("I could not read a scenario change from that question. Try e.g. 'what if demand increases by 20%' or 'what if transport delays add 7 days'.", "help")
    res = simulate(ctx.T, ctx.out, sc, ctx.policy)
    t = res["kpis"]
    for d in res["description"]:  # scenario parameters are the user's own inputs, echoed back
        for m in NUM_RE.findall(d):
            f.nums.add(round(float(m.replace(",", "")), 2))
    text = "Scenario (" + "; ".join(res["description"]) + ") recomputed with the planning engine (baseline unchanged):\n" + _tbl(t, ["metric", "baseline", "scenario", "delta"], f, {"baseline": 2, "scenario": 2, "delta": 2}) \
        + f"\n\nShortages: {f.n(res['counts']['new'])} new, {f.n(res['counts']['resolved'])} resolved, {f.n(res['counts']['worse'])} worse, {f.n(res['counts']['better'])} better."
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "whatif", {}, [], [], ok, bad, f.nums)


# ------------------------------------------------------------------------------------ supplier deep-dive handlers
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
REFERENTIAL = re.compile(r"\b(these|those|them|same|above|previous|listed|aforementioned|all\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))\b")
COMPONENTS = [("on_time", "on_time_pct", "on-time delivery %"), ("fulfilment", "fulfilment_pct", "fulfilment %"),
              ("delay", "delay_score", "delay performance (0-100)"), ("capacity", "capacity_score", "capacity headroom (0-100)"),
              ("exposure", "exposure_score", "shortage exposure (0-100, higher = less exposed)")]
# New-PO risk = supplier_disruption_risk (risk.py) + current-week capacity pressure + lead-time length + missing lead times.
NEW_PO_WEIGHTS = {"capacity_pressure": 20.0, "lead_time": 10.0, "lead_time_days_cap": 60.0, "missing_lead_time": 10.0}


def _count(part: str, default: int | None = 5) -> int | None:
    m = re.search(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:\w+\s+)?suppliers?\b", part.lower())
    if not m:
        return default
    v = m.group(1)
    return int(v) if v.isdigit() else NUM_WORDS[v]


def _doc_item(doc: str, key: str) -> str:
    """Exact definition text from a module docstring (the documented methodology), whitespace-normalised."""
    for it in re.split(r"\n\* ", doc):
        if it.strip().startswith(key):
            return " ".join(it.split()).rstrip(",.")
    norm = " ".join(doc.split())
    m = re.search(re.escape(key) + r".*?(?=, \w+_score =|\. [A-Z]|\.$)", norm)
    return m.group(0).rstrip(",.") if m else ""


def _plain_definitions(f: Facts) -> str:
    """Plain-language meaning of the five score components (numbers are the documented thresholds of supplier_intel)."""
    w = supplier_intel.WEIGHTS
    return "\n".join([
        "**What each component means:**",
        f"- **On-time delivery %** (weight {f.n(w['on_time'], 2)}): of the orders this supplier has committed to (confirmed, in transit, delayed or received), the share that arrived - or is currently expected - on or before the date we asked for. Higher is better.",
        f"- **Fulfilment %** (weight {f.n(w['fulfilment'], 2)}): the share of the quantity we ordered that falls in weeks where the supplier has enough declared capacity, i.e. orders it can deliver in full. Higher is better. (A proxy: the data has no partial-shipment records.)",
        f"- **Delay score** (weight {f.n(w['delay'], 2)}): starts at {f.n(100)} and loses points for transport-delay incidents relative to the supplier's committed orders and for the average number of days it promised later than we requested. Higher means fewer and shorter delays.",
        f"- **Capacity headroom** (weight {f.n(w['capacity'], 2)}): how much spare capacity the supplier had in its busiest order week. Full marks up to {f.n(60)}% peak utilisation, falling to {f.n(0)} at {f.n(100)}% or more. Higher means more room for extra orders.",
        f"- **Shortage exposure** (weight {f.n(w['exposure'], 2)}): how little of the plan's shortage quantity is traced back to this supplier's late or cancelled orders. {f.n(100)} means none of our shortages come from its orders; lower means its orders contributed to shortages.",
    ])


def supplier_breakdown(ctx: Ctx, ids: list | None = None, n: int = 5, why: str = "", define: bool = False) -> Answer:
    """All five score components (value x weight = contribution) + raw drivers for each requested supplier."""
    f = Facts()
    card = ctx.card
    if ids:
        missing = [i for i in ids if i not in set(card["supplier_id"])]
        if missing:
            return Answer(f"I could not find {', '.join(missing)} in the supplier scorecard.", "not_found")
        sel = card.set_index("supplier_id").loc[ids].reset_index()
    else:
        sel = card[card["committed_orders"] >= 3].sort_values(["score", "supplier_id"]).head(n)
        why = why or f"the {f.n(len(sel))} lowest-scoring suppliers with at least {f.n(3)} committed orders"
    rows, checks = [], []
    for sid in sel["supplier_id"]:
        e = supplier_intel.explain_score(card, sid).set_index("component")
        r = card[card["supplier_id"] == sid].iloc[0]
        row = {"supplier_id": sid, "score": r["score"], "tier": r["tier"], "confidence": r["confidence"]}
        for k, col, _ in COMPONENTS:
            row[col] = e.at[k, "value"]
            row[f"{k}_pts"] = e.at[k, "contribution"]
        rows.append(row)
        total = float(e["contribution"].sum())
        checks.append({"check": f"{sid}: components sum to score", "ok": abs(total - float(r["score"])) < 0.06, "detail": f"{total:.2f} vs {float(r['score']):.2f}"})
    t = pd.DataFrame(rows)
    w = supplier_intel.WEIGHTS
    lines = [f"Complete score breakdown for {why} (score 0-100 = " + " + ".join(f"{f.n(w[k], 2)} x {label}" for k, _, label in COMPONENTS) + "):\n",
             _tbl(t, ["supplier_id", "score", "tier", "on_time_pct", "fulfilment_pct", "delay_score", "capacity_score", "exposure_score", "confidence"], f,
                  {"score": 2, "on_time_pct": 2, "fulfilment_pct": 2, "delay_score": 2, "capacity_score": 2, "exposure_score": 2}),
             "\n**Points contributed by each component (value x weight):**\n",
             _tbl(t, ["supplier_id", "on_time_pts", "fulfilment_pts", "delay_pts", "capacity_pts", "exposure_pts", "score"], f,
                  {"on_time_pts": 2, "fulfilment_pts": 2, "delay_pts": 2, "capacity_pts": 2, "exposure_pts": 2, "score": 2}),
             "\n**Underlying data per supplier:**\n",
             _tbl(sel, ["supplier_id", "committed_orders", "delay_incidents", "avg_delay_days", "avg_slip_days", "peak_util_pct", "weeks_over_90", "shortages_exposed", "exposed_units"], f,
                  {"avg_delay_days": 2, "avg_slip_days": 2, "peak_util_pct": 1})]
    for c in checks:
        reg(f, c["detail"])
    lines.append("\nCheck: " + ("every breakdown sums exactly to the supplier score." if all(c["ok"] for c in checks) else "MISMATCH between components and score: " + "; ".join(c["detail"] for c in checks if not c["ok"])))
    lines.append("\nNote: fulfilment is the in-full proxy (share of ordered quantity in supplier-weeks within capacity) because the data has no partial-shipment records.")
    if define:
        lines.append("\n" + _plain_definitions(f))
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "supplier_breakdown", {"suppliers": list(sel["supplier_id"])}, list(sel["supplier_id"]), checks, ok, bad, f.nums)


TERMS = [  # (term key, regex, docstring source, docstring key)
    ("peak_utilisation", r"peak\s*util|utili[sz]ation|above\s*100|over\s*100|>\s*100\s*%", "supplier_intel", "peak_util_pct"),
    ("on_time", r"on[- ]?time", "supplier_intel", "on_time_pct"),
    ("fulfilment", r"fulfil", "supplier_intel", "fulfilment_pct"),
    ("delay_performance", r"delay (?:performance|score)", "supplier_intel", "delay_score"),
    ("capacity_headroom", r"capacity (?:headroom|score)|headroom", "supplier_intel", "capacity_score"),
    ("shortage_exposure", r"shortage exposure|exposure score", "supplier_intel", "exposure_score"),
    ("supplier_score", r"supplier score|composite score|tier", "supplier_intel", "Composite score"),
    ("disruption_risk", r"disruption risk", "risk", "Supplier disruption risk"),
]


def explain_term(ctx: Ctx, key: str) -> Answer:
    f = Facts()
    mod = {"supplier_intel": supplier_intel, "risk": risk}
    _, _, src, dkey = next(t for t in TERMS if t[0] == key)
    definition = _doc_item(mod[src].__doc__ or "", dkey)
    reg(f, definition)  # documented methodology constants (weights, thresholds) from the scoring module itself
    if key != "peak_utilisation":
        text = f"**{key.replace('_', ' ')}** - documented definition (source: `{src}` module):\n\n> {definition or 'no documented definition found'}"
        ok, bad = verify_grounded(text, ctx, f)
        return Answer(text, "term", {"term": key}, [], [], ok, bad, f.nums)
    card, led = ctx.card, ctx.out["SupplierCapacityLedger"]
    over = card[card["peak_util_pct"] > 100].sort_values("peak_util_pct", ascending=False)
    ex = led[(led["status"] == "EXCEEDED")].sort_values(["supplier_id", "week_start_date"])
    fnd = ctx.out["DataQualityFinding"]
    n_f = int((fnd["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED").sum())
    cap_doc = _doc_item(supplier_intel.__doc__, "capacity_score")
    reg(f, cap_doc)
    checks = []
    for r in over.itertuples():  # verify the documented headroom formula against the stored component
        expect = 100 - min(100, 2.5 * max(0, r.peak_util_pct - 60))
        checks.append({"check": f"{r.supplier_id}: capacity headroom formula", "ok": abs(expect - r.capacity_score) < 0.01, "detail": f"{expect:.2f} vs {r.capacity_score:.2f}"})
    lines = [f"**Peak utilisation** - {definition}",
             f"\nPeak utilisation = highest weekly committed quantity / effective weekly capacity, over all order weeks in the capacity ledger. "
             f"**Above {f.n(100)}%** means the orders already committed for that week exceed what the supplier declared it can supply, so part of that load "
             f"is at risk of late or short delivery. The planning engine flags every such supplier-week as SUPPLIER_CAPACITY_EXCEEDED, gives new-order "
             f"mitigations zero remaining capacity for that week, and the capacity-headroom component drops to {f.n(0)} once peak utilisation reaches {f.n(100)}% ({cap_doc}).",
             f"\nIn this dataset **{f.n(len(over))}** supplier(s) have peak utilisation above {f.n(100)}% and the engine raised **{f.n(n_f)}** capacity-exceeded finding(s):"]
    if len(over):
        lines.append(_tbl(over, ["supplier_id", "peak_util_pct", "capacity_score", "fulfilment_pct", "score"], f, {"peak_util_pct": 1, "capacity_score": 2, "fulfilment_pct": 2, "score": 2}))
    if len(ex):
        lines.append("\nExceeded supplier-weeks (capacity ledger):\n" + _tbl(ex.head(15), ["supplier_id", "product_family", "week_start_date", "committed_qty", "capacity_qty", "utilisation_pct"], f, {"utilisation_pct": 1}))
    for c in checks:
        reg(f, c["detail"])
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "term", {"term": key}, list(over["supplier_id"]), checks, ok, bad, f.nums)


def po_risk_table(ctx: Ctx, sku: str | None = None, family: str | None = None) -> pd.DataFrame:
    """Per supplier: eligibility, disruption risk (risk.supplier_disruption_risk), current-week commitments vs capacity,
    open orders, lead time; new_po_risk = disruption + capacity pressure + lead time + missing-lead-time penalty."""
    from .. import dq
    T, out, card = ctx.T, ctx.out, ctx.card
    fam_of = T["SKU"].set_index("sku_id")["product_family"]
    dr = risk.supplier_disruption_risk(T, card).set_index("supplier_id")
    sup = T["Supplier"].set_index("supplier_id")
    ss = T["SKUSupplier"]
    appr = ss[ss["approval_status"] == "APPROVED"]
    if sku:
        appr = appr[appr["sku_id"] == sku]
    if family:
        appr = appr[appr["sku_id"].map(fam_of) == family]
    cand = sorted(set(appr["supplier_id"])) if (sku or family) else list(card["supplier_id"])
    ws = dq.week_start_str(pd.Series([ctx.as_of])).iloc[0]
    cap = T["SupplierCapacity"]
    keys = cap[["supplier_id", "product_family"]].drop_duplicates()
    if family or sku:
        keys = keys[keys["product_family"] == (family or fam_of[sku])]
    keys = keys[keys["supplier_id"].isin(cand)].assign(week_start_date=ws).reset_index(drop=True)
    keys["capacity_now"] = dq.capacity_for(cap, keys).fillna(0).values
    led = out["SupplierCapacityLedger"]
    com = led[led["week_start_date"] == ws].set_index(["supplier_id", "product_family"])["committed_qty"]
    keys["committed_now"] = [int(com.get((a, b), 0)) for a, b in zip(keys["supplier_id"], keys["product_family"])]
    keys["remaining_now"] = (keys["capacity_now"] - keys["committed_now"]).clip(lower=0)
    g = keys.groupby("supplier_id")[["capacity_now", "committed_now", "remaining_now"]].sum()
    po = T["PurchaseOrder"]
    op = po[po["status"].isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"])]
    lt = T["LeadTime"]
    lt_s = lt[lt["sku_id"] == sku] if sku else lt
    rows = []
    for s in cand:
        o = op[op["supplier_id"] == s]
        l = lt_s[lt_s["supplier_id"] == s]["total_lead_days"]
        a_skus = set(appr.loc[appr["supplier_id"] == s, "sku_id"])
        missing_lt = len(a_skus - set(lt[lt["supplier_id"] == s]["sku_id"]))
        capn, comn = (float(g.at[s, "capacity_now"]), float(g.at[s, "committed_now"])) if s in g.index else (0.0, 0.0)
        util = comn / capn if capn > 0 else 1.0
        med = float(l.median()) if len(l) else float("nan")
        eligible = sup.at[s, "status"] == "ACTIVE" and len(a_skus) > 0
        reason = "eligible" if eligible else ("supplier status " + sup.at[s, "status"] if sup.at[s, "status"] != "ACTIVE" else "no approved sourcing record")
        comp = {"disruption": float(dr.at[s, "disruption_risk"]),
                "capacity_pressure": round(NEW_PO_WEIGHTS["capacity_pressure"] * min(1.0, util), 2),
                "lead_time": round(NEW_PO_WEIGHTS["lead_time"] * min(1.0, (med if med == med else NEW_PO_WEIGHTS["lead_time_days_cap"]) / NEW_PO_WEIGHTS["lead_time_days_cap"]), 2),
                "missing_lead_time": NEW_PO_WEIGHTS["missing_lead_time"] if missing_lt else 0.0}
        rows.append({"supplier_id": s, "eligible": eligible, "eligibility": reason, "score": float(card.set_index("supplier_id").at[s, "score"]),
                     "disruption_band": dr.at[s, "band"], **comp, "new_po_risk": round(sum(comp.values()), 2),
                     "committed_now": comn, "capacity_now": capn, "util_now_pct": round(100 * util, 1) if capn > 0 else None,
                     "remaining_now": float(g.at[s, "remaining_now"]) if s in g.index else 0.0, "open_orders": len(o), "open_qty": int(o["qty_base"].sum()),
                     "delayed_open": int((o["status"] == "DELAYED").sum()), "median_lead_days": med, "missing_lead_times": missing_lt,
                     "approved_skus": len(a_skus)})
    return pd.DataFrame(rows).sort_values(["new_po_risk", "supplier_id"], ascending=[False, True]).reset_index(drop=True)


def _capacity_now(ctx: Ctx, suppliers: list) -> pd.DataFrame:
    """Per supplier x product family in the as-of order week: effective capacity (latest effective record), committed load
    (capacity ledger) and remaining capacity.  A new order placed now is booked in this week."""
    from .. import dq
    ws = dq.week_start_str(pd.Series([ctx.as_of])).iloc[0]
    cap = ctx.T["SupplierCapacity"]
    keys = cap[cap["supplier_id"].isin(suppliers)][["supplier_id", "product_family"]].drop_duplicates().assign(week_start_date=ws).reset_index(drop=True)
    if keys.empty:
        return keys.assign(capacity_now=[], committed_now=[], remaining_now=[])
    keys["capacity_now"] = dq.capacity_for(cap, keys).fillna(0).astype(int).values
    led = ctx.out["SupplierCapacityLedger"]
    com = led[led["week_start_date"] == ws].set_index(["supplier_id", "product_family"])["committed_qty"]
    keys["committed_now"] = [int(com.get((a, b), 0)) for a, b in zip(keys["supplier_id"], keys["product_family"])]
    keys["remaining_now"] = (keys["capacity_now"] - keys["committed_now"]).clip(lower=0)
    return keys.sort_values(["supplier_id", "product_family"]).reset_index(drop=True)


def capacity_exceedance(ctx: Ctx, ids: list) -> Answer:
    """Why named suppliers exceed capacity: the exceeded supplier-weeks from the capacity ledger, the orders that make up
    the committed load, and the capacity record in effect for that week (all read from the tables, nothing inferred)."""
    from .. import dq
    f = Facts()
    T, out = ctx.T, ctx.out
    led = out["SupplierCapacityLedger"]
    cap = T["SupplierCapacity"]
    pe = dq.po_effective(T)
    pe = pe[(pe["status"] != "CANCELLED") & ~pe["is_duplicate"] & ~pe["factor_missing"]].copy()
    pe["ws"] = dq.week_start_str(pe["order_date"])
    fnd = out["DataQualityFinding"]
    card = ctx.card.set_index("supplier_id")
    lines, checks = [f"**Capacity exceedance** (capacity ledger: committed order quantity per supplier, product family and order week vs. the capacity record in effect that week):"], []
    for s in ids:
        rows = led[(led["supplier_id"] == s) & (led["status"] == "EXCEEDED")].sort_values(["week_start_date", "product_family"])
        if rows.empty:
            lines.append(f"\n**{s}** does not exceed capacity in any order week: its peak utilisation is {f.n(card.at[s, 'peak_util_pct'], 1)}% "
                         f"({f.n(card.at[s, 'weeks_over_90'])} week(s) at or above {f.n(90)}%).")
            continue
        lines.append(f"\n**{s}** exceeds capacity in {f.n(len(rows))} supplier-week(s) (peak utilisation {f.n(card.at[s, 'peak_util_pct'], 1)}%):")
        for r in rows.itertuples():
            ws, fam = r.week_start_date, r.product_family
            o = pe[(pe["supplier_id"] == s) & (pe["product_family"] == fam) & (pe["ws"] == ws)].sort_values("qty_eff", ascending=False)
            c = cap[(cap["supplier_id"] == s) & (cap["product_family"] == fam) & (cap["status"] == "ACTIVE")].sort_values("effective_from")
            eff = c[(c["effective_from"] <= ws) & (c["effective_to"].isna() | (ws < c["effective_to"]))].iloc[-1]
            base = c.iloc[0]
            fids = list(fnd[(fnd["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED") & (fnd["record_id"] == dq.cap_key(s, fam, ws))]["finding_id"])
            top = ", ".join(f"{x.po_id} ({f.n(x.qty_eff)})" for x in o.head(3).itertuples())
            txt = (f"- {fam}, order week of {ws}: {f.n(r.committed_qty)} units committed on {f.n(len(o))} order(s) (largest: {top}) against a weekly capacity of "
                   f"{f.n(r.capacity_qty)}, i.e. {f.n(r.utilisation_pct, 1)}% - {f.n(r.committed_qty - r.capacity_qty)} units over. Capacity record in effect: "
                   f"{eff['capacity_id']} ({f.n(eff['weekly_capacity_qty'])} units/week, effective {eff['effective_from']} to {eff['effective_to'] if isinstance(eff['effective_to'], str) else 'open-ended'})")
            if eff["capacity_id"] != base["capacity_id"] and eff["weekly_capacity_qty"] < base["weekly_capacity_qty"]:
                fits = r.committed_qty <= base["weekly_capacity_qty"]
                period = "for that period only" if isinstance(eff["effective_to"], str) else "from that date onwards"
                txt += (f"; it supersedes the base record {base['capacity_id']} ({f.n(base['weekly_capacity_qty'])} units/week) {period}, so a load that "
                        + ("would fit the base capacity exceeds the reduced one" if fits else "already exceeds the base capacity exceeds it even more"))
            lines.append(txt + "." + (f" Engine finding: {', '.join(fids)}." if fids else ""))
            checks.append({"check": f"{s} {fam} {ws}: committed load equals the sum of its orders", "ok": int(o["qty_eff"].sum()) == int(r.committed_qty),
                           "detail": f"{int(o['qty_eff'].sum())} vs {int(r.committed_qty)}"})
            checks.append({"check": f"{s} {fam} {ws}: ledger capacity equals the record in effect", "ok": int(eff["weekly_capacity_qty"]) == int(r.capacity_qty),
                           "detail": f"{int(eff['weekly_capacity_qty'])} vs {int(r.capacity_qty)}"})
    for c in checks:
        reg(f, c["detail"])
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "capacity", {"suppliers": list(ids)}, list(ids), checks, ok and all(c["ok"] for c in checks), bad, f.nums)


def order_eligibility(ctx: Ctx, ids: list) -> Answer:
    """Can a new order be placed with each named supplier now?  Status, approved sourcing, lead times, and the
    current order week's capacity / committed / remaining capacity per product family; upcoming exceeded weeks."""
    from .. import dq
    f = Facts()
    T = ctx.T
    sup = T["Supplier"].set_index("supplier_id")
    ss = T["SKUSupplier"]
    lt = T["LeadTime"]
    capn = _capacity_now(ctx, ids)
    ws = dq.week_start_str(pd.Series([ctx.as_of])).iloc[0]
    led = ctx.out["SupplierCapacityLedger"]
    lines = [f"**Can a new order be placed now?** (order booked in the as-of week starting {ws}; eligibility = ACTIVE supplier with an approved sourcing record)"]
    checks, verdicts = [], {}
    for s in ids:
        status = sup.at[s, "status"]
        mine = ss[ss["supplier_id"] == s]
        appr = set(mine.loc[mine["approval_status"] == "APPROVED", "sku_id"])
        blocked = int((mine["approval_status"] != "APPROVED").sum())
        no_lt = len(appr - set(lt[lt["supplier_id"] == s]["sku_id"]))
        cn = capn[capn["supplier_id"] == s]
        rem, capt, comt = int(cn["remaining_now"].sum()), int(cn["capacity_now"].sum()), int(cn["committed_now"].sum())
        ahead = led[(led["supplier_id"] == s) & (led["status"] == "EXCEEDED") & (led["week_start_date"] >= ws)]
        if status != "ACTIVE":
            v = f"No - supplier status is {status}"
        elif not appr:
            v = "No - no approved sourcing record"
        elif rem <= 0:
            v = "Not this week - no remaining capacity in the current order week"
        else:
            full = list(cn.loc[cn["remaining_now"] <= 0, "product_family"])
            v = f"Yes - eligible, {f.n(rem)} units of remaining capacity this week" + (f" (none left for {', '.join(full)})" if full else "")
        verdicts[s] = v.split(" ")[0]
        lines.append(f"\n**{s}: {v}.** {f.n(len(appr))} approved SKU(s)" + (f", {f.n(blocked)} blocked sourcing record(s)" if blocked else "")
                     + (f", {f.n(no_lt)} approved SKU(s) without a lead time (orders for those cannot be scheduled)" if no_lt else "")
                     + f". This week: {f.n(comt)} committed of {f.n(capt)} capacity across {f.n(len(cn))} product family(ies).")
        if len(cn):
            lines.append(_tbl(cn, ["product_family", "capacity_now", "committed_now", "remaining_now"], f))
        if len(ahead):
            lines.append("Upcoming order weeks already over capacity (avoid scheduling extra load there): "
                         + "; ".join(f"{r.product_family} week of {r.week_start_date} ({f.n(r.utilisation_pct, 1)}%)" for r in ahead.itertuples()))
        checks.append({"check": f"{s} status in Supplier table", "ok": True, "detail": status})
        checks.append({"check": f"{s} remaining capacity = capacity - committed per family (floored at 0)", "ok": bool((cn["remaining_now"] == (cn["capacity_now"] - cn["committed_now"]).clip(lower=0)).all()),
                       "detail": f"{rem} of {capt}"})
    for c in checks:
        reg(f, c["detail"])
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "eligibility", {"suppliers": list(ids), "verdicts": verdicts}, list(ids), checks, ok and all(c["ok"] for c in checks), bad, f.nums)


def po_supplier_choice(ctx: Ctx, mode: str = "riskiest", focus: list | None = None, sku: str | None = None, family: str | None = None) -> Answer:
    """mode='riskiest': highest new-PO risk among eligible suppliers.  mode='safest' (= best choice): lowest new-PO risk among
    eligible suppliers that have remaining capacity this week and lead times for all approved SKUs.  With `focus`, the
    best choice is made among those suppliers only and the highest-risk one is reported separately."""
    f = Facts()
    t = po_risk_table(ctx, sku, family)
    if t.empty:
        return Answer("No supplier has an approved sourcing record for that scope, so I cannot rank suppliers for a new order.", "not_found")
    focus = [s for s in (focus or []) if s in set(t["supplier_id"])]
    el = t[t["eligible"]]
    pool_all = t[t["supplier_id"].isin(focus)] if focus else t
    pool = el[el["supplier_id"].isin(focus)] if focus else el
    suitable = pool[(pool["remaining_now"] > 0) & (pool["missing_lead_time"] == 0)].sort_values(["new_po_risk", "supplier_id"])
    if mode == "safest":
        pick = suitable.iloc[0] if len(suitable) else None
    else:
        pick = el.iloc[0] if len(el) else None
    checks = []
    if pick is not None:
        sid = pick["supplier_id"]
        st_ = ctx.T["Supplier"].set_index("supplier_id").at[sid, "status"]
        checks.append({"check": f"{sid} status in Supplier table", "ok": st_ == "ACTIVE", "detail": st_})
        ss = ctx.T["SKUSupplier"]
        n_ok = int(((ss["supplier_id"] == sid) & (ss["approval_status"] == "APPROVED")).sum())
        checks.append({"check": f"{sid} has approved sourcing records", "ok": n_ok > 0, "detail": f"{n_ok} approved SKU(s)"})
        dr = risk.supplier_disruption_risk(ctx.T, ctx.card).set_index("supplier_id").at[sid, "disruption_risk"]
        checks.append({"check": "disruption risk equals risk.supplier_disruption_risk()", "ok": abs(float(dr) - pick["disruption"]) < 0.01, "detail": f"{float(dr):.2f}"})
        comp_sum = pick["disruption"] + pick["capacity_pressure"] + pick["lead_time"] + pick["missing_lead_time"]
        checks.append({"check": "new-PO risk equals the sum of its components", "ok": abs(comp_sum - pick["new_po_risk"]) < 0.02, "detail": f"{comp_sum:.2f}"})
        if mode == "safest":
            rn = _capacity_now(ctx, [sid])["remaining_now"].sum()
            checks.append({"check": f"{sid} has remaining capacity this week (recomputed)", "ok": rn > 0, "detail": f"{int(rn)} units"})
        for c in checks:
            reg(f, c["detail"])
    scope = f"SKU {sku}" if sku else (f"family {family}" if family else (f"the {len(focus)} suppliers discussed earlier" if focus else "all suppliers"))
    w = NEW_PO_WEIGHTS
    cols = ["supplier_id", "new_po_risk", "disruption", "capacity_pressure", "lead_time", "missing_lead_time", "score", "util_now_pct", "remaining_now", "open_orders", "delayed_open", "median_lead_days"]
    dec = {"new_po_risk": 2, "disruption": 2, "capacity_pressure": 2, "lead_time": 2, "missing_lead_time": 2, "score": 2, "util_now_pct": 1, "median_lead_days": 1}
    lines = [f"**New-purchase-order supplier risk** ({scope.replace(str(len(focus)), f.n(len(focus))) if focus else scope}; as-of week {ctx.as_of}). New-PO risk = disruption risk (supplier score inverse + inactive-status, "
             f"single-source and open-delay adjustments from the risk module) + {f.n(w['capacity_pressure'])} x current-week committed/capacity + "
             f"{f.n(w['lead_time'])} x min(1, median lead days / {f.n(w['lead_time_days_cap'])}) + {f.n(w['missing_lead_time'])} if any approved SKU lacks a lead time. "
             f"Lower is safer. Only ACTIVE suppliers with an approved sourcing record are eligible."]

    def evidence(r):
        return (f"new-PO risk {f.n(r['new_po_risk'], 2)} (disruption {f.n(r['disruption'], 2)}, band {r['disruption_band']}; capacity pressure {f.n(r['capacity_pressure'], 2)}; "
                f"lead time {f.n(r['lead_time'], 2)}; missing lead time {f.n(r['missing_lead_time'], 2)}). Evidence: supplier score {f.n(r['score'], 2)}; this week "
                f"{f.n(r['committed_now'])} committed against {f.n(r['capacity_now'])} capacity, {f.n(r['remaining_now'])} units remaining; {f.n(r['open_orders'])} open order(s) "
                f"totalling {f.n(r['open_qty'])} units, {f.n(r['delayed_open'])} currently delayed; median lead time {f.n(r['median_lead_days'], 1)} days")
    if mode == "safest":
        if pick is None:
            lines.append("\n**No suitable supplier**: none of the suppliers in scope is eligible with remaining capacity this week and lead times for its approved SKUs.")
        else:
            lines.append(f"\n**Best choice (lowest new-order risk): {pick['supplier_id']}** - {evidence(pick)}.")
            hi = pool.sort_values(["new_po_risk", "supplier_id"], ascending=[False, True])
            if len(hi) and hi.iloc[0]["supplier_id"] != pick["supplier_id"]:
                h = hi.iloc[0]
                lines.append(f"\n**Highest risk (not recommended): {h['supplier_id']}** - {evidence(h)}.")
            lines.append("\n**Trade-offs versus the other suitable suppliers:**")
            names = {"disruption": "disruption risk", "capacity_pressure": "capacity pressure", "lead_time": "lead-time risk"}
            for o in suitable.itertuples():
                if o.supplier_id == pick["supplier_id"]:
                    continue
                better = [f"{names[k]} {f.n(pick[k], 2)} vs {f.n(getattr(o, k), 2)}" for k in names if pick[k] < getattr(o, k) - 1e-9]
                worse = [f"{names[k]} {f.n(pick[k], 2)} vs {f.n(getattr(o, k), 2)}" for k in names if pick[k] > getattr(o, k) + 1e-9]
                cap_note = (f"; remaining capacity this week: {pick['supplier_id']} {f.n(pick['remaining_now'])} vs {o.supplier_id} {f.n(o.remaining_now)} units"
                            if o.remaining_now != pick["remaining_now"] else "")
                lines.append(f"- vs {o.supplier_id} (new-PO risk {f.n(o.new_po_risk, 2)}): {pick['supplier_id']} is better on " + (", ".join(better) if better else "no component")
                             + ("; worse on " + ", ".join(worse) if worse else "") + cap_note + ".")
    else:
        if pick is None:
            lines.append("\nNo eligible supplier was found for this scope.")
        else:
            lines.append(f"\n**Riskiest eligible choice: {pick['supplier_id']}** - {evidence(pick)}.")
        if focus:
            ff = pool.sort_values(["new_po_risk", "supplier_id"], ascending=[False, True])
            if len(ff):
                r = ff.iloc[0]
                lines.append(f"\nAmong the {f.n(len(focus))} suppliers discussed above, the highest-risk choice is **{r['supplier_id']}** (new-PO risk {f.n(r['new_po_risk'], 2)}).")
    excluded = pool_all[~pool_all["supplier_id"].isin(suitable["supplier_id"])] if mode == "safest" else pool_all[~pool_all["eligible"]]
    for r in excluded.itertuples():
        why = r.eligibility if not r.eligible else ("no remaining capacity this week" if r.remaining_now <= 0 else "approved SKU(s) without a lead time")
        lines.append(f"\nNot suitable: {r.supplier_id} ({why}).")
    show = pool.sort_values(["new_po_risk", "supplier_id"], ascending=[mode == "safest", True]).head(8)
    lines.append(f"\n**{'Suppliers in scope' if focus else 'Top eligible suppliers'} by this ranking ({'lowest' if mode == 'safest' else 'highest'} risk first):**\n" + _tbl(show, cols, f, dec))
    if checks:
        lines.append("\nValidation: " + "; ".join(f"{'OK' if c['ok'] else 'FAIL'} {c['check']} ({c['detail']})" for c in checks))
    text = "\n".join(lines)
    ok, bad = verify_grounded(text, ctx, f)
    sources = ([pick["supplier_id"]] if pick is not None else []) + [s for s in show["supplier_id"] if pick is None or s != pick["supplier_id"]]
    return Answer(text, "po_supplier", {"pick": None if pick is None else pick["supplier_id"], "mode": mode, "suppliers": focus or [], "highest_risk": None if pool.empty else pool.iloc[0]["supplier_id"]},
                  sources, checks, ok and all(c["ok"] for c in checks), bad, f.nums)


def supplier_disruption(ctx: Ctx, n: int = 8) -> Answer:
    f = Facts()
    d = risk.supplier_disruption_risk(ctx.T, ctx.card).head(n)
    text = f"Supplier disruption risk (risk module: {f.n(100)} - score + inactive-status, single-source and open-delay adjustments):\n" + \
        _tbl(d, ["supplier_id", "disruption_risk", "band", "base", "status_adj", "single_source_adj", "open_delay_adj", "supplier_status", "score"], f,
             {"disruption_risk": 2, "base": 2, "status_adj": 2, "single_source_adj": 2, "open_delay_adj": 2, "score": 2})
    ok, bad = verify_grounded(text, ctx, f)
    return Answer(text, "disruption", {}, list(d["supplier_id"]), [], ok, bad, f.nums)


CAPS = ("I can answer from the loaded data: shortage explanations ('why does SHORT-2026-000001 happen?'), recommendations with validation "
        "('what should we do about SHORT-2026-000001?'), top shortages, problematic suppliers or locations, supplier details ('SUP-0001'), "
        "full supplier score breakdowns, definitions such as peak utilisation, the riskiest or safest supplier for a new purchase order, "
        "supplier disruption risk, early-warning risks, plan overview, and what-if questions ('what if demand increases by 20%?'). "
        "Multi-part questions are answered part by part.")

CAPS_SHORT = ("Supported topics: shortage explanations and recommendations, top shortages, problematic suppliers or locations, supplier details, "
              "supplier score breakdowns, definitions, new-order supplier risk, supplier disruption risk, early-warning risk, plan overview and what-if scenarios.")

LABELS = {"whatif": "What-if scenario", "explain": "Shortage explanation", "recommend": "Recommendation", "breakdown": "Supplier score breakdown",
          "term": "Definition", "po_choice": "Supplier choice for a new purchase order", "disruption": "Supplier disruption risk",
          "supplier": "Supplier detail", "suppliers": "Problematic suppliers", "risk": "Early-warning risk", "locations": "Problematic locations",
          "top": "Top shortages", "overview": "Plan overview", "capacity_why": "Capacity exceedance", "eligibility": "New-order eligibility"}


def _split(q: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+|;\s+|\s+and then\s+", q.strip())
    return [p.strip() for p in parts if len(re.sub(r"\W", "", p)) > 2]


RANK_WORDS = r"riskiest|most risky|highest[- ]risk|\bavoid\b|least (?:safe|reliable)|safest|least risky|lowest[- ]risk|\bbest\b|choose|recommend|prefer|go with|which (?:supplier|one|of)|who should|pick"
RISKY_WORDS = r"riskiest|most risky|highest[- ]risk|\bavoid\b|least (?:safe|reliable)|worst"
ORDER_WORDS = r"new (?:purchase )?order|new po\b|purchase order|place (?:a|an) (?:new )?order|order with|order from|for (?:a|an|the) (?:new )?(?:order|po)\b|\bsource from"
DEFINE_CUE = r"\bexplain|meaning|what does|what (?:is|are)|define|definition|\bmeans?\b|interpret"


def _intents(p: str) -> list[tuple]:
    """All intents found in one part of the question (several per part are allowed, unrelated ones are not added)."""
    pl = p.lower()
    ids = ID_RE.findall(p)
    sup_ids = list(dict.fromkeys(i for i in ids if i.startswith("SUP-")))
    sku = next((i for i in ids if i.startswith("SKU-")), None)
    fam = next((i for i in ids if i.startswith("FAM-")), None)
    shorts = [i[:len("SHORT-2026-000000")] for i in ids if i.startswith("SHORT-")] + [i[4:4 + len("SHORT-2026-000000")] for i in ids if i.startswith("MIT-SHORT-")]
    if re.search(r"what[\s-]*if|scenario|suppose|simulate", pl):
        return [("whatif", pl)]
    out = []
    sup_ctx = bool(sup_ids) or re.search(r"supplier|vendor", pl)
    breakdown = sup_ctx and re.search(r"breakdown|component|scoring|score details?|each score|every score|explain (?:the |their )?scores?", pl)
    define = bool(re.search(DEFINE_CUE, pl))
    if define and not breakdown:  # component definitions are included inside the breakdown when both are asked
        out += [("term", key) for key, rx, _, _ in TERMS if re.search(rx, pl)][:2]
    for s in dict.fromkeys(shorts):
        rec = re.search(r"recommend|what should|fix|mitigat|solve|action|do about|resolve", pl)
        if rec:
            out.append(("recommend", s))
        if not rec or re.search(r"\bwhy\b|explain|cause|reason|happen", pl):
            out.append(("explain", s))
    if sup_ids and re.search(r"exceed|over[- ]capacity|above capacity|capacity", pl) and re.search(r"\bwhy\b|explain|reason|cause|how come|exceed", pl):
        out.append(("capacity_why", tuple(sup_ids)))
    eligibility = sup_ids and re.search(r"can (?:i|we)|could (?:i|we)|eligible|allowed|able to|possible|ok to|safe to|either|both", pl) and re.search(r"order|\bpo\b|purchase|buy|source", pl)
    if eligibility:
        out.append(("eligibility", tuple(sup_ids)))
    if sup_ctx and re.search(ORDER_WORDS, pl) and re.search(RANK_WORDS, pl) and not (eligibility and not re.search(r"riskiest|safest|\bbest\b|choose|recommend|which", pl)):
        out.append(("po_choice", ("riskiest" if re.search(RISKY_WORDS, pl) else "safest", sku, fam)))
    elif sup_ctx and re.search(r"disruption", pl) and not any(k == "term" for k, _ in out):
        out.append(("disruption", None))
    if breakdown:
        out.append(("breakdown", (tuple(sup_ids), define)))
    specific = any(k in ("po_choice", "breakdown", "disruption", "term", "capacity_why", "eligibility") for k, _ in out)
    if not specific and not shorts:
        if sup_ids:
            out += [("supplier", s) for s in sup_ids]
        elif sup_ctx and re.search(r"problem|worst|risk|late|delay|poor|bad|weak|issue|underperform|unreliab", pl):
            out.append(("suppliers", None))
        elif re.search(r"at risk|risk of|early warning|potential shortage|could (?:run|stock|become)|risk score|risky sku|risk", pl) and not re.search(r"locations? (?:have|with)|which locations", pl):
            out.append(("risk", None))
        elif re.search(r"location|warehouse|store|site|\bdc\b|plant", pl) and re.search(r"problem|worst|most|issue|short", pl):
            out.append(("locations", None))
        elif re.search(r"top|worst|critical|priorit|urgent|biggest", pl) and re.search(r"shortage", pl):
            out.append(("top", int(re.search(r"\b(\d{1,2})\b", pl).group(1)) if re.search(r"\b(\d{1,2})\b", pl) else 10))
        elif re.search(r"overview|summary|status|how are we|kpi|health", pl):
            out.append(("overview", None))
    return out


def _answer_suppliers(a) -> list:
    """The supplier list an answer is *about* (its canonical referent), falling back to supplier sources."""
    a = a.get("a") if isinstance(a, dict) else a
    s = (getattr(a, "facts", None) or {}).get("suppliers") or [x for x in (getattr(a, "sources", None) or []) if isinstance(x, str) and x.startswith("SUP-")]
    return list(dict.fromkeys(s))


def _prev_suppliers(history: list | None, n: int | None = None) -> list:
    """Most recent earlier answer about suppliers.  With a count ('those five suppliers') the most recent answer about
    exactly n suppliers wins; otherwise the most recent answer about at least n suppliers (first n)."""
    fallback = []
    for a in reversed(history or []):
        s = _answer_suppliers(a)
        if not s:
            continue
        if n is None or len(s) == n:
            return s
        if len(s) > n and not fallback:
            fallback = s[:n]
    return fallback


def _run(ctx: Ctx, name: str, arg, part: str, history: list | None, state: dict) -> Answer:
    if name == "whatif":
        return whatif(ctx, arg)
    if name == "explain":
        return explain_shortage(ctx, arg)
    if name == "recommend":
        return recommend(ctx, arg)
    if name == "term":
        return explain_term(ctx, arg)
    if name == "breakdown":
        sids, define = arg
        if sids:
            a = supplier_breakdown(ctx, list(sids), why="the requested suppliers", define=define)
        else:
            n = _count(part)
            prev = state.get("suppliers") or _prev_suppliers(history, _count(part, None))
            if REFERENTIAL.search(part.lower()) and prev:
                a = supplier_breakdown(ctx, prev[:n], why=f"the {len(prev[:n])} suppliers from the previous answer", define=define)
            else:
                a = supplier_breakdown(ctx, None, n, define=define)
        state["suppliers"] = a.facts.get("suppliers", [])
        return a
    if name == "capacity_why":
        return capacity_exceedance(ctx, list(arg))
    if name == "eligibility":
        return order_eligibility(ctx, list(arg))
    if name == "po_choice":
        mode, sku, fam = arg
        referential = REFERENTIAL.search(part.lower()) or re.search(r"\bof (?:the|those|these)\b", part.lower())
        focus = state.get("suppliers") or (_prev_suppliers(history, _count(part, None)) if referential else [])
        a = po_supplier_choice(ctx, mode, focus, sku, fam)
        if referential and not focus:  # never silently swap the referent
            a.text = ("_Note: I could not find an earlier answer about the suppliers you referred to, so this compares all eligible suppliers instead._\n\n" + a.text)
            a.facts["referent_missing"] = True
        return a
    if name == "disruption":
        return supplier_disruption(ctx)
    if name == "supplier":
        return supplier_info(ctx, arg)
    if name == "suppliers":
        a = problematic_suppliers(ctx)
        state["suppliers"] = list(a.facts.get("suppliers", a.sources))
        return a
    if name == "risk":
        return risk_top(ctx)
    if name == "locations":
        return problematic_locations(ctx)
    if name == "top":
        return top_shortages(ctx, arg)
    return overview(ctx)


def ask(ctx: Ctx, question: str, use_llm: bool = False, history: list | None = None) -> Answer:
    """Split the question into parts, answer every recognised intent, and report any part that could not be answered.
    `history` = previous Answers (or {'q','a'} dicts) so follow-ups such as 'these suppliers' resolve to real IDs."""
    q = question.strip()
    ids = ID_RE.findall(q)
    unknown = [i for i in ids if i not in ctx.universe]
    if unknown:
        return Answer(f"I can't find {', '.join(unknown)} in the dataset, so I won't guess. " + CAPS, "not_found")
    parts = _split(q) or [q]
    plan, uncovered, seen = [], [], set()
    for p in parts:
        its = _intents(p)
        if not its:
            uncovered.append(p)
        for it in its:
            k = (it[0], str(it[1]))
            if k not in seen:
                seen.add(k)
                plan.append((it[0], it[1], p))
    if not plan:
        return Answer(CAPS, "help")
    state: dict = {}
    answers = [(name, _run(ctx, name, arg, p, history, state)) for name, arg, p in plan]
    if len(answers) == 1 and not uncovered:
        a = answers[0][1]
    else:
        f = Facts()
        sections, sources, checks = [], [], []
        for i, (name, a) in enumerate(answers, start=1):
            f.nums |= a.nums
            sections.append(f"### Part {f.n(i)}: {LABELS.get(name, name)}\n\n{a.text}")
            sources += [s for s in a.sources if s not in sources]
            checks += a.checks
        if uncovered:
            reg(f, " ".join(uncovered))  # the user's own words, quoted back
            sections.append("### Not answered\n\nI could not map these part(s) to a data lookup, so I did not answer them rather than guess:\n"
                            + "\n".join(f"- \"{u}\"" for u in uncovered) + "\n\n" + CAPS_SHORT)
        text = "\n\n".join(sections)
        ok, bad = verify_grounded(text, ctx, f)
        ok = ok and all(a.grounded for _, a in answers)
        bad = bad + [b for _, a in answers for b in a.ungrounded]
        a = Answer(text, "multi", {"parts": [n for n, _ in answers], "sub_kinds": [x.kind for _, x in answers]}, sources, checks, ok, bad, f.nums, uncovered)
    if use_llm and llm_available() and a.grounded:
        a = llm_rephrase(ctx, q, a)
    return a


def llm_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def llm_rephrase(ctx: Ctx, question: str, a: Answer) -> Answer:  # pragma: no cover - requires network/key
    """Optional: ask an LLM to restate the deterministic answer.  Accepted only if it passes the grounding check."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(model=os.environ.get("ORYVA_LLM_MODEL", "claude-sonnet-5-5"), max_tokens=900,
                                     system="Rewrite the given supply-chain answer for a planner. Use ONLY the facts, identifiers and numbers in it. Never add or change any value.",
                                     messages=[{"role": "user", "content": f"Question: {question}\n\nFacts:\n{a.text}"}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        f = Facts()
        f.nums |= {round(float(x.replace(",", "")), d) for x in NUM_RE.findall(ID_RE.sub(" ", DATE_RE.sub(" ", a.text))) for d in (0, 1, 2) if x.replace(",", "").replace(".", "", 1).replace("-", "", 1).isdigit()}
        ok, bad = verify_grounded(text, ctx, f)
        if ok:
            return Answer(text, a.kind, a.facts, a.sources, a.checks, True, [], f.nums, a.not_covered)
        a.text += "\n\n_(LLM rewrite rejected by the grounding check; showing the verified answer.)_"
    except Exception as e:  # network / key problems must never break the verified answer
        a.text += f"\n\n_(LLM rewrite unavailable: {type(e).__name__}.)_"
    return a

