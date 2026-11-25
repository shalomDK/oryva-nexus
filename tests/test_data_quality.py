"""Generated-data tests: counts, assortment coverage, validators (positive + negative), reconciliation."""
from oryva.config import load_profile
from oryva.datagen import generate_baseline
from oryva.validate import validate


def test_clean_baseline_has_zero_failures(tiny):
    assert all(r["failed"] == 0 for r in tiny["baseline_report"].rows)


def test_final_data_zero_unexpected_failures_and_exact_labelled_set(tiny):
    assert tiny["report"].unexpected_failures == 0
    assert tiny["eval"]["all_validator_reconciled"]


def test_row_counts_follow_profile(tiny):
    P, T = tiny["P"], tiny["T"]
    assert len(T["SKU"]) == P["n_skus"] and len(T["Location"]) == P["n_locations"]
    assert len(T["Supplier"]) == P["n_suppliers"] and len(T["PurchaseOrder"]) == P["n_purchase_orders"]


def test_all_skus_and_locations_represented_and_52_weeks_for_active_pairs(tiny):
    T = tiny["T"]
    sl, fd = T["SKULocation"], T["ForecastDemand"]
    act = sl[sl["stocking_status"] == "ACTIVE"]
    assert set(act["sku_id"]) == set(T["SKU"]["sku_id"])
    assert set(act["location_id"]) == set(T["Location"]["location_id"])
    cnt = fd.groupby(["sku_id", "location_id"])["iso_week"].nunique()
    assert len(cnt) == len(act) and (cnt == 52).all()
    ina = sl[sl["stocking_status"] == "INACTIVE"]
    assert not set(zip(ina["sku_id"], ina["location_id"])) & set(cnt.index)


def test_density_parameter_changes_assortment():
    # (make-SKUs and components are only stocked at plants, so the structural maximum for tiny is ~0.67)
    lo = load_profile("tiny", ["assortment_density=0.3", "n_purchase_orders=120"])
    hi = load_profile("tiny", ["assortment_density=0.6", "n_purchase_orders=120"])
    a = generate_baseline(lo, 0)[1]
    b = generate_baseline(hi, 0)[1]
    assert b["n_pairs_total"] > a["n_pairs_total"] * 1.7
    assert abs(a["actual_assortment_density"] - 0.3) < 0.05 and abs(b["actual_assortment_density"] - 0.6) < 0.05


def test_pab_reconciles_week_by_week(tiny):
    pb = tiny["out"]["ProjectedBalance"]
    res = pb["closing_qty"] - (pb["opening_qty"] + pb["scheduled_receipts_qty"] + pb["production_receipts_qty"]
                               - pb["gross_demand_qty"] - pb["dependent_demand_qty"])
    assert (res == 0).all()
    pb = pb.sort_values(["sku_id", "location_id", "week_start_date"])
    prev = pb.groupby(["sku_id", "location_id"])["closing_qty"].shift(1)
    assert (pb["opening_qty"][prev.notna()] == prev[prev.notna()]).all()


def test_every_shortage_has_explainable_causes_that_sum_to_quantity(tiny):
    o = tiny["out"]
    cs = o["ShortageCause"].groupby("shortage_id")["contribution_qty"].sum()
    assert set(cs.index) == set(o["Shortage"]["shortage_id"])
    assert (cs.reindex(o["Shortage"]["shortage_id"]).values == o["Shortage"]["shortage_qty"].values).all()
    assert o["ShortageCause"]["source_id"].notna().all()


def test_mitigations_respect_policy_capacity_and_show_tradeoffs(tiny):
    mo, sh = tiny["out"]["MitigationOption"], tiny["out"]["Shortage"]
    rec = mo[mo["is_recommendable"] == 1]
    assert (rec["policy_check"] == "PASS").all() and (rec["capacity_check"] != "FAIL").all() and (rec["lead_time_check"] != "MISSING").all()
    assert (mo.groupby("shortage_id").size() >= 2).all()
    assert mo[["total_cost", "fill_rate_pct", "cost_delta_vs_baseline"]].notna().all().all()
    assert (mo[mo["is_recommended"] == 1].groupby("shortage_id").size() == 1).all()
    assert mo["shortage_id"].isin(sh["shortage_id"]).all()


