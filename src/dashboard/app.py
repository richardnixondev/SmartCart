"""SmartCart Streamlit Dashboard - Main Application Entry Point."""

import streamlit as st

st.set_page_config(
    page_title="SmartCart",
    page_icon="\U0001f6d2",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar branding
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="text-align:center;padding:1rem 0 0.5rem 0;">
            <span style="font-size:2.4rem;">\U0001f6d2</span>
            <h2 style="margin:0;padding:0;">SmartCart</h2>
            <p style="color:grey;margin:0;font-size:0.85rem;">
                Irish Grocery Price Tracker
            </p>
        </div>
        <hr style="margin:0.5rem 0 1rem 0;">
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Multi-page navigation (Streamlit >= 1.36 st.navigation API)
# ---------------------------------------------------------------------------
overview_page = st.Page(
    "pages/overview.py",
    title="Overview",
    icon="\U0001f4ca",
    default=True,
)
battle_page = st.Page(
    "pages/price_battle.py",
    title="Price Battle",
    icon="\u2694\ufe0f",
)
history_page = st.Page(
    "pages/product_history.py",
    title="Product History",
    icon="\U0001f4c8",
)
basket_page = st.Page(
    "pages/basket_compare.py",
    title="Basket Compare",
    icon="\U0001f6d2",
)

pg = st.navigation(
    [overview_page, battle_page, history_page, basket_page],
)

pg.run()
