"""Streamlit dashboard (Chapter 3.1.2 / 6.2).

Read-only: queries daily_snapshots and guest_demo_snapshots directly via a
synchronous connection (psycopg2, already a project dependency) so this
stays fully decoupled from the FastAPI app's async engine. It never writes
to the database, and never touches per-user auth (materials are a shared,
unauthenticated list in the existing schema — only alert subscriptions are
tied to an API key), which is why the same page can show the daily brief,
guest mode, and the portfolio view without needing a login this semester.

Portfolio View deliberately does NOT lead with a single blended average
score across materials — that number is close to meaningless when the
underlying materials are unrelated (a steel-price spike and a stable
plastics score would average into "moderate," hiding the real signal).
The average appears only as a thin reference line; the real content is
per-material lines, colored by risk band.
"""

from __future__ import annotations

import io
import os
import sys
import textwrap
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import psycopg2
import psycopg2.extras
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snapshot.delta import compute_trend  # pure function — no async engine involved

load_dotenv()

RISK_BANDS = {
    "low": {"color": "#34d399", "label": "Low"},
    "moderate": {"color": "#fbbf24", "label": "Moderate"},
    "elevated": {"color": "#f87171", "label": "Elevated"},
}
TREND_META = {
    "rising": {"arrow": "▲", "color": "#f87171"},
    "falling": {"arrow": "▼", "color": "#34d399"},
    "unchanged": {"arrow": "—", "color": "#8b96a5"},
}
PAGES = ["Daily Brief", "Guest Mode", "Portfolio View"]


def _risk_band(score: int) -> dict:
    if score >= 70:
        return RISK_BANDS["elevated"]
    if score >= 40:
        return RISK_BANDS["moderate"]
    return RISK_BANDS["low"]


def _sync_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://")


@st.cache_resource
def _connection():
    return psycopg2.connect(_sync_dsn())


def _clean(html: str) -> str:
    """Collapse a multi-line HTML fragment to one line.

    st.markdown(..., unsafe_allow_html=True) still runs the string through
    a CommonMark parser first. A blank line or 4+ space indent — both of
    which triple-quoted f-strings produce naturally — makes CommonMark drop
    out of "raw HTML block" mode and render the next fragment as an
    indented code block (escaped literal text) instead of HTML. Joining
    everything onto one line with no leading whitespace sidesteps that
    entirely.
    """
    return " ".join(textwrap.dedent(html).split())


def _fetch_daily_briefs():
    conn = _connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select m.name, m.symbol, ds.score, ds.summary, ds.snapshot_date
            from materials m
            join daily_snapshots ds on ds.material_id = m.id
            where ds.snapshot_date = (
                select max(snapshot_date) from daily_snapshots where material_id = m.id
            )
            order by m.name
            """
        )
        latest = cur.fetchall()

        cur.execute(
            "select material_id, snapshot_date, score from daily_snapshots order by material_id, snapshot_date"
        )
        history_rows = cur.fetchall()

        cur.execute("select id, name from materials")
        id_to_name = {row["id"]: row["name"] for row in cur.fetchall()}

    history_by_material: dict[str, list[int]] = {}
    for row in history_rows:
        name = id_to_name.get(row["material_id"])
        history_by_material.setdefault(name, []).append(row["score"])

    return latest, history_by_material


def _fetch_guest_briefs():
    conn = _connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select material_name, score, trend, summary, snapshot_date
            from guest_demo_snapshots
            where snapshot_date = (
                select max(snapshot_date) from guest_demo_snapshots g2
                where g2.material_name = guest_demo_snapshots.material_name
            )
            order by material_name
            """
        )
        latest = cur.fetchall()

        cur.execute(
            "select material_name, snapshot_date, score from guest_demo_snapshots order by material_name, snapshot_date"
        )
        history_rows = cur.fetchall()

    history_by_material: dict[str, list[int]] = {}
    for row in history_rows:
        history_by_material.setdefault(row["material_name"], []).append(row["score"])

    return latest, history_by_material


