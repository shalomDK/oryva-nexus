"""Streamlit entry: login, role-aware navigation, dataset selection, per-page error boundary, logging."""
from __future__ import annotations

import logging
import os
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

from . import cache, ui, views
from .state import PAGE_ACCESS, State

ROOT = Path(__file__).resolve().parents[3]
ICONS = {"Overview": "📊", "Inventory": "📦", "Demand": "📈", "Suppliers": "🏭", "Shortages": "⚠️", "Decision room": "⚖️", "Recovery planner": "🧩", "Stress test": "🧨", "Mitigation": "🛠️", "Purchase orders": "🧾", "Data quality": "🔎",
         "Scenarios": "🧪", "Risk": "🚨", "Optimizer": "🎯", "AI assistant": "🤖", "Reports": "📑", "Audit history": "🗂️"}


def _logger() -> logging.Logger:
    log = logging.getLogger("oryva.app")
    if not log.handlers:
        log.setLevel(logging.INFO)
        d = Path(os.environ.get("ORYVA_LOG_DIR", ROOT / "logs"))
        try:
            d.mkdir(parents=True, exist_ok=True)
            h = RotatingFileHandler(d / "oryva_app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(h)
        except OSError:
            log.addHandler(logging.StreamHandler())
    return log


@st.cache_resource
def _state_for(path: str) -> State:
    s = State(path)
    s.seed_demo_users()
    return s


def get_state() -> State:
    return _state_for(os.environ.get("ORYVA_STATE_DB", str(ROOT / "data" / "app_state.sqlite")))


def datasets() -> dict[str, Path]:
    root = Path(os.environ.get("ORYVA_DATA_ROOT", ROOT / "data"))
    found = {p.name: p for p in sorted(root.glob("*")) if (p / "manifest.json").exists() and not p.name.startswith("_")}
    extra = os.environ.get("ORYVA_DATA_DIR")
    if extra and (Path(extra) / "manifest.json").exists():
        found[Path(extra).name] = Path(extra)
    return found


def login_screen(state: State):
    ui.inject_css()
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<div style='margin-top:8vh'></div>", unsafe_allow_html=True)
        st.markdown("## ORYVA NEXUS")
        st.caption("AI-powered demand, inventory & supply planning")
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            ok = st.form_submit_button("Sign in", type="primary")
        if ok:
            user = state.authenticate(u.strip(), p)
            if user:
                st.session_state["user"] = {k: user[k] for k in ("username", "role", "display_name", "supplier_id")}
                state.audit(st.session_state["user"], "login", "user", user["username"], {})
                st.rerun()
            else:
                st.error("Invalid credentials.")
                _logger().warning("failed login for %s", u)
        st.caption("Local demo accounts: admin, ops, planner, analyst, warehouse, supplier - password from ORYVA_DEMO_PASSWORD (see README).")


def main():
    st.set_page_config(page_title="ORYVA NEXUS", page_icon="📦", layout="wide", initial_sidebar_state="expanded")
    log = _logger()
    state = get_state()
    user = st.session_state.get("user")
    if not user:
        login_screen(state)
        return
    ui.inject_css()
    ds_all = datasets()
    if not ds_all:
        ui.title("No dataset found", "")
        ui.empty("No exported dataset in the data folder.", "Run: python -m oryva generate --profile starter --out data/starter")
        return
    allowed = PAGE_ACCESS[user["role"]]
    pages = [(n, t, f) for (n, t, f) in views.PAGES if allowed is None or n in allowed]
    with st.sidebar:
        st.markdown("<div class='oryva-brand'>ORYVA NEXUS</div><div class='oryva-sub'>Supply planning cockpit</div>", unsafe_allow_html=True)
        st.write("")
        default = os.environ.get("ORYVA_DEFAULT_DATASET", "starter")
        names = list(ds_all)
        key = st.selectbox("Dataset", names, index=names.index(default) if default in names else 0, key="dataset")
        st.caption(f"{user['display_name']} - {user['role'].replace('_', ' ').title()}")
        nav = st.radio("Navigate", [n for n, _, _ in pages], format_func=lambda n: f"{ICONS.get(n, '')}  {n}", key="nav", label_visibility="collapsed")
        st.write("")
        if st.button("Sign out"):
            state.audit(user, "logout", "user", user["username"], {})
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
        st.caption("Baseline data is read-only. All changes are stored in the application state and audited.")
    path = str(ds_all[key])
    c = SimpleNamespace(path=path, key=key, user=user, state=state)
    try:
        c.ds = cache.get_ds(path)
    except Exception as e:
        log.error("dataset load failed: %s", traceback.format_exc())
        st.error(f"Could not load dataset '{key}': {e}")
        return
    page = next(f for n, _, f in pages if n == nav)
    try:
        page(c)
    except PermissionError as e:
        st.error(f"Not permitted: {e}")
    except Exception as e:  # error boundary: never show a stack trace to the user, always log it
        log.error("page %s failed: %s", nav, traceback.format_exc())
        st.error(f"This page could not be rendered ({type(e).__name__}: {e}). The error was logged.")
