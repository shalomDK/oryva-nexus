"""Assistant: multi-part questions, supplier breakdowns, definitions, new-PO supplier choice, follow-up context, and
regression tests for every pre-existing handler.  Grounding/verification must stay as strict as before."""
import re

import pandas as pd
import pytest

from oryva.advanced import assistant as A
from oryva.advanced import risk, supplier_intel
from oryva.advanced.assistant import Ctx, Facts, ask, verify_grounded
from oryva.config import load_policy

USER_Q = ("For all five suppliers, provide the complete breakdown of every scoring component, including fulfilment percentage, on-time delivery, "
          "delay performance, capacity headroom and shortage exposure. Explain the meaning of peak utilisation above 100%. Then identify which "
          "supplier would be the riskiest choice for a new purchase order and justify your answer using the underlying data.")


@pytest.fixture(scope="module")
def ctx(tiny):
    return Ctx(tiny["T"], tiny["out"], load_policy())


# ------------------------------------------------------------------ the reported question
def test_reported_multi_part_question_answers_all_three_parts(ctx):
    prev = ask(ctx, "Which suppliers are problematic?")
    a = ask(ctx, USER_Q, history=[prev])
    assert a.kind == "multi" and a.facts["parts"] == ["breakdown", "term", "po_choice"]
    assert a.grounded and not a.ungrounded and not a.not_covered
    assert a.text != prev.text and all(c["ok"] for c in a.checks)
    assert "### Part 1" in a.text and "### Part 2" in a.text and "### Part 3" in a.text


def test_breakdown_shows_all_five_components_for_every_requested_supplier(ctx):
    prev = ask(ctx, "Which suppliers are problematic?")
    a = ask(ctx, USER_Q, history=[prev])
    part1 = a.text.split("### Part 2")[0]
    sups = [s for s in prev.sources if s.startswith("SUP-")]
    assert len(sups) == 5
    header = re.search(r"\| supplier_id \| score \| tier \|.*", part1).group(0)
    for col in ("on_time_pct", "fulfilment_pct", "delay_score", "capacity_score", "exposure_score"):
        assert col in header
    for col in ("on_time_pts", "fulfilment_pts", "delay_pts", "capacity_pts", "exposure_pts"):
        assert col in part1
    card = ctx.card.set_index("supplier_id")
    for s in sups:
        rows = [ln for ln in part1.splitlines() if ln.startswith(f"| {s} |")]
        assert len(rows) == 3, s  # component table, points table, underlying data table
        assert f"{card.at[s, 'fulfilment_pct']:,.2f}" in rows[0] and f"{card.at[s, 'on_time_pct']:,.2f}" in rows[0]


def test_peak_utilisation_definition_uses_live_data(ctx):
    a = ask(ctx, "Explain the meaning of peak utilisation above 100%.")
    assert a.kind == "term" and a.grounded
    over = ctx.card[ctx.card["peak_util_pct"] > 100]["supplier_id"]
    for s in over:
        assert s in a.text
    n_f = int((ctx.out["DataQualityFinding"]["issue_type"] == "SUPPLIER_CAPACITY_EXCEEDED").sum())
    assert f"**{n_f:,}** capacity-exceeded finding" in a.text
    assert all(c["ok"] for c in a.checks)  # documented headroom formula reproduces the stored component


@pytest.mark.parametrize("key", [t[0] for t in A.TERMS])
def test_every_term_has_a_documented_grounded_definition(ctx, key):
    a = A.explain_term(ctx, key)
    assert a.grounded and "no documented definition" not in a.text


def test_riskiest_supplier_matches_the_ranking_and_is_eligible(ctx):
    a = A.po_supplier_choice(ctx, "riskiest")
    t = A.po_risk_table(ctx)
    el = t[t["eligible"]]
    assert a.facts["pick"] == el.iloc[0]["supplier_id"] and a.grounded and all(c["ok"] for c in a.checks)
    pick = el.iloc[0]
    sup = ctx.T["Supplier"].set_index("supplier_id")
    assert sup.at[pick["supplier_id"], "status"] == "ACTIVE"
    dr = risk.supplier_disruption_risk(ctx.T, ctx.card).set_index("supplier_id")["disruption_risk"]
    assert (t.set_index("supplier_id")["disruption"] - dr.reindex(t["supplier_id"]).values).abs().max() < 1e-9
    comp = t["disruption"] + t["capacity_pressure"] + t["lead_time"] + t["missing_lead_time"]
    assert (comp - t["new_po_risk"]).abs().max() < 0.02


