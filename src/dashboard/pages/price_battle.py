"""SmartCart Dashboard -- Price Battle page."""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.core.config import settings
from src.dashboard.components.charts import STORE_COLOURS, battle_pie_chart
from src.dashboard.components.filters import category_filter

API = settings.api_base_url

POPULAR_SEARCHES = [
    "milk", "bread", "chicken", "rice", "butter", "cheese",
    "eggs", "pasta", "sugar", "tea", "coffee", "water",
    "beef", "salmon", "yoghurt", "cereal", "oil", "flour",
]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------
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


@st.cache_data(ttl=60, show_spinner=False)
def _search_prices(query: str) -> list[dict[str, Any]]:
    if not query:
        return []
    try:
        resp = httpx.get(
            f"{API}/api/search-prices",
            params={"q": query, "limit": 60},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return []


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.title("Price Battle")
st.caption("Compare real product prices across Irish supermarkets.")

# ---- Store Rankings (compact) --------------------------------------------
battle = _fetch_battle()
results = battle.get("results", [])
stores_with_data = [r for r in results if float(r.get("avg_price", 0)) > 0]

if stores_with_data:
    st.subheader("Store Overview")
    metric_cols = st.columns(len(stores_with_data))
    for idx, r in enumerate(stores_with_data):
        store_name = r["store"]["name"]
        avg_price = float(r.get("avg_price", 0))
        product_count = r.get("wins", 0)
        metric_cols[idx].metric(
            label=store_name,
            value=f"\u20ac{avg_price:.2f} avg",
        )
    st.divider()

# ---- Product Price Comparison --------------------------------------------
st.subheader("Compare Products")

# Popular search buttons
st.caption("Popular searches:")
button_cols = st.columns(9)
for idx, term in enumerate(POPULAR_SEARCHES[:9]):
    with button_cols[idx]:
        if st.button(term.capitalize(), key=f"pop_{term}", use_container_width=True):
            st.session_state.battle_search_input = term
            st.rerun()

# Second row of popular searches
button_cols2 = st.columns(9)
for idx, term in enumerate(POPULAR_SEARCHES[9:18]):
    with button_cols2[idx]:
        if st.button(term.capitalize(), key=f"pop_{term}", use_container_width=True):
            st.session_state.battle_search_input = term
            st.rerun()

# Search input
actual_query = st.text_input(
    "Search for a product to compare prices",
    placeholder="e.g. milk, bread, chicken ...",
    key="battle_search_input",
)

if actual_query:
    results_data = _search_prices(actual_query)

    if not results_data:
        st.warning(f"No products found for '{actual_query}'.")
    else:
        # Build comparison table
        rows = []
        for item in results_data:
            price = item["price"]
            promo = item.get("promo_price")
            effective = item["effective_price"]

            row = {
                "Store": item["store"],
                "Product": item["product_name"],
                "Price": price,
                "Effective": effective,
                "Promo": item.get("promo_label") or "",
            }
            rows.append(row)

        df = pd.DataFrame(rows)

        # Sort by effective price
        df = df.sort_values("Effective")

        # Show count per store
        store_counts = df["Store"].value_counts()
        st.caption(
            f"Found {len(df)} products matching '{actual_query}': "
            + ", ".join(f"{store} ({count})" for store, count in store_counts.items())
        )

        # Format for display
        display_df = df.copy()
        display_df["Price"] = display_df["Price"].apply(lambda p: f"\u20ac{p:.2f}")
        display_df["Effective"] = display_df["Effective"].apply(lambda p: f"\u20ac{p:.2f}")

        # Color-code by store
        def _style_store(row: pd.Series) -> list[str]:
            store = row.get("Store", "")
            color = STORE_COLOURS.get(store, "")
            # Match partial store names
            for key, val in STORE_COLOURS.items():
                if key.lower() in store.lower():
                    color = val
                    break
            if color:
                return [f"border-left: 4px solid {color}"] + [""] * (len(row) - 1)
            return [""] * len(row)

        styled = display_df.style.apply(_style_store, axis=1)
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            height=min(len(display_df) * 38 + 50, 600),
        )

        # Average price chart per store for this search
        st.subheader(f"Average price for '{actual_query}' by store")
        avg_by_store = df.groupby("Store")["Effective"].mean().sort_values()

        colors = []
        for store in avg_by_store.index:
            color = "#888888"
            for key, val in STORE_COLOURS.items():
                if key.lower() in store.lower():
                    color = val
                    break
            colors.append(color)

        fig = go.Figure(
            go.Bar(
                x=avg_by_store.index,
                y=avg_by_store.values,
                marker_color=colors,
                text=[f"\u20ac{v:.2f}" for v in avg_by_store.values],
                textposition="outside",
            )
        )
        fig.update_layout(
            yaxis_title="Average Price (\u20ac)",
            yaxis_tickprefix="\u20ac",
            margin=dict(l=40, r=20, t=20, b=40),
            template="plotly_white",
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Cheapest finds
        st.subheader("Best Deals")
        cheapest = df.nsmallest(5, "Effective")
        for _, row in cheapest.iterrows():
            promo_text = f" ({row['Promo']})" if row["Promo"] else ""
            st.markdown(
                f"**\u20ac{row['Effective']:.2f}** - {row['Product']} @ {row['Store']}{promo_text}"
            )
else:
    st.info("Search for a product above or click a popular category to compare prices across stores.")
