"""SmartCart Dashboard -- Product History page."""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import pandas as pd
import streamlit as st

from src.core.config import settings
from src.dashboard.components.charts import price_history_chart, store_comparison_bar
from src.dashboard.components.filters import date_range_filter, search_filter

API = settings.api_base_url


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def _search_products(query: str) -> list[dict[str, Any]]:
    if not query:
        return []
    try:
        resp = httpx.get(
            f"{API}/api/products",
            params={"search": query, "limit": 50},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        # Support both a bare list and a paginated wrapper ({items: [...]})
        if isinstance(payload, list):
            return payload
        return payload.get("items", payload.get("results", []))
    except httpx.HTTPError:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_price_history(product_id: int, days: int = 30) -> list[dict[str, Any]]:
    try:
        resp = httpx.get(
            f"{API}/api/products/{product_id}/prices",
            params={"days": days},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_comparison(product_id: int) -> list[dict[str, Any]]:
    try:
        resp = httpx.get(f"{API}/api/products/{product_id}/compare", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return []


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.title("\U0001f4c8 Product History")
st.caption("Search for a product and explore its price history across stores.")

# ---- Sidebar filters ------------------------------------------------------
with st.sidebar:
    st.subheader("Filters")
    start_date, end_date = date_range_filter(key="history_date")

# ---- Search & select product ---------------------------------------------
query = search_filter(key="product_history_search")

products = _search_products(query)

if query and not products:
    st.warning("No products found. Try a different search term.")
    st.stop()

if not products:
    st.info("Enter a search term above to find products.")
    st.stop()

product_options = {p.get("name", f"Product {p['id']}"): p["id"] for p in products}
selected_name = st.selectbox(
    "Select a product",
    options=list(product_options.keys()),
    key="product_selector",
)

if not selected_name:
    st.stop()

product_id: int = product_options[selected_name]

# ---- Calculate days from date range --------------------------------------
days = (end_date - start_date).days
if days < 1:
    days = 30

# ---- Price history chart --------------------------------------------------
history = _fetch_price_history(product_id, days=days)

if history:
    # Filter data to requested date range
    filtered: list[dict[str, Any]] = []
    for entry in history:
        entry_date = entry.get("date", "")
        try:
            d = datetime.date.fromisoformat(entry_date[:10])
        except (ValueError, TypeError):
            filtered.append(entry)
            continue
        if start_date <= d <= end_date:
            filtered.append(entry)

    if filtered:
        fig = price_history_chart(filtered)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No price data in the selected date range.")
else:
    st.info("No price history available for this product.")

st.divider()

# ---- Current prices table -------------------------------------------------
st.subheader("Current Prices")
comparison = _fetch_comparison(product_id)

if comparison:
    comp_df = pd.DataFrame(comparison)
    display_cols = [
        c
        for c in ["store_name", "price", "is_promo", "last_updated"]
        if c in comp_df.columns
    ]
    if display_cols:
        comp_df = comp_df[display_cols]

    # Format
    if "price" in comp_df.columns:
        comp_df["price"] = comp_df["price"].apply(
            lambda v: f"\u20ac{v:.2f}" if v is not None else "\u2014"
        )
    if "is_promo" in comp_df.columns:
        comp_df["is_promo"] = comp_df["is_promo"].apply(
            lambda v: "Yes" if v else "No"
        )

    comp_df.columns = [c.replace("_", " ").title() for c in comp_df.columns]
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

    # Also show a bar comparison chart
    raw_comparison = _fetch_comparison(product_id)
    bar_data = [
        {"store_name": r["store_name"], "price": r["price"]}
        for r in raw_comparison
        if r.get("price") is not None
    ]
    if bar_data:
        fig2 = store_comparison_bar(bar_data)
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No comparison data available for this product.")
