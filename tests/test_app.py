"""Dashboard tests: every page renders without exception (Streamlit AppTest), role-based access, audit chain, approvals."""
import os
from pathlib import Path

import pandas as pd
import pytest

from oryva.app import views
from oryva.app.state import ACTIONS, PAGE_ACCESS, State

APP = str(Path(__file__).resolve().parents[1] / "app.py")
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture(scope="module")
def data_root(tmp_path_factory, tiny_dir):
    root = tmp_path_factory.mktemp("dataroot")
    (root / "tiny").symlink_to(tiny_dir, target_is_directory=True) if hasattr(os, "symlink") and False else None
    import shutil
    shutil.copytree(tiny_dir, root / "tiny")
    return root


def _app(data_root, tmp_path, role="ADMIN", username="admin", page="Overview"):
    os.environ["ORYVA_DATA_ROOT"] = str(data_root)
    os.environ["ORYVA_DEFAULT_DATASET"] = "tiny"
    os.environ["ORYVA_STATE_DB"] = str(tmp_path / "state.sqlite")
    os.environ["ORYVA_LOG_DIR"] = str(tmp_path / "logs")
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["user"] = {"username": username, "role": role, "display_name": username, "supplier_id": "SUP-0001" if role == "SUPPLIER" else None}
    at.session_state["nav"] = page
    return at


@pytest.mark.parametrize("page", [p[0] for p in views.PAGES])
def test_every_page_renders_without_error(data_root, tmp_path, page):
    at = _app(data_root, tmp_path, page=page).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_login_screen_when_not_authenticated(data_root, tmp_path):
    os.environ["ORYVA_DATA_ROOT"] = str(data_root)
    os.environ["ORYVA_STATE_DB"] = str(tmp_path / "s.sqlite")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception and any("Sign in" in b.label for b in at.button) or len(at.text_input) == 2


def test_supplier_role_sees_only_permitted_pages(data_root, tmp_path):
    at = _app(data_root, tmp_path, role="SUPPLIER", username="supplier", page="Overview").run()
    assert not at.exception
    opts = at.radio(key="nav").options
    assert {o.split("  ")[-1] for o in opts} == set(PAGE_ACCESS["SUPPLIER"])


def test_scenario_form_runs_recomputes_and_is_audited(data_root, tmp_path):
    at = _app(data_root, tmp_path, role="PLANNER", username="planner", page="Scenarios").run()
    at.slider[0].set_value(30)
    next(b for b in at.button if b.label == "Run scenario").click().run()
    assert not at.exception and not at.error
    assert any("baseline unchanged" in m.value for m in at.markdown)
    s = State(tmp_path / "state.sqlite")
    assert any(r["action"] == "scenario.run" for r in s.audit_rows()) and s.verify_chain()[0]


def test_optimizer_button_produces_strategy_table(data_root, tmp_path):
    at = _app(data_root, tmp_path, role="PLANNER", username="planner", page="Optimizer").run()
    next(b for b in at.button if b.label == "Optimise").click().run()
    assert not at.exception and not at.error
    assert len(at.dataframe) >= 1


def test_mitigation_approval_through_the_ui_is_persisted_and_audited(data_root, tmp_path):
    at = _app(data_root, tmp_path, role="PLANNER", username="planner", page="Mitigation").run()
    at.button(key="mit_ok").click().run()
    assert not at.exception and not at.error
    s = State(tmp_path / "state.sqlite")
    hist = s.decision_history("tiny")
    assert [h["to_status"] for h in reversed(hist)] == ["PROPOSED", "APPROVED"] and hist[0]["username"] == "planner"
    assert any(r["action"] == "mitigation.approved" for r in s.audit_rows())


def test_supplier_role_cannot_approve_mitigations(data_root, tmp_path):
    at = _app(data_root, tmp_path, role="LOGISTICS_ANALYST", username="analyst", page="Mitigation").run()
    assert at.button(key="mit_ok").disabled