@st.cache_data(ttl=60)
def _fetch_portfolio_history() -> pd.DataFrame:
    """Full daily_snapshots history for every material, as a long dataframe.

    Backs Portfolio View only — Daily Brief / Guest Mode keep their own
    narrower queries above unchanged.
    """
    conn = _connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select m.name as material, ds.snapshot_date as date, ds.score as score
            from daily_snapshots ds
            join materials m on m.id = ds.material_id
            order by ds.snapshot_date, m.name
            """
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["material", "date", "score"])


def _sparkline_svg(scores: list[int], color: str, width: int = 236, height: int = 56) -> str:
    if len(scores) < 2:
        return ""
    lo, hi = min(scores), max(scores)
    span = max(hi - lo, 1)
    pad = 6
    step = (width - 2 * pad) / (len(scores) - 1)

    def y_of(v: int) -> float:
        return height - pad - ((v - lo) / span) * (height - 2 * pad)

    points = [(pad + i * step, y_of(v)) for i, v in enumerate(scores)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = f"{pad:.1f},{height - pad:.1f} " + line + f" {points[-1][0]:.1f},{height - pad:.1f}"
    gid = f"grad{abs(hash((tuple(scores), color))) % 100000}"

    return _clean(f"""
    <svg width="100%" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <polygon points="{area}" fill="url(#{gid})" />
      <polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.2"
                stroke-linejoin="round" stroke-linecap="round"/>
    </svg>
    """)


def _render_card(name: str, symbol: str | None, score: int, summary: str, history: list[int]) -> str:
    band = _risk_band(score)
    trend = compute_trend(history) if history else "unchanged"
    tmeta = TREND_META[trend]
    symbol_chip = f'<span class="sw-symbol">{symbol}</span>' if symbol else ""
    spark = _sparkline_svg(history, band["color"]) if len(history) >= 2 else (
        '<div class="sw-nohistory">Not enough history yet</div>'
    )
    return _clean(f"""
    <div class="sw-card" style="--band: {band['color']}">
      <div class="sw-card-head">
        <div class="sw-card-title">{name} {symbol_chip}</div>
        <div class="sw-risk-pill" style="color:{band['color']}; border-color:{band['color']}55; background:{band['color']}1a;">
          {band['label']}
        </div>
      </div>
      <div class="sw-score-row">
        <span class="sw-score" style="color:{band['color']}">{score}</span>
        <span class="sw-score-max">/100</span>
        <span class="sw-trend" style="color:{tmeta['color']}">{tmeta['arrow']} {trend}</span>
      </div>
      <div class="sw-summary">{summary}</div>
      <div class="sw-sparkline">{spark}</div>
    </div>
    """)


def _render_grid(cards_html: list[str]) -> None:
    st.markdown(f'<div class="sw-grid">{"".join(cards_html)}</div>', unsafe_allow_html=True)


def _render_stats(scores: list[int], label: str) -> None:
    if not scores:
        return
    avg = round(sum(scores) / len(scores))
    elevated = sum(1 for s in scores if s >= 70)
    moderate = sum(1 for s in scores if 40 <= s < 70)
    low = len(scores) - elevated - moderate
    tiles = [
        (str(len(scores)), f"{label} tracked"),
        (str(avg), "Avg. risk score"),
        (str(elevated), "Elevated"),
        (str(moderate), "Moderate"),
        (str(low), "Low"),
    ]
    cols = st.columns(len(tiles))
    for col, (value, caption) in zip(cols, tiles):
        col.markdown(
            f'<div class="sw-stat"><div class="sw-stat-value">{value}</div>'
            f'<div class="sw-stat-label">{caption}</div></div>',
            unsafe_allow_html=True,
        )


def _build_portfolio_chart(filtered: pd.DataFrame) -> alt.LayerChart:
    band_domain = ["low", "moderate", "elevated"]
    band_range = [RISK_BANDS[b]["color"] for b in band_domain]
    latest_band = (
        filtered.sort_values("date").groupby("material").tail(1).set_index("material")["score"].apply(
            lambda s: "elevated" if s >= 70 else ("moderate" if s >= 40 else "low")
        )
    )
    plot_df = filtered.copy()
    plot_df["band"] = plot_df["material"].map(latest_band)

    material_lines = (
        alt.Chart(plot_df)
        .mark_line(point=True, strokeWidth=2.2)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("score:Q", title="Risk score", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("band:N", scale=alt.Scale(domain=band_domain, range=band_range), title="Latest band"),
            detail="material:N",
            tooltip=["material:N", "date:T", "score:Q"],
        )
    )

    daily_avg = filtered.groupby("date", as_index=False)["score"].mean()
    avg_line = (
        alt.Chart(daily_avg)
        .mark_line(strokeDash=[5, 4], color="#8b96a5", strokeWidth=1.6)
        .encode(x="date:T", y="score:Q", tooltip=[alt.Tooltip("score:Q", title="Avg", format=".1f")])
    )

    chart = (material_lines + avg_line).properties(height=380).interactive()
    return (
        chart.configure(background="#12161f")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor="#8b96a5", titleColor="#9aa5b3", gridColor="#1f2733",
            domainColor="#1f2733", tickColor="#1f2733", labelFont="Inter", titleFont="Space Grotesk",
        )
        .configure_legend(labelColor="#9aa5b3", titleColor="#dfe4eb", labelFont="Inter", titleFont="Space Grotesk")
    )


def _build_export_xlsx(filtered: pd.DataFrame) -> bytes:
    daily = filtered.sort_values(["date", "material"])[["date", "material", "score"]]
    summary = (
        filtered.groupby("material")["score"]
        .agg(min="min", max="max", avg="mean", latest="last")
        .reset_index()
        .round(1)
        .sort_values("material")
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        daily.to_excel(writer, sheet_name="Daily Scores", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
    return buf.getvalue()


st.set_page_config(page_title="SupplyWatch Daily Brief", page_icon="\U0001F4CA", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: radial-gradient(circle at 20% 0%, #131a26 0%, #0b0e14 45%); }
    .block-container { padding-top: 2.2rem; max-width: 1180px; }
    section[data-testid="stSidebar"] { background: #0e1219; border-right: 1px solid #1f2733; }
    section[data-testid="stSidebar"] .stButton button {
        width: 100%; text-align: left; font-family: 'Space Grotesk', sans-serif; font-weight: 600;
        background: transparent; border: 1px solid transparent; color: #9aa5b3;
    }
    section[data-testid="stSidebar"] .stButton button:hover { border-color: #2a3543; color: #eef1f6; }

    .sw-hero-title {
        font-family: 'Space Grotesk', sans-serif; font-weight: 700;
        font-size: 2.1rem; color: #eef1f6; letter-spacing: -0.02em; margin-bottom: 0.1rem;
    }
    .sw-hero-sub {
        font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
        color: #6f7c8e; letter-spacing: 0.02em;
    }

    .sw-stat {
        background: #12161f; border: 1px solid #1f2733; border-radius: 10px;
        padding: 14px 6px; text-align: center; margin-bottom: 6px;
    }
    .sw-stat-value {
        font-family: 'Space Grotesk', sans-serif; font-size: 1.6rem; font-weight: 700; color: #eef1f6;
    }
    .sw-stat-label {
        font-family: 'Inter', sans-serif; font-size: 0.72rem; color: #8b96a5;
        text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px;
    }

    .sw-section-label {
        font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 1.05rem;
        color: #dfe4eb; margin: 1.6rem 0 0.2rem 0;
    }
    .sw-section-caption { font-family: 'Inter'; font-size: 0.85rem; color: #6f7c8e; margin-bottom: 1rem; }

    .sw-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 18px; margin-top: 0.6rem;
    }
    .sw-card {
        background: #12161f; border: 1px solid #1f2733; border-left: 4px solid var(--band);
        border-radius: 14px; padding: 18px 20px 14px 20px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.25);
    }
    .sw-card-head { display: flex; justify-content: space-between; align-items: center; }
    .sw-card-title {
        font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 1rem; color: #eef1f6;
    }
    .sw-symbol {
        font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #8b96a5;
        background: rgba(255,255,255,0.06); padding: 1px 6px; border-radius: 5px; margin-left: 4px;
    }
    .sw-risk-pill {
        font-family: 'Inter'; font-size: 0.68rem; font-weight: 600; padding: 3px 9px;
        border-radius: 999px; border: 1px solid; text-transform: uppercase; letter-spacing: 0.03em;
    }
    .sw-score-row { display: flex; align-items: baseline; gap: 6px; margin-top: 10px; }
    .sw-score { font-family: 'JetBrains Mono', monospace; font-size: 2.4rem; font-weight: 700; line-height: 1; }
    .sw-score-max { font-family: 'JetBrains Mono', monospace; font-size: 0.95rem; color: #6f7c8e; }
    .sw-trend {
        font-family: 'Inter'; font-size: 0.75rem; font-weight: 600; margin-left: auto;
        text-transform: capitalize;
    }
    .sw-summary { font-family: 'Inter'; font-size: 0.8rem; color: #9aa5b3; line-height: 1.5; margin-top: 10px; min-height: 2.6em; }
    .sw-sparkline { margin-top: 12px; line-height: 0; }
    .sw-nohistory { font-family: 'Inter'; font-size: 0.72rem; color: #4d5866; padding: 14px 0; }

    [data-baseweb="tag"] { background-color: #1e2a3a !important; border: 1px solid #2f4258 !important; }
    [data-baseweb="tag"] span, [data-baseweb="tag"] * { color: #cfe0f0 !important; fill: #cfe0f0 !important; font-family: 'Inter'; }
    div[data-testid="stDateInput"] input, div[data-baseweb="select"] { font-family: 'Inter'; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "page" not in st.session_state:
    st.session_state.page = "Daily Brief"

with st.sidebar:
    st.markdown('<div class="sw-hero-sub" style="margin-bottom:1rem;">SUPPLYWATCH</div>', unsafe_allow_html=True)
    for page_name in PAGES:
        is_active = st.session_state.page == page_name
        if st.button(("● " if is_active else "  ") + page_name, key=f"nav_{page_name}", use_container_width=True):
            st.session_state.page = page_name

st.markdown('<div class="sw-hero-title">SupplyWatch — Daily Signal Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sw-hero-sub">INGESTION → SCORING → DAILY SNAPSHOT → DELTA/HISTORY → DELIVERY</div>',
    unsafe_allow_html=True,
)
st.write("")

page = st.session_state.page

if page == "Daily Brief":
    try:
        latest, history = _fetch_daily_briefs()
    except Exception as exc:  # pragma: no cover - dashboard display path only
        st.error(f"Could not load daily snapshots: {exc}")
        latest, history = [], {}

    if not latest:
        st.info("No daily snapshots yet. Run the daily snapshot job (or scripts/backfill_snapshots.py) first.")
    else:
        _render_stats([row["score"] for row in latest], "materials")
        st.markdown('<div class="sw-section-label">Tracked materials</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sw-section-caption">Authenticated view — one card per material, 7-day trend from the delta/history module.</div>',
            unsafe_allow_html=True,
        )
        cards = [
            _render_card(row["name"], row["symbol"], row["score"], row["summary"], history.get(row["name"], []))
            for row in latest
        ]
        _render_grid(cards)

elif page == "Guest Mode":
    try:
        g_latest, g_history = _fetch_guest_briefs()
    except Exception as exc:  # pragma: no cover
        st.error(f"Could not load guest snapshots: {exc}")
        g_latest, g_history = [], {}

    if not g_latest:
        st.info("No guest snapshots yet. Run scripts/backfill_snapshots.py first.")
    else:
        _render_stats([row["score"] for row in g_latest], "demo materials")
        st.markdown('<div class="sw-section-label">Free, no signup</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sw-section-caption">Served entirely from guest_demo_snapshots — isolated from the authenticated pipeline above.</div>',
            unsafe_allow_html=True,
        )
        cards = [
            _render_card(row["material_name"], None, row["score"], row["summary"], g_history.get(row["material_name"], []))
            for row in g_latest
        ]
        _render_grid(cards)

else:  # Portfolio View
    st.markdown('<div class="sw-section-label">Portfolio view</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sw-section-caption">Per-material risk over time (colored by each material\'s latest risk band), '
        'with the cross-material average shown only as a thin reference line — a blended average across unrelated '
        'materials is not a number worth leading with.</div>',
        unsafe_allow_html=True,
    )

    try:
        full_history = _fetch_portfolio_history()
    except Exception as exc:  # pragma: no cover
        st.error(f"Could not load portfolio history: {exc}")
        full_history = pd.DataFrame(columns=["material", "date", "score"])

    if full_history.empty:
        st.info("No snapshot history yet. Run scripts/backfill_snapshots.py first.")
    else:
        full_history["date"] = pd.to_datetime(full_history["date"]).dt.date
        min_date, max_date = full_history["date"].min(), full_history["date"].max()
        all_materials = sorted(full_history["material"].unique())

        col_range, col_materials = st.columns([1, 2])
        with col_range:
            date_range = st.date_input(
                "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
            )
        with col_materials:
            selected_materials = st.multiselect("Materials", options=all_materials, default=all_materials)

        if not isinstance(date_range, tuple) or len(date_range) != 2:
            st.warning("Pick a start and end date to see the graph.")
        elif not selected_materials:
            st.warning("Select at least one material to see the graph.")
        else:
            start_date, end_date = date_range
            filtered = full_history[
                (full_history["date"] >= start_date)
                & (full_history["date"] <= end_date)
                & (full_history["material"].isin(selected_materials))
            ]
            if filtered.empty:
                st.warning("No snapshot data in that date range for the selected materials.")
            else:
                st.altair_chart(_build_portfolio_chart(filtered), use_container_width=True)

                xlsx_bytes = _build_export_xlsx(filtered)
                st.download_button(
                    "Export .xlsx (daily scores + summary)",
                    data=xlsx_bytes,
                    file_name=f"supplywatch_portfolio_{start_date}_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
