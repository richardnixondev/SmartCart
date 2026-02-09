"""SmartCart Dashboard -- Overview / KPI page."""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from src.core.config import settings
from src.dashboard.components.charts import battle_pie_chart

API = settings.api_base_url


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120, show_spinner=False)
def _fetch_stats() -> dict[str, Any]:
    try:
        resp = httpx.get(f"{API}/api/stats", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return {}


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_battle(category_id: int | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if category_id is not None:
        params["category_id"] = category_id
    try:
        resp = httpx.get(f"{API}/api/battle", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return {}


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.title("\U0001f4ca Overview")
st.caption("Key performance indicators and today's highlights.")

stats = _fetch_stats()
battle = _fetch_battle()

if not stats:
    st.error(
        "Unable to reach the SmartCart API. Please ensure the backend is running "
        f"at **{API}**."
    )
    st.stop()

# ---- KPI cards -----------------------------------------------------------
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

kpi1.metric(
    label="Products Tracked",
    value=f"{stats.get('total_products', 0):,}",
)
kpi2.metric(
    label="Stores",
    value=f"{stats.get('total_stores', 0):,}",
)
kpi3.metric(
    label="Price Records",
    value=f"{stats.get('total_price_records', 0):,}",
)
kpi4.metric(
    label="Last Scrape",
    value=stats.get("last_scrape_time", "N/A"),
)

st.divider()

# ---- Cheapest store of the day -------------------------------------------
cheapest_store = stats.get("cheapest_store")
if cheapest_store:
    st.subheader("Cheapest Store Today")
    cs_col1, cs_col2 = st.columns([1, 3])
    with cs_col1:
        st.markdown(
            f"<div style='text-align:center;padding:1rem;background:#f0f2f6;"
            f"border-radius:0.5rem;'>"
            f"<h2 style='margin:0;'>{cheapest_store.get('name', 'N/A')}</h2>"
            f"<p style='margin:0;color:grey;'>avg. \u20ac{cheapest_store.get('avg_price', 0):.2f}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with cs_col2:
        st.markdown(
            f"Based on the average price across all tracked products today, "
            f"**{cheapest_store.get('name', 'N/A')}** offers the best overall value."
        )
    st.divider()

# ---- Price battle pie chart + Top 5 biggest differences ------------------
left_col, right_col = st.columns(2)

with left_col:
    st.subheader("Cheapest Store Breakdown")
    if battle:
        wins: dict[str, int] = battle.get("wins", {})
        if wins:
            fig = battle_pie_chart(wins)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No battle data available yet.")
    else:
        st.info("No battle data available yet.")

with right_col:
    st.subheader("Top 5 Biggest Price Differences")
    top_diffs: list[dict[str, Any]] = stats.get("top_price_differences", [])
    if top_diffs:
        for i, item in enumerate(top_diffs[:5], start=1):
            product_name = item.get("product_name", "Unknown")
            cheapest = item.get("cheapest_price", 0)
            most_expensive = item.get("most_expensive_price", 0)
            diff = most_expensive - cheapest
            st.markdown(
                f"**{i}. {product_name}**  \n"
                f"\u20ac{cheapest:.2f} \u2013 \u20ac{most_expensive:.2f} "
                f"(diff: **\u20ac{diff:.2f}**)"
            )
    else:
        st.info("No price difference data available yet.")

st.divider()

# ---- Recent price changes ------------------------------------------------
st.subheader("Recent Price Changes")
recent_changes: list[dict[str, Any]] = stats.get("recent_price_changes", [])
if recent_changes:
    import pandas as pd

    df = pd.DataFrame(recent_changes)
    display_cols = [
        c
        for c in ["product_name", "store_name", "old_price", "new_price", "change", "date"]
        if c in df.columns
    ]
    if display_cols:
        df = df[display_cols]

    # Format currency columns
    for col in ("old_price", "new_price", "change"):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: f"\u20ac{v:.2f}" if v is not None else "")

    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No recent price changes recorded yet.")
