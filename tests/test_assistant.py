"""AI assistant grounding: answers come from data, unknown IDs are refused, fabricated text is caught."""
import re

import pytest

from oryva.advanced import assistant as A
from oryva.advanced.assistant import Ctx, Facts, ask, validate_option, verify_grounded
from oryva.config import load_policy


@pytest.fixture(scope="module")
def ctx(tiny):
    return Ctx(tiny["T"], tiny["out"], load_policy())


def test_explanation_cites_real_sources_and_is_grounded(ctx):
    sid = ctx.out["Shortage"].sort_values("priority_rank")["shortage_id"].iloc[0]
    a = ask(ctx, f"Why does {sid} happen?")
    assert a.kind == "explain" and a.grounded and not a.ungrounded
    row = ctx.out["Shortage"].set_index("shortage_id").loc[sid]
    assert row["sku_id"] in a.text and row["location_id"] in a.text and f"{int(row['shortage_qty']):,}" in a.text
    causes = ctx.out["ShortageCause"].query("shortage_id == @sid")
    for src in causes["source_id"]:
        assert src in a.text
    assert set(A.ID_RE.findall(a.text)) <= ctx.universe


def test_unknown_ids_are_refused_not_invented(ctx):
    a = ask(ctx, "Why does SHORT-2026-999999 happen?")
    assert a.kind == "not_found" and "won't guess" in a.text
    a = ask(ctx, "tell me about SUP-9999")
    assert a.kind == "not_found"


def test_recommendation_is_validated_against_source_tables(ctx):
    sid = ctx.out["Shortage"].sort_values("priority_rank")["shortage_id"].iloc[0]
    a = ask(ctx, f"What should we do about {sid}?")
    assert a.kind == "recommend" and a.grounded and a.checks
    assert "Validation against the planning data" in a.text
    assert all(c["ok"] for c in a.checks) == a.facts["valid"]


def test_every_recommended_option_passes_independent_validation(ctx):
    mo = ctx.out["MitigationOption"]
    rec = mo[(mo["is_recommended"] == 1) & (mo["option_type"] != "PARTIAL_FILL_BACKORDER")]
    fails = [m for m in rec["mitigation_id"].head(60) if not all(c["ok"] for c in validate_option(ctx, m))]
    assert fails == []


def test_grounding_check_catches_fabricated_facts(ctx):
    f = Facts()
    ok, bad = verify_grounded("SHORT-2026-999999 is short by 12,345 units at LOC-999", ctx, f)
    assert not ok and "SHORT-2026-999999" in bad and "LOC-999" in bad and "12,345" in bad
    sid = ctx.out["Shortage"]["shortage_id"].iloc[0]
    ok, bad = verify_grounded(f"{sid} is short by 987654 units", ctx, Facts())
    assert not ok and "987654" in bad
    f2 = Facts()
    txt = f"{sid} is short by {f2.n(int(ctx.out['Shortage']['shortage_qty'].iloc[0]))} units"
    assert verify_grounded(txt, ctx, f2)[0]


def test_supplier_and_location_questions_use_real_rankings(ctx):
    a = ask(ctx, "Which suppliers are problematic?")
    assert a.kind == "suppliers" and a.grounded and set(a.sources) <= set(ctx.T["Supplier"]["supplier_id"])
    low = ctx.card[ctx.card["committed_orders"] >= 3].sort_values(["score", "supplier_id"])["supplier_id"].iloc[0]
    assert low in a.sources
    b = ask(ctx, "Which locations have the most shortage problems?")
    assert b.kind == "locations" and b.grounded and set(b.sources) <= set(ctx.T["Location"]["location_id"])


def test_overview_numbers_equal_computed_kpis(ctx):
    from oryva.advanced.kpi import plan_kpis
    a = ask(ctx, "give me an overview of the plan status")
    k = plan_kpis(ctx.out)
    assert a.grounded and f"{k['shortages']:,}" in a.text and f"{k['shortage_units']:,}" in a.text


def test_whatif_question_runs_engine_and_leaves_baseline_untouched(ctx):
    before = ctx.out["Shortage"].copy()
    a = ask(ctx, "what if demand increases by 30%?")
    assert a.kind == "whatif" and a.grounded and "baseline unchanged" in a.text
    assert ctx.out["Shortage"].equals(before)


@pytest.mark.parametrize("q,kind", [
    ("Give me an overview of the plan", "overview"), ("Which suppliers are problematic?", "suppliers"),
    ("Which locations have the most shortage problems?", "locations"), ("Which SKU-locations are at risk of shortage?", "risk"),
    ("What if demand increases by 20%?", "whatif"), ("What if demand drops by 10% and capacity falls by 20%?", "whatif"),
    ("What if transport delays add 7 days?", "whatif"), ("show the top 5 shortages", "top"), ("tell me about SUP-0001", "supplier")])
def test_every_supported_question_type_is_grounded(ctx, q, kind):
    a = ask(ctx, q)
    assert a.kind == kind and a.grounded, (q, a.ungrounded)


def test_whatif_direction_words_set_sign(ctx):
    from oryva.advanced.assistant import whatif  # noqa: F401
    a = ask(ctx, "What if demand drops by 10%?")
    assert "x0.9" in a.text


def test_unsupported_question_returns_help_without_facts(ctx):
    a = ask(ctx, "what is the weather tomorrow?")
    assert a.kind == "help" and not a.sources and re.search(r"I can answer", a.text)