def test_new_po_table_accounts_for_capacity_commitments_and_lead_time(ctx):
    from oryva import dq
    t = A.po_risk_table(ctx).set_index("supplier_id")
    ws = dq.week_start_str(pd.Series([ctx.as_of])).iloc[0]
    led = ctx.out["SupplierCapacityLedger"]
    com = led[led["week_start_date"] == ws].groupby("supplier_id")["committed_qty"].sum()
    for s in t.index:
        assert t.at[s, "committed_now"] == com.get(s, 0)
        assert t.at[s, "remaining_now"] <= t.at[s, "capacity_now"]
    po = ctx.T["PurchaseOrder"]
    op = po[po["status"].isin(["PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED"])].groupby("supplier_id").size()
    assert (t["open_orders"] == op.reindex(t.index).fillna(0).astype(int)).all()
    lt = ctx.T["LeadTime"].groupby("supplier_id")["total_lead_days"].median()
    has = t["median_lead_days"].notna()
    assert (t.loc[has, "median_lead_days"] == lt.reindex(t.index[has])).all()


def test_ineligible_suppliers_are_never_recommended(ctx):
    T = dict(ctx.T)
    sup = T["Supplier"].copy()
    top = A.po_risk_table(ctx).query("eligible")["supplier_id"].iloc[0]
    sup.loc[sup["supplier_id"] == top, "status"] = "ON_HOLD"
    T["Supplier"] = sup
    c2 = Ctx(T, ctx.out, ctx.policy, ctx.card)
    a = A.po_supplier_choice(c2, "riskiest")
    assert a.facts["pick"] != top and f"{top} (supplier status ON_HOLD)" in a.text


def test_safest_choice_has_remaining_capacity(ctx):
    a = ask(ctx, "Which supplier is the safest choice for a new purchase order?")
    assert a.kind == "po_supplier" and a.facts["mode"] == "safest" and a.grounded
    t = A.po_risk_table(ctx).set_index("supplier_id")
    assert t.at[a.facts["pick"], "remaining_now"] > 0 and t.at[a.facts["pick"], "eligible"]


def test_sku_scoped_choice_only_uses_approved_suppliers_of_that_sku(ctx):
    sku = ctx.T["SKUSupplier"].query("approval_status == 'APPROVED'")["sku_id"].value_counts().index[0]
    a = ask(ctx, f"Which supplier is the riskiest choice for a new purchase order of {sku}?")
    ok = set(ctx.T["SKUSupplier"].query("sku_id == @sku and approval_status == 'APPROVED'")["supplier_id"])
    assert a.kind == "po_supplier" and a.facts["pick"] in ok and a.grounded


# ------------------------------------------------------------------ multi-intent mechanics
def test_unanswerable_part_is_reported_not_dropped(ctx):
    a = ask(ctx, "Give me an overview of the plan. Also tell me the weather in Paris tomorrow.")
    assert a.kind == "multi" and a.not_covered and "weather" in a.not_covered[0]
    assert "### Not answered" in a.text and a.grounded


def test_explain_and_recommend_in_one_sentence(ctx):
    sid = ctx.out["Shortage"].sort_values("priority_rank")["shortage_id"].iloc[0]
    a = ask(ctx, f"Explain why {sid} happens and recommend a fix")
    assert a.kind == "multi" and a.facts["sub_kinds"] == ["recommend", "explain"] and a.grounded


def test_follow_up_resolves_suppliers_from_previous_answer(ctx):
    prev = ask(ctx, "Which suppliers are problematic?")
    a = ask(ctx, "Show the score breakdown for these suppliers", history=[prev])
    assert a.kind == "supplier_breakdown" and a.facts["suppliers"] == [s for s in prev.sources if s.startswith("SUP-")]
    b = ask(ctx, "Show the score breakdown for these suppliers")  # no history: falls back to the documented default
    assert b.kind == "supplier_breakdown" and "lowest-scoring" in b.text