def test_mitigation_ids_follow_shortage_ids(tiny):
    mo = tiny["out"]["MitigationOption"]
    assert (mo["mitigation_id"].str[4:-3] == mo["shortage_id"]).all()


def test_history_is_append_only_and_lifecycle_valid(tiny):
    T = tiny["T"]
    po, ev = T["PurchaseOrder"], T["PurchaseOrderEvent"].sort_values("event_id")
    last = ev.groupby("po_id")["to_status"].last()
    assert (po.set_index("po_id")["status"] == last.reindex(po["po_id"]).values).all()
    assert (ev["event_date"] <= tiny["P"]["as_of_date"]).all()


def test_dates_valid(tiny):
    po = tiny["T"]["PurchaseOrder"]
    assert (po["created_date"] <= po["order_date"]).all() and (po["order_date"] <= po["requested_date"]).all()
    assert (po["requested_date"] <= po["promised_date"]).all() and (po["promised_date"] <= po["eta_date"]).all()


# ------------------------------------------------------------------ validator negative tests: it must catch corruption
def _fails(tiny, mutate, check):
    T = {**{k: v.copy() for k, v in tiny["T"].items()}, **{k: v.copy() for k, v in tiny["out"].items()}}
    mutate(T)
    fr = validate(T, tiny["P"]).frame()
    return len(fr[(fr["check"] == check) & (fr["status"] == "FAIL")]) > 0


def test_validator_catches_broken_foreign_key(tiny):
    def m(T):
        T["PurchaseOrder"].loc[0, "supplier_id"] = "SUP-9999"
    assert _fails(tiny, m, "fk.supplier_id->Supplier.supplier_id")


def test_validator_catches_duplicate_primary_key(tiny):
    def m(T):
        T["SKU"].loc[1, "sku_id"] = T["SKU"].loc[0, "sku_id"]
    assert _fails(tiny, m, "pk.unique")


def test_validator_catches_bad_enum_and_pattern(tiny):
    def m(T):
        T["Supplier"].loc[0, "status"] = "BOGUS"
        T["PurchaseOrder"].loc[0, "po_id"] = "PO-1"
    assert _fails(tiny, m, "enum.status") and _fails(tiny, m, "pattern.po_id")


def test_validator_catches_date_ordering(tiny):
    def m(T):
        T["PurchaseOrder"].loc[0, "promised_date"] = "2020-01-01"
    assert _fails(tiny, m, "dates.PO.requested_date<=promised_date")


def test_validator_catches_arithmetic_and_pab_breaks(tiny):
    def m(T):
        T["Inventory"].loc[0, "available_qty"] += 1
        T["ProjectedBalance"].loc[5, "closing_qty"] += 7
    assert _fails(tiny, m, "arith.Inventory.available") and _fails(tiny, m, "accept.PAB_identity_each_week")


def test_validator_catches_illegal_lifecycle_transition(tiny):
    def m(T):
        ev = T["PurchaseOrderEvent"]
        i = ev.index[ev["event_type"] == "CONFIRMED"][0]
        ev.loc[i, "to_status"] = "RECEIVED"
    assert _fails(tiny, m, "PurchaseOrderEvent.transitions_allowed")


def test_validator_catches_missing_demand_week(tiny):
    def m(T):
        T["ForecastDemand"] = T["ForecastDemand"].iloc[1:].reset_index(drop=True)
    assert _fails(tiny, m, "coverage.active_pair_has_52_weeks")


def test_validator_catches_shortage_without_cause(tiny):
    def m(T):
        T["ShortageCause"] = T["ShortageCause"].iloc[1:].reset_index(drop=True)
    assert _fails(tiny, m, "accept.every_shortage_has_a_cause")


def test_validator_catches_unapproved_substitute_recommended(tiny):
    def m(T):
        mo, sh = T["MitigationOption"], T["Shortage"]
        i = mo.index[(mo["option_type"] == "PARTIAL_FILL_BACKORDER") & (mo["is_recommendable"] == 1)][0]
        mo.loc[i, "option_type"] = "SUBSTITUTE_SKU"
        sku = sh.set_index("shortage_id").at[mo.at[i, "shortage_id"], "sku_id"]
        mo.loc[i, "alt_sku_id"] = [s for s in T["SKU"]["sku_id"] if s != sku][0]
    assert _fails(tiny, m, "accept.recommendable_substitutes_are_approved")
