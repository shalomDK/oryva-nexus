"""Phase-5 verification: grounding over every shortage, scenario isolation on disk, no hard-coded dashboard metrics,
module independence from ground truth."""
import hashlib
import os
import re
import shutil
from pathlib import Path

import pytest

from oryva.advanced import assistant as A
from oryva.advanced.kpi import plan_kpis
from oryva.advanced.scenario import Scenario, simulate
from oryva.config import load_policy

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(scope="module")
def ctx(tiny):
    return A.Ctx(tiny["T"], tiny["out"], load_policy())


def test_assistant_grounded_for_every_shortage_explanation_and_recommendation(ctx):
    for sid in ctx.out["Shortage"]["shortage_id"]:
        for q in (f"why does {sid} happen", f"what should we do about {sid}"):
            a = A.ask(ctx, q)
            assert a.grounded, (sid, q, a.ungrounded)
            assert set(A.ID_RE.findall(a.text)) <= ctx.universe


def test_every_recommendation_shown_to_users_passed_validation_or_says_it_failed(ctx):
    for sid in ctx.out["Shortage"]["shortage_id"].head(40):
        a = A.ask(ctx, f"what should we do about {sid}")
        assert ("PASSED" in a.text) == bool(a.facts["valid"])


def test_scenario_does_not_touch_files_on_disk(tiny_dir):
    from oryva.advanced.data import load_dataset

    def digest():
        return {str(p.relative_to(tiny_dir)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(tiny_dir.rglob("*")) if p.is_file()}
    before = digest()
    ds = load_dataset(tiny_dir)
    simulate(ds["T"], ds["out"], Scenario(demand_multiplier=1.4, capacity_factor=0.6, transport_delay_days=10, lead_time_delta_days=7), ds["policy"])
    assert digest() == before


def test_dashboard_overview_numbers_come_from_the_data(data_root_overview):
    at, k = data_root_overview
    text = " ".join(m.value for m in at.markdown)
    assert f"{k['shortages']:,}" in text and f"{k['service_level_pct']:.2f}%" in text and f"{k['shortage_units']:,}" in text


@pytest.fixture(scope="module")
def data_root_overview(tmp_path_factory, tiny_dir, tiny):
    root = tmp_path_factory.mktemp("overview")
    shutil.copytree(tiny_dir, root / "tiny")
    tmp = tmp_path_factory.mktemp("st")
    os.environ.update(ORYVA_DATA_ROOT=str(root), ORYVA_DEFAULT_DATASET="tiny", ORYVA_STATE_DB=str(tmp / "s.sqlite"), ORYVA_LOG_DIR=str(tmp / "l"))
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["user"] = {"username": "admin", "role": "ADMIN", "display_name": "a", "supplier_id": None}
    at.session_state["nav"] = "Overview"
    at.run()
    assert not at.exception
    return at, plan_kpis(tiny["out"])


def test_no_hardcoded_numeric_kpis_in_views():
    """Dashboard code must compute KPIs from data: no literal service-level / cost / count figures in the view layer."""
    src = Path("src/oryva/app/views.py").read_text(encoding="utf-8")
    assert not re.search(r"value\"\s*:\s*[\"']\$?\d", src)  # no KPI card with a literal number
    assert not re.search(r"(service level|value at risk)[^\n]{0,40}\d{2,}\.\d", src, re.I)


def test_advanced_modules_do_not_read_ground_truth():
    for p in Path("src/oryva/advanced").glob("*.py"):
        assert not re.search(r"ground_truth|GROUND_TRUTH", p.read_text(encoding="utf-8")), p.name
    for p in Path("src/oryva/app").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "ground_truth/" not in text and "read_csv(" not in text.replace("pd.read_csv(p)", ""), p.name


def test_mandatory_pipeline_does_not_import_optional_modules():
    for m in ("planning", "datagen", "validate", "inject", "dq", "export", "pipeline", "evaluate", "schema"):
        text = Path(f"src/oryva/{m}.py").read_text(encoding="utf-8")
        assert "oryva.advanced" not in text and "from .advanced" not in text and "oryva.app" not in text and "streamlit" not in text, m