def test_breakdown_for_explicit_ids_and_counts(ctx):
    ids = list(ctx.card["supplier_id"].head(2))
    a = ask(ctx, f"Give the scoring component breakdown for {ids[0]} and {ids[1]}")
    assert a.kind == "supplier_breakdown" and a.facts["suppliers"] == ids
    b = ask(ctx, "score breakdown for three suppliers")
    assert len(b.facts["suppliers"]) == 3


def test_history_accepts_chat_dicts_like_the_ui(ctx):
    prev = ask(ctx, "Which suppliers are problematic?")
    a = ask(ctx, "breakdown of every scoring component for those suppliers", history=[{"q": "x", "a": prev}])
    assert a.facts["suppliers"] == [s for s in prev.sources if s.startswith("SUP-")]


# ------------------------------------------------------------------ safeguards are not weakened
def test_multi_answer_with_injected_fake_number_fails_verification(ctx):
    a = ask(ctx, USER_Q)
    f = Facts()
    f.nums |= a.nums
    ok, bad = verify_grounded(a.text + "\n\nSUP-0001 will deliver 987654 units tomorrow.", ctx, f)
    assert not ok and "987654" in bad


def test_unknown_ids_in_multi_part_questions_are_still_refused(ctx):
    a = ask(ctx, "Explain peak utilisation. Then give the breakdown for SUP-9999.")
    assert a.kind == "not_found" and "SUP-9999" in a.text


def test_breakdown_components_sum_to_score_checked(ctx):
    a = A.supplier_breakdown(ctx, None, 5)
    assert a.checks and all(c["ok"] for c in a.checks)
    for s in a.facts["suppliers"]:
        e = supplier_intel.explain_score(ctx.card, s)
        assert abs(e["contribution"].sum() - float(ctx.card.set_index("supplier_id").at[s, "score"])) < 0.06


# ------------------------------------------------------------------ regression: every pre-existing handler
def _sid(ctx):
    return ctx.out["Shortage"].sort_values("priority_rank")["shortage_id"].iloc[0]


@pytest.mark.parametrize("fn,kind", [("explain_shortage", "explain"), ("recommend", "recommend"), ("top_shortages", "top"), ("problematic_suppliers", "suppliers"),
                                     ("problematic_locations", "locations"), ("supplier_info", "supplier"), ("risk_top", "risk"), ("overview", "overview"),
                                     ("whatif", "whatif"), ("supplier_disruption", "disruption")])
def test_each_handler_directly(ctx, fn, kind):
    args = {"explain_shortage": (_sid(ctx),), "recommend": (_sid(ctx),), "top_shortages": (5,), "supplier_info": (ctx.card["supplier_id"].iloc[0],),
            "whatif": ("what if demand increases by 10%",)}.get(fn, ())
    a = getattr(A, fn)(ctx, *args)
    assert a.kind == kind and a.grounded and a.nums and not a.ungrounded


@pytest.mark.parametrize("q,kind", [
    ("Which suppliers are problematic?", "suppliers"), ("Which locations have the most shortage problems?", "locations"),
    ("Which SKU-locations are at risk of shortage?", "risk"), ("Give me an overview of the plan", "overview"), ("show the top 5 shortages", "top"),
    ("tell me about SUP-0001", "supplier"), ("What if demand increases by 20%?", "whatif"), ("what is the weather tomorrow?", "help"),
    ("Why does SHORT-2026-999999 happen?", "not_found"), ("Which suppliers have the highest disruption risk?", "disruption")])
def test_single_intent_questions_still_route_as_before(ctx, q, kind):
    a = ask(ctx, q)
    assert a.kind == kind and (a.grounded or kind in ("help", "not_found"))


def test_shortage_questions_still_route_as_before(ctx):
    sid = _sid(ctx)
    assert ask(ctx, f"Why does {sid} happen?").kind == "explain"
    assert ask(ctx, f"What should we do about {sid}?").kind == "recommend"


