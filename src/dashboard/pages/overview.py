"""SmartCart Dashboard -- Overview / KPI page."""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import streamlit as st

from src.core.config import settings

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
def _fetch_products(page: int = 1, limit: int = 50, search: str = "") -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "limit": limit}
    if search:
        params["search"] = search
    try:
        resp = httpx.get(f"{API}/api/products", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return {"items": [], "total": 0}


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_battle() -> dict[str, Any]:
    try:
        resp = httpx.get(f"{API}/api/battle", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return {}


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.title("Overview")
st.caption("Key performance indicators and product catalogue.")

stats = _fetch_stats()

if not stats:
    st.error(
        "Unable to reach the SmartCart API. Please ensure the backend is running "
        f"at **{API}**."
    )
    st.stop()

# ---- KPI cards -----------------------------------------------------------
kpi1, kpi2, kpi3 = st.columns(3)

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

st.divider()

# ---- Average Price by Store ----------------------------------------------
avg_by_store = stats.get("avg_prices_by_store", [])
if avg_by_store:
    st.subheader("Average Price by Store")
    store_cols = st.columns(len(avg_by_store))
    for idx, entry in enumerate(avg_by_store):
        store_info = entry.get("store", {})
        store_name = store_info.get("name", "Unknown")
        avg_price = entry.get("avg_price", "0")
        store_cols[idx].metric(
            label=store_name,
            value=f"\u20ac{float(avg_price):.2f}",
        )
    st.divider()

# ---- Battle summary (if multiple stores) ---------------------------------
battle = _fetch_battle()
battle_results = battle.get("results", [])
stores_with_wins = [r for r in battle_results if r.get("wins", 0) > 0]

if stores_with_wins:
    from src.dashboard.components.charts import battle_pie_chart

    st.subheader("Cheapest Store Breakdown")
    wins_dict = {r["store"]["name"]: r["wins"] for r in stores_with_wins}
    col_chart, col_stats = st.columns(2)
    with col_chart:
        fig = battle_pie_chart(wins_dict)
        st.plotly_chart(fig, use_container_width=True)
    with col_stats:
        for r in battle_results:
            store_name = r["store"]["name"]
            wins = r.get("wins", 0)
            avg = r.get("avg_price", 0)
            pct = r.get("cheapest_pct", 0)
            if wins > 0 or float(avg) > 0:
                st.markdown(
                    f"**{store_name}**: {wins} wins ({pct}%) "
                    f"| avg \u20ac{float(avg):.2f}"
                )
    st.divider()

# ---- Product catalogue table ---------------------------------------------
st.subheader("Product Catalogue")

# Search bar
search_query = st.text_input(
    "Search products",
    placeholder="e.g. milk, bread, chicken ...",
    key="overview_search",
)

# Pagination
if "overview_page" not in st.session_state:
    st.session_state.overview_page = 1

PAGE_SIZE = 25
data = _fetch_products(
    page=st.session_state.overview_page, limit=PAGE_SIZE, search=search_query
)

items = data.get("items", [])
total = data.get("total", 0)
total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

if items:
    rows = []
    for p in items:
        cat = p.get("category")
        rows.append({
            "ID": p.get("id"),
            "Name": p.get("name", ""),
            "Brand": p.get("brand") or "\u2014",
            "Category": cat.get("name", "") if cat else "\u2014",
            "Unit": f"{p['unit_size']} {p['unit']}" if p.get("unit_size") and p.get("unit") else "\u2014",
            "Image": p.get("image_url") or "",
        })

    df = pd.DataFrame(rows)

    # Show image column if available
    has_images = any(r["Image"] for r in rows)
    if has_images:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Image": st.column_config.ImageColumn("Image", width="small"),
                "ID": st.column_config.NumberColumn("ID", width="small"),
            },
            height=min(len(rows) * 40 + 50, 700),
        )
    else:
        display_df = df.drop(columns=["Image"])
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Pagination controls
    st.caption(f"Showing {len(items)} of {total} products (page {st.session_state.overview_page}/{total_pages})")

    nav_cols = st.columns([1, 1, 4])
    with nav_cols[0]:
        if st.button("Previous", disabled=st.session_state.overview_page <= 1):
            st.session_state.overview_page -= 1
            st.rerun()
    with nav_cols[1]:
        if st.button("Next", disabled=st.session_state.overview_page >= total_pages):
            st.session_state.overview_page += 1
            st.rerun()
else:
    if search_query:
        st.warning("No products found for your search.")
    else:
        st.info("No products in the database yet. Run a scraper first!")
