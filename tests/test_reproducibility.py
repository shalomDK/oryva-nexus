"""Fixed-seed reproducibility: regenerate twice, compare row counts and SHA-256 checksums (PDF Step 10)."""
from pathlib import Path

from oryva.pipeline import build, reproducibility


def test_same_seed_gives_identical_row_counts_and_checksums(tmp_path):
    res = reproducibility("tiny", tmp_path, quiet=True)
    assert res["ok"], res["mismatches"]
    assert res["files"] > 100


def test_different_seed_changes_data_but_still_validates(tmp_path):
    a = build("tiny", tmp_path / "a", quiet=True)
    b = build("tiny", tmp_path / "b", ["seed=20261023"], quiet=True)
    assert a["manifest"]["files"]["csv/ForecastDemand.csv"]["sha256"] != b["manifest"]["files"]["csv/ForecastDemand.csv"]["sha256"]
    assert b["report"].unexpected_failures == 0 and b["eval"]["all_detection_perfect"]


def test_ids_are_identical_across_regenerations():
    a = build("tiny", None, quiet=True)["T"]
    b = build("tiny", None, quiet=True)["T"]
    for t in ("SKU", "PurchaseOrder", "ForecastDemand", "SupplierCapacity", "LeadTime"):
        assert a[t].equals(b[t]), t
