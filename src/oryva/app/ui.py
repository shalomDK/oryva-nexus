"""Design system: CSS, KPI cards, charts, tables, empty states.  One consistent look for every page."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

PALETTE = {"primary": "#4F46E5", "teal": "#0D9488", "amber": "#D97706", "red": "#DC2626", "green": "#16A34A", "slate": "#475569", "light": "#EEF2FF"}
CATEGORY = ["#4F46E5", "#0D9488", "#D97706", "#DC2626", "#7C3AED", "#0891B2", "#65A30D", "#DB2777", "#475569", "#EA580C"]

CSS = """
<style>
:root { --primary:#4F46E5; --ink:#0F172A; --muted:#64748B; --card:#FFFFFF; --line:#E2E8F0; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }
h1, h2, h3 { letter-spacing:-0.01em; color:var(--ink); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0F172A 0%,#1E1B4B 100%); }
[data-testid="stSidebar"] * { color:#E2E8F0 !important; }
[data-testid="stSidebar"] .stRadio label p { font-size:0.92rem; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color:#0F172A !important; }
[data-testid="stSidebar"] button p { color:#0F172A !important; font-weight:600; }
.oryva-brand { font-weight:800; font-size:1.25rem; letter-spacing:.02em; color:#fff !important; }
.oryva-sub { font-size:.72rem; color:#A5B4FC !important; text-transform:uppercase; letter-spacing:.12em; }
.kpi-grid { display:flex; flex-wrap:wrap; gap:14px; margin: 4px 0 18px 0; }
.kpi { flex:1 1 190px; background:var(--card); border:1px solid var(--line); border-left:5px solid var(--primary); border-radius:12px;
       padding:14px 16px; box-shadow:0 1px 2px rgba(15,23,42,.05); min-width:170px; }
.kpi .label { font-size:.74rem; color:var(--muted); text-transform:uppercase; letter-spacing:.07em; font-weight:600; }
.kpi .value { font-size:1.65rem; font-weight:750; color:var(--ink); line-height:1.25; }
.kpi .note { font-size:.78rem; color:var(--muted); }
.kpi.good { border-left-color:#16A34A; } .kpi.warn { border-left-color:#D97706; } .kpi.bad { border-left-color:#DC2626; } .kpi.info { border-left-color:#0D9488; }
.page-title { font-size:1.7rem; font-weight:800; margin-bottom:0; color:var(--ink); }
.page-sub { color:var(--muted); margin-bottom:1rem; }
.badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.74rem; font-weight:650; }
.badge.ok { background:#DCFCE7; color:#166534; } .badge.bad { background:#FEE2E2; color:#991B1B; } .badge.warn { background:#FEF3C7; color:#92400E; } .badge.info { background:#E0E7FF; color:#3730A3; }
.empty { border:1px dashed #CBD5E1; border-radius:12px; padding:28px; text-align:center; color:var(--muted); background:#F8FAFC; }
.card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:14px 18px; margin-bottom:12px; }
@media (max-width: 760px) { .kpi { flex:1 1 140px; } .block-container { padding-left:.8rem; padding-right:.8rem; } .page-title { font-size:1.35rem; } }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def title(text: str, sub: str = ""):
    st.markdown(f"<div class='page-title'>{text}</div><div class='page-sub'>{sub}</div>", unsafe_allow_html=True)


def kpis(items: list[dict]):
    """items: [{label, value, note, tone}] rendered as responsive cards."""
    html = "<div class='kpi-grid'>" + "".join(
        f"<div class='kpi {i.get('tone', '')}'><div class='label'>{i['label']}</div><div class='value'>{i['value']}</div><div class='note'>{i.get('note', '')}</div></div>" for i in items) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def badge(text: str, tone: str = "info") -> str:
    return f"<span class='badge {tone}'>{text}</span>"


def empty(message: str, hint: str = ""):
    st.markdown(f"<div class='empty'><b>{message}</b><br><span>{hint}</span></div>", unsafe_allow_html=True)


def money(x: float) -> str:
    return f"${x:,.0f}" if abs(x) >= 1000 else f"${x:,.2f}"


def show_df(df: pd.DataFrame, height: int | None = None, column_config: dict | None = None, key: str | None = None):
    if df is None or len(df) == 0:
        empty("No rows match the current filters.", "Adjust or clear the filters above.")
        return
    kw = {"hide_index": True, "column_config": column_config}
    if height:
        kw["height"] = height
    try:
        st.dataframe(df, width="stretch", key=key, **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, key=key, **kw)


def show_chart(chart):
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def bar(df: pd.DataFrame, x: str, y: str, color: str | None = None, horizontal: bool = True, height: int = 280, title: str = "", sort: str | None = "-x"):
    enc_x, enc_y = (alt.X(f"{x}:Q", title=x.replace("_", " ")), alt.Y(f"{y}:N", sort=sort, title=None)) if horizontal else (alt.X(f"{x}:N", sort=sort, title=None), alt.Y(f"{y}:Q", title=y.replace("_", " ")))
    ch = alt.Chart(df, title=title).mark_bar(cornerRadiusEnd=3, color=PALETTE["primary"]).encode(x=enc_x, y=enc_y, tooltip=list(df.columns[:6]))
    if color:
        ch = ch.encode(color=alt.Color(f"{color}:N", scale=alt.Scale(range=CATEGORY), legend=alt.Legend(orient="bottom")))
    return ch.properties(height=height)


def line(df: pd.DataFrame, x: str, y: str, color: str | None = None, height: int = 280, title: str = "", rule: float | None = None, area: bool = False):
    base = alt.Chart(df, title=title)
    mark = base.mark_area(opacity=0.25, line={"color": PALETTE["primary"]}, color=PALETTE["primary"]) if area else base.mark_line(point=True, strokeWidth=2.2)
    ch = mark.encode(x=alt.X(f"{x}:N" if df[x].dtype == object else f"{x}:Q", title=None), y=alt.Y(f"{y}:Q", title=y.replace("_", " ")), tooltip=list(df.columns[:6]))
    if color:
        ch = ch.encode(color=alt.Color(f"{color}:N", scale=alt.Scale(range=CATEGORY), legend=alt.Legend(orient="bottom")))
    if rule is not None:
        ch = ch + alt.Chart(pd.DataFrame({"y": [rule]})).mark_rule(color=PALETTE["red"], strokeDash=[5, 4]).encode(y="y:Q")
    return ch.properties(height=height)


def scatter(df: pd.DataFrame, x: str, y: str, color: str, size: str | None = None, height: int = 300, title: str = ""):
    ch = alt.Chart(df, title=title).mark_circle(opacity=0.85).encode(
        x=alt.X(f"{x}:Q", title=x.replace("_", " ")), y=alt.Y(f"{y}:Q", title=y.replace("_", " ")),
        color=alt.Color(f"{color}:N", scale=alt.Scale(range=CATEGORY), legend=alt.Legend(orient="bottom")), tooltip=list(df.columns[:8]))
    if size:
        ch = ch.encode(size=alt.Size(f"{size}:Q", legend=None))
    return ch.properties(height=height)
