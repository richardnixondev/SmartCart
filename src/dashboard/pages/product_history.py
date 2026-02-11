"""SmartCart Dashboard -- Product History page."""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.core.config import settings
from src.dashboard.components.charts import STORE_COLOURS, price_history_chart, store_comparison_bar
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
        if isinstance(payload, list):
            return payload
        return payload.get("items", payload.get("results", []))
    except httpx.HTTPError:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_price_history(product_id: int, days: int = 90) -> list[dict[str, Any]]:
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
def _fetch_comparison(product_id: int) -> dict[str, Any]:
    try:
        resp = httpx.get(f"{API}/api/products/{product_id}/compare", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return {}


@st.cache_data(ttl=60, show_spinner=False)
def _search_prices(query: str) -> list[dict[str, Any]]:
    if not query:
        return []
    try:
        resp = httpx.get(
            f"{API}/api/search-prices",
            params={"q": query, "limit": 100},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return []


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.title("Product History")
st.caption("Search for a product and explore its price history across stores.")

# ---- Sidebar filters ------------------------------------------------------
with st.sidebar:
    st.subheader("Filters")
    start_date, end_date = date_range_filter(key="history_date", default_days=90)

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
    days = 90

# ---- Price history time series chart -------------------------------------
st.subheader("Price History")
history = _fetch_price_history(product_id, days=days)

if history:
    # The API returns list of {store: {...}, prices: [{price, promo_price, scraped_at, ...}]}
    chart_data: list[dict[str, Any]] = []
    for entry in history:
        store_info = entry.get("store", {})
        store_name = store_info.get("name", "Unknown")
        prices = entry.get("prices", [])
        for pr in prices:
            scraped_at = pr.get("scraped_at", "")
            price = float(pr.get("price", 0))
            promo = pr.get("promo_price")
            effective = float(promo) if promo else price
            chart_data.append({
                "date": scraped_at,
                "price": effective,
                "store_name": store_name,
                "is_promo": pr.get("promo_label") is not None,
            })

    if chart_data:
        fig = price_history_chart(chart_data)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No price data in the selected date range.")
else:
    st.info("No price history available for this product.")

st.divider()

# ---- Current prices across stores ----------------------------------------
st.subheader("Current Prices Across Stores")
comparison = _fetch_comparison(product_id)

if comparison:
    stores_list = comparison.get("stores", [])
    if stores_list:
        rows = []
        bar_data = []
        for sp in stores_list:
            store_info = sp.get("store", {})
            store_name = store_info.get("name", "Unknown")
            price = sp.get("latest_price")
            promo_price = sp.get("promo_price")
            promo_label = sp.get("promo_label")

            effective_price = promo_price if promo_price is not None else price

            row = {
                "Store": store_name,
                "Price": f"\u20ac{float(price):.2f}" if price is not None else "\u2014",
                "Promo": promo_label or "\u2014",
            }
            if promo_price is not None:
                row["Promo Price"] = f"\u20ac{float(promo_price):.2f}"
            rows.append(row)

            if effective_price is not None:
                bar_data.append({
                    "store_name": store_name,
                    "price": float(effective_price),
                })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        if bar_data:
            fig2 = store_comparison_bar(bar_data)
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("This product is not available in any store currently.")
else:
    st.info("No comparison data available for this product.")

st.divider()

# ---- Similar products across stores (using search) -----------------------
st.subheader("Similar Products Across Stores")
st.caption(f"Other products matching '{query}' across all stores.")

similar = _search_prices(query) if query else []
if similar:
    sim_rows = []
    for item in similar:
        price = item["price"]
        effective = item["effective_price"]
        sim_rows.append({
            "Store": item["store"],
            "Product": item["product_name"],
            "Price": f"\u20ac{price:.2f}",
            "Effective": f"\u20ac{effective:.2f}",
            "Promo": item.get("promo_label") or "",
        })
    sim_df = pd.DataFrame(sim_rows).sort_values("Effective")
    st.dataframe(sim_df, use_container_width=True, hide_index=True, height=min(len(sim_df) * 38 + 50, 400))
else:
    if query:
        st.info("No similar products found across stores.")