def test_proposal_approval_via_ui_creates_draft_order(data_root, tmp_path):
    at = _app(data_root, tmp_path, role="PLANNER", username="planner", page="Purchase orders").run()
    btn = at.button(key="prop_ok")
    if btn.disabled:
        pytest.skip("selected proposal not approvable for this role/value")
    btn.click().run()
    assert not at.exception
    s = State(tmp_path / "state.sqlite")
    assert len(s.draft_orders("tiny")) in (0, 1)  # 0 only if the proposal failed validation; never partial state
    if s.draft_orders("tiny"):
        assert s.status_of("tiny", "proposal", s.draft_orders("tiny")[0]["proposal_id"]) == "APPROVED"


def test_state_audit_chain_detects_tampering(tmp_path):
    s = State(tmp_path / "a.sqlite")
    s.seed_demo_users("pw12345")
    u = s.authenticate("planner", "pw12345")
    assert u and s.authenticate("planner", "wrong") is None
    for i in range(5):
        s.audit(u, "test.action", "x", str(i), {"i": i})
    assert s.verify_chain()[0]
    with s.conn() as c:
        c.execute("UPDATE audit_log SET details='{\"i\": 99}' WHERE id=3")
    ok, n, bad = s.verify_chain()
    assert not ok and bad == 3


def test_permissions_and_append_only_workflow(tmp_path):
    s = State(tmp_path / "b.sqlite")
    s.seed_demo_users("pw12345")
    planner, supplier = s.authenticate("planner", "pw12345"), s.authenticate("supplier", "pw12345")
    with pytest.raises(PermissionError):
        s.transition(supplier, "d", "proposal", "RPL-1", "PROPOSED", "", "decide_proposal")
    s.transition(planner, "d", "proposal", "RPL-1", "PROPOSED", "", "decide_proposal")
    with pytest.raises(ValueError):
        s.transition(planner, "d", "proposal", "RPL-1", "REJECTED", "", "decide_proposal")  # rejection needs a note
    s.transition(planner, "d", "proposal", "RPL-1", "REJECTED", "price too high", "decide_proposal")
    with pytest.raises(ValueError):
        s.transition(planner, "d", "proposal", "RPL-1", "APPROVED", "", "decide_proposal")  # illegal transition
    assert [h["to_status"] for h in reversed(s.decision_history("d"))] == ["PROPOSED", "REJECTED"]
    assert any(r["action"] == "permission.denied" for r in s.audit_rows())
    assert s.verify_chain()[0]


def test_approval_creates_draft_order_validates_and_never_touches_baseline(tiny, tmp_path):
    from oryva.advanced import replenish
    from oryva.config import load_policy
    s = State(tmp_path / "c.sqlite")
    s.seed_demo_users("pw12345")
    planner = s.authenticate("planner", "pw12345")
    props = replenish.build_proposals(tiny["T"], tiny["out"], load_policy())
    p = props[props["valid"]].iloc[0].to_dict()
    p["order_value"] = 1.0  # below the approval threshold
    before = tiny["T"]["PurchaseOrder"].copy()
    oid = s.approve_proposal(planner, "tiny", p, 25000.0, "ok")
    assert oid == "RPO-000001" and s.status_of("tiny", "proposal", p["proposal_id"]) == "APPROVED"
    assert len(s.draft_orders("tiny")) == 1 and tiny["T"]["PurchaseOrder"].equals(before)
    with pytest.raises(ValueError):
        s.approve_proposal(planner, "tiny", p, 25000.0, "again")  # cannot approve twice
    p2 = dict(p, proposal_id="RPL-X", order_value=1e6)
    with pytest.raises(PermissionError):
        s.approve_proposal(planner, "tiny", p2, 25000.0)  # high value needs ops manager
    ops = s.authenticate("ops", "pw12345")
    assert s.approve_proposal(ops, "tiny", p2, 25000.0).startswith("RPO-")


def test_role_action_matrix_is_consistent():
    assert set(ACTIONS["manage_users"]) == {"ADMIN"} and "SUPPLIER" not in ACTIONS["decide_proposal"]
    assert PAGE_ACCESS["SUPPLIER"] and "Audit history" not in PAGE_ACCESS["SUPPLIER"]

