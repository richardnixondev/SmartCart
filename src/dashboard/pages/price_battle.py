"""SmartCart Dashboard -- Price Battle page."""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import streamlit as st

from src.core.config import settings
from src.dashboard.components.charts import battle_pie_chart
from src.dashboard.components.filters import category_filter

API = settings.api_base_url


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


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.title("\u2694\ufe0f Price Battle")
st.caption("See which store offers the cheapest price for every product.")

# ---- Filters -------------------------------------------------------------
with st.sidebar:
    st.subheader("Filters")
    selected_category = category_filter(key="battle_category")

# ---- Fetch data ----------------------------------------------------------
battle = _fetch_battle(category_id=selected_category)

if not battle:
    st.error(
        "Unable to load battle data. Please make sure the API is running "
        f"at **{API}**."
    )
    st.stop()

# ---- Summary statistics --------------------------------------------------
products: list[dict[str, Any]] = battle.get("products", [])
wins: dict[str, int] = battle.get("wins", {})
store_names: list[str] = battle.get("stores", [])

if not products:
    st.info("No products found for the selected category.")
    st.stop()

st.subheader("Summary")
summary_cols = st.columns(len(wins) if wins else 1)
for idx, (store, count) in enumerate(sorted(wins.items(), key=lambda x: -x[1])):
    summary_cols[idx % len(summary_cols)].metric(
        label=store,
        value=f"{count} wins",
    )

st.divider()

# ---- Pie chart + table side by side --------------------------------------
chart_col, table_col = st.columns([1, 2])

with chart_col:
    if wins:
        fig = battle_pie_chart(wins)
        st.plotly_chart(fig, use_container_width=True)

with table_col:
    st.subheader("Product Comparison Table")

    # Build a DataFrame: Product | Store1 | Store2 | ... | Cheapest
    rows: list[dict[str, Any]] = []
    for prod in products:
        row: dict[str, Any] = {"Product": prod.get("product_name", "Unknown")}
        prices: dict[str, float | None] = prod.get("prices", {})
        valid_prices: dict[str, float] = {}
        for store in store_names:
            price = prices.get(store)
            row[store] = f"\u20ac{price:.2f}" if price is not None else "\u2014"
            if price is not None:
                valid_prices[store] = price
        if valid_prices:
            cheapest_store = min(valid_prices, key=valid_prices.get)  # type: ignore[arg-type]
            row["Cheapest"] = cheapest_store
        else:
            row["Cheapest"] = "\u2014"
        rows.append(row)

    df = pd.DataFrame(rows)

    # ---------------------------------------------------------------------------
    # Highlight the cheapest price cell per row in green
    # ---------------------------------------------------------------------------
    def _highlight_cheapest(row: pd.Series) -> list[str]:
        """Return a list of CSS styles, highlighting the cheapest store cell."""
        styles = [""] * len(row)
        cheapest = row.get("Cheapest", "\u2014")
        if cheapest == "\u2014":
            return styles
        for i, col in enumerate(row.index):
            if col == cheapest:
                styles[i] = "background-color: #d4edda; font-weight: bold;"
        return styles

    styled = df.style.apply(_highlight_cheapest, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

st.divider()

# ---- Detailed stats -------------------------------------------------------
st.subheader("Detailed Statistics")
if wins:
    total_products = len(products)
    stats_rows = []
    for store, count in sorted(wins.items(), key=lambda x: -x[1]):
        pct = (count / total_products * 100) if total_products else 0
        stats_rows.append(
            {"Store": store, "Wins": count, "Win %": f"{pct:.1f}%"}
        )
    st.dataframe(
        pd.DataFrame(stats_rows),
        use_container_width=True,
        hide_index=True,
    )
