"""SmartCart Dashboard -- Basket Compare page."""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import streamlit as st

from src.core.config import settings
from src.dashboard.components.charts import basket_comparison_bar

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
            params={"search": query, "limit": 30},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list):
            return payload
        return payload.get("items", payload.get("results", []))
    except httpx.HTTPError:
        return []


def _compare_basket(items: list[dict[str, Any]]) -> dict[str, Any]:
    """POST the basket to the API and return comparison results."""
    try:
        resp = httpx.post(
            f"{API}/api/baskets",
            json={"name": "My Basket", "items": items},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"API error: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "basket_items" not in st.session_state:
    st.session_state.basket_items: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.title("Basket Compare")
st.caption(
    "Build a shopping list, then compare the total cost at each store."
)

# ---- Add items section ----------------------------------------------------
st.subheader("Add Items to Basket")

add_col1, add_col2, add_col3 = st.columns([3, 1, 1])

with add_col1:
    search_query = st.text_input(
        "Search for a product",
        key="basket_search",
        placeholder="e.g. milk, bread, chicken ...",
    )

products = _search_products(search_query)

if search_query and not products:
    st.warning("No products found for your search.")

if products:
    product_map = {p.get("name", f"Product {p['id']}"): p for p in products}
    with add_col2:
        selected_product_name = st.selectbox(
            "Product",
            options=list(product_map.keys()),
            key="basket_product_select",
        )
    with add_col3:
        quantity = st.number_input(
            "Qty",
            min_value=1,
            max_value=99,
            value=1,
            key="basket_qty",
        )

    if st.button("Add to basket", type="primary"):
        product = product_map[selected_product_name]
        st.session_state.basket_items.append(
            {
                "product_id": product["id"],
                "product_name": product.get("name", f"Product {product['id']}"),
                "quantity": quantity,
            }
        )
        st.rerun()

st.divider()

# ---- Shopping list display ------------------------------------------------
st.subheader("Your Basket")

if not st.session_state.basket_items:
    st.info("Your basket is empty. Search and add products above.")
else:
    # Show basket as a table
    basket_df = pd.DataFrame(
        [
            {
                "Product": item["product_name"],
                "Quantity": item["quantity"],
            }
            for item in st.session_state.basket_items
        ]
    )

    st.dataframe(basket_df, use_container_width=True, hide_index=True)

    # Remove buttons
    remove_cols = st.columns(min(len(st.session_state.basket_items), 6))
    for idx, item in enumerate(st.session_state.basket_items):
        col = remove_cols[idx % len(remove_cols)]
        if col.button(
            f"Remove {item['product_name'][:20]}",
            key=f"remove_{idx}",
        ):
            st.session_state.basket_items.pop(idx)
            st.rerun()

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        compare_clicked = st.button(
            "Compare Basket",
            type="primary",
            use_container_width=True,
        )
    with action_col2:
        if st.button("Clear Basket", use_container_width=True):
            st.session_state.basket_items = []
            st.rerun()

    # ---- Comparison results -----------------------------------------------
    if compare_clicked:
        payload_items = [
            {"product_id": item["product_id"], "quantity": item["quantity"]}
            for item in st.session_state.basket_items
        ]

        with st.spinner("Comparing prices across stores..."):
            result = _compare_basket(payload_items)

        if not result:
            st.error(
                "Could not compare your basket. Make sure the API is running "
                f"at **{API}**."
            )
            st.stop()

        st.divider()
        st.subheader("Comparison Results")

        # ---- Totals per store (from BasketCompareOut.stores) ------
        store_totals: list[dict[str, Any]] = result.get("stores", [])
        if store_totals:
            # Filter out stores with 0 items found
            active_stores = [s for s in store_totals if s.get("items_found", 0) > 0]
            if not active_stores:
                st.warning("None of the stores carry these products.")
            else:
                # Sort cheapest first
                active_sorted = sorted(active_stores, key=lambda s: float(s.get("total", 99999)))

                # Metrics row
                metric_cols = st.columns(len(active_sorted))
                cheapest_total = float(active_sorted[0]["total"]) if active_sorted else 0
                for idx, st_total in enumerate(active_sorted):
                    store_info = st_total.get("store", {})
                    name = store_info.get("name", "Unknown")
                    total = float(st_total.get("total", 0))
                    found = st_total.get("items_found", 0)
                    missing = st_total.get("items_missing", 0)
                    delta = total - cheapest_total

                    metric_cols[idx].metric(
                        label=name,
                        value=f"\u20ac{total:.2f}",
                        delta=f"+\u20ac{delta:.2f}" if delta > 0 else "Cheapest",
                        delta_color="inverse" if delta > 0 else "off",
                    )
                    metric_cols[idx].caption(f"{found} found, {missing} missing")

                # Bar chart
                chart_data = [
                    {
                        "store_name": s["store"]["name"],
                        "total": float(s["total"]),
                    }
                    for s in active_sorted
                ]
                fig = basket_comparison_bar(chart_data)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No store comparison data available.")