# ================================================================== follow-up sequence (reported failure)
P1 = "Show me the five most problematic suppliers, with every score component and what each component means."
P2 = "Why are SUP-0001 and SUP-0002 exceeding capacity, and can I place a new order with either?"
P3 = "Of those five suppliers, which would you choose for a new purchase order, and why?"


def _sequence(c):
    a1 = ask(c, P1)
    a2 = ask(c, P2, history=[a1])
    a3 = ask(c, P3, history=[a1, a2])
    return a1, a2, a3


def test_prompt1_is_only_a_breakdown_with_plain_definitions(ctx):
    assert A._intents(P1) == [("breakdown", ((), True))]
    a = ask(ctx, P1)
    assert a.kind == "supplier_breakdown" and a.grounded and all(c["ok"] for c in a.checks)
    assert "What each component means" in a.text
    for label in ("On-time delivery %", "Fulfilment %", "Delay score", "Capacity headroom", "Shortage exposure"):
        assert f"**{label}**" in a.text
    assert "New-purchase-order" not in a.text and "### Part" not in a.text and "Riskiest" not in a.text
    low5 = list(ctx.card[ctx.card["committed_orders"] >= 3].sort_values(["score", "supplier_id"]).head(5)["supplier_id"])
    assert a.facts["suppliers"] == low5


def test_plain_definition_thresholds_match_the_scoring_formula(ctx):
    c = ctx.card
    # "full marks up to 60% peak utilisation, falling to 0 at 100%": check against the stored component
    assert (c.loc[c["peak_util_pct"] <= 60, "capacity_score"] == 100).all()
    assert (c.loc[c["peak_util_pct"] >= 100, "capacity_score"] == 0).all()
    assert (c["delay_score"] <= 100).all() and (c["exposure_score"] <= 100).all()


def test_prompt2_answers_capacity_why_and_eligibility_only(ctx):
    assert [k for k, _ in A._intents(P2)] == ["capacity_why", "eligibility"]
    a = ask(ctx, P2)
    assert a.kind == "multi" and a.facts["parts"] == ["capacity_why", "eligibility"] and a.grounded and not a.not_covered
    assert all(c["ok"] for c in a.checks)
    assert "New-purchase-order supplier risk" not in a.text and "lowest-scoring suppliers" not in a.text
    led = ctx.out["SupplierCapacityLedger"]
    cap = ctx.T["SupplierCapacity"]
    for s in ("SUP-0001", "SUP-0002"):
        rows = led[(led["supplier_id"] == s) & (led["status"] == "EXCEEDED")]
        if rows.empty:
            assert f"**{s}** does not exceed capacity" in a.text
        for r in rows.itertuples():
            assert f"{r.committed_qty:,} units committed" in a.text and f"weekly capacity of {r.capacity_qty:,}" in a.text
            c = cap[(cap["supplier_id"] == s) & (cap["product_family"] == r.product_family) & (cap["effective_from"] <= r.week_start_date)
                    & (cap["effective_to"].isna() | (r.week_start_date < cap["effective_to"]))].sort_values("effective_from").iloc[-1]
            assert c["capacity_id"] in a.text  # the record in effect is named, not invented
    cn = A._capacity_now(ctx, ["SUP-0001", "SUP-0002"])
    for s in ("SUP-0001", "SUP-0002"):
        g = cn[cn["supplier_id"] == s]
        assert f"{int(g['committed_now'].sum()):,} committed of {int(g['capacity_now'].sum()):,} capacity" in a.text
        assert a.facts is not None
    sup = ctx.T["Supplier"].set_index("supplier_id")
    elig = [x for x in a.checks if "status in Supplier table" in x["check"]]
    assert {x["detail"] for x in elig} == {sup.at["SUP-0001", "status"], sup.at["SUP-0002", "status"]}


