"""Unit tests: IDs, calendar, schema/dictionary, config."""
import re

from oryva import ids, schema, weeks as W
from oryva.config import load_profile, rng


def test_id_patterns_zero_padded_and_consistent():
    assert ids.sku(1) == "SKU-000001" and ids.matches("sku_id", "SKU-000001")
    assert ids.po(1) == "PO-2026-000001" and ids.matches("po_id", ids.po(10000))
    assert ids.short(1) == "SHORT-2026-000001"
    s = ids.short(7)
    assert ids.mit(s, 1) == "MIT-SHORT-2026-000007-01" and ids.matches("mitigation_id", ids.mit(s, 1))
    d = ids.dem(ids.sku(12), ids.loc(3), "2026W01")
    assert d == "DEM-SKU-000012-LOC-003-2026W01" and ids.matches("demand_id", d)
    assert not ids.matches("sku_id", "SKU-1")


def test_calendar_2026W01_is_monday_2025_12_29():
    assert W.week_start_s(1) == "2025-12-29" and W.label(1) == "2026W01"
    assert W.label(52) == "2026W52" and W.week_start_s(52) == "2026-12-21"
    assert W.week_of("2026-01-04") == 1 and W.week_of("2026-01-05") == 2 and W.week_of("2025-12-28") == 0


def test_every_field_has_dictionary_entry():
    for r in schema.dictionary_rows():
        for k in ("type", "required", "allowed_values", "unit", "uniqueness", "validation_rule"):
            assert str(r[k]).strip() != "", (r["table"], r["field"], k)
    for core in schema.CORE:
        assert core in schema.T


def test_ddl_has_pk_and_fk_for_every_table():
    ddl = schema.ddl()
    for name in schema.ALL_TABLES:
        assert f'CREATE TABLE "{name}"' in ddl
    assert ddl.count("PRIMARY KEY") == len(schema.ALL_TABLES)
    assert ddl.count("FOREIGN KEY") > 40


def test_named_rng_streams_are_stable_and_independent():
    a1 = rng(20261022, "demand").random(3).tolist()
    a2 = rng(20261022, "demand").random(3).tolist()
    b = rng(20261022, "supplier").random(3).tolist()
    assert a1 == a2 and a1 != b


def test_full_profile_matches_pdf_volumes_and_profiles_share_parameters():
    full = load_profile("full")
    assert (full["n_skus"], full["n_locations"], full["n_weeks"], full["n_suppliers"], full["n_purchase_orders"]) == (3000, 50, 52, 500, 10000)
    assert full["seed"] == 20261022
    for p in ("tiny", "starter"):
        assert set(load_profile(p)) == set(full)


def test_density_is_configurable_not_hardcoded():
    assert load_profile("full")["assortment_density"] == 0.10
    assert load_profile("full", ["assortment_density=0.25"])["assortment_density"] == 0.25
    src = open("src/oryva/datagen.py", encoding="utf-8").read()
    assert 'P["assortment_density"]' in src and not re.search(r"round\(0\.1\d?\s*\*\s*nS", src)