def test_prompt3_follow_up_keeps_the_five_suppliers_and_recommends_lowest_risk(ctx):
    a1, a2, a3 = _sequence(ctx)
    five = a1.facts["suppliers"]
    assert len(five) == 5 and a3.facts["suppliers"] == five  # not prompt 2's two suppliers
    assert a3.kind == "po_supplier" and a3.facts["mode"] == "safest" and a3.grounded and all(c["ok"] for c in a3.checks)
    t = A.po_risk_table(ctx)
    pool = t[t["supplier_id"].isin(five) & t["eligible"]]
    suitable = pool[(pool["remaining_now"] > 0) & (pool["missing_lead_time"] == 0)].sort_values(["new_po_risk", "supplier_id"])
    assert a3.facts["pick"] == suitable.iloc[0]["supplier_id"] and a3.facts["pick"] in five
    highest = pool.sort_values(["new_po_risk", "supplier_id"], ascending=[False, True]).iloc[0]["supplier_id"]
    assert f"**Best choice (lowest new-order risk): {a3.facts['pick']}**" in a3.text
    if highest != a3.facts["pick"]:
        assert f"**Highest risk (not recommended): {highest}**" in a3.text
    assert "Trade-offs versus the other suitable suppliers" in a3.text and "Riskiest eligible choice" not in a3.text


def test_follow_up_without_matching_context_says_so(ctx):
    a2 = ask(ctx, P2)
    a3 = ask(ctx, P3, history=[a2])  # only two suppliers were discussed: 'those five' cannot be resolved
    assert a3.facts.get("referent_missing") and a3.facts["suppliers"] == [] and "could not find an earlier answer" in a3.text
    assert a3.grounded


@pytest.mark.parametrize("q,expected", [
    ("Why are SUP-0001 and SUP-0002 exceeding capacity?", ["capacity_why"]),
    ("Can I place a new order with SUP-0001?", ["eligibility"]),
    ("Which supplier is the riskiest choice for a new purchase order?", ["po_choice"]),
    ("Which supplier would you choose for a new purchase order?", ["po_choice"]),
    ("Show me the five most problematic suppliers, with every score component and what each component means.", ["breakdown"]),
    ("Which suppliers are problematic?", ["suppliers"]),
    ("tell me about SUP-0001", ["supplier"]),
])
def test_parts_do_not_trigger_unrelated_handlers(q, expected):
    assert [k for k, _ in A._intents(q)] == expected


def test_choice_mode_follows_the_wording():
    assert A._intents("Which supplier would you choose for a new purchase order?")[0][1][0] == "safest"
    assert A._intents("Which supplier should I avoid for a new purchase order?")[0][1][0] == "riskiest"
    assert A._intents("Which supplier would be the riskiest choice for a new purchase order?")[0][1][0] == "riskiest"


def test_referent_resolution_prefers_the_answer_with_the_stated_count(ctx):
    a1, a2, _ = _sequence(ctx)
    assert A._prev_suppliers([a1, a2], 5) == a1.facts["suppliers"]
    assert A._prev_suppliers([a1, a2], 2) == ["SUP-0001", "SUP-0002"]
    assert A._prev_suppliers([a1, a2]) == ["SUP-0001", "SUP-0002"]  # no count: most recent


STARTER = __import__("pathlib").Path("data/starter")


@pytest.mark.skipif(not (STARTER / "manifest.json").exists(), reason="committed starter dataset not present")
def test_exact_sequence_on_the_committed_starter_dataset():
    from oryva.advanced.data import load_dataset
    ds = load_dataset(STARTER)
    c = Ctx(ds["T"], ds["out"], ds["policy"])
    a1, a2, a3 = _sequence(c)
    assert a1.kind == "supplier_breakdown" and a2.facts["parts"] == ["capacity_why", "eligibility"] and a3.facts["mode"] == "safest"
    assert all(x.grounded for x in (a1, a2, a3))
    led = ds["out"]["SupplierCapacityLedger"]
    for s in ("SUP-0001", "SUP-0002"):  # in this dataset both suppliers really do exceed capacity
        assert ((led["supplier_id"] == s) & (led["status"] == "EXCEEDED")).any() and f"**{s}** exceeds capacity" in a2.text
    assert a3.facts["pick"] != a3.facts["highest_risk"] or len(a3.facts["suppliers"]) == 1
