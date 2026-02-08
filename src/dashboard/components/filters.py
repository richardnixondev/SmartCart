"""Reusable Streamlit filter / input components for the SmartCart dashboard."""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import streamlit as st

from src.core.config import settings

API = settings.api_base_url


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def _fetch_stores() -> list[dict[str, Any]]:
    """Fetch the list of stores from the API (cached 5 min)."""
    try:
        resp = httpx.get(f"{API}/api/stores", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_categories() -> list[dict[str, Any]]:
    """Fetch the list of categories from the API (cached 5 min)."""
    try:
        resp = httpx.get(f"{API}/api/categories", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return []


# ---------------------------------------------------------------------------
# Public filter widgets
# ---------------------------------------------------------------------------
def store_filter(stores: list[dict[str, Any]] | None = None, key: str = "store_filter") -> list[int]:
    """Render a multiselect widget for stores.

    Returns a list of selected store IDs.  If *stores* is ``None`` the list is
    fetched from the API automatically.
    """
    if stores is None:
        stores = _fetch_stores()

    if not stores:
        st.warning("Could not load stores from the API.")
        return []

    options = {s["name"]: s["id"] for s in stores}
    selected_names: list[str] = st.multiselect(
        "Stores",
        options=list(options.keys()),
        default=list(options.keys()),
        key=key,
    )
    return [options[n] for n in selected_names]


def category_filter(
    categories: list[dict[str, Any]] | None = None,
    key: str = "category_filter",
    include_all: bool = True,
) -> int | None:
    """Render a selectbox for category.

    Returns the selected category ID, or ``None`` when *All Categories* is
    chosen.
    """
    if categories is None:
        categories = _fetch_categories()

    if not categories:
        st.warning("Could not load categories from the API.")
        return None

    labels: list[str] = []
    id_map: dict[str, int | None] = {}

    if include_all:
        labels.append("All Categories")
        id_map["All Categories"] = None

    for cat in categories:
        labels.append(cat["name"])
        id_map[cat["name"]] = cat["id"]

    selected = st.selectbox("Category", options=labels, key=key)
    return id_map.get(selected)


def date_range_filter(
    key: str = "date_range_filter",
    default_days: int = 30,
) -> tuple[datetime.date, datetime.date]:
    """Render a date-range picker.

    Returns ``(start_date, end_date)``.  Defaults to the last
    *default_days* days.
    """
    today = datetime.date.today()
    start_default = today - datetime.timedelta(days=default_days)

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("From", value=start_default, key=f"{key}_start")
    with col2:
        end = st.date_input("To", value=today, key=f"{key}_end")

    if start > end:
        st.error("Start date must be before end date.")
        start = end

    return start, end


def search_filter(
    label: str = "Search products",
    key: str = "search_filter",
    placeholder: str = "e.g. milk, bread, chicken ...",
) -> str:
    """Render a text input for product search.

    Returns the current search string (may be empty).
    """
    return st.text_input(label, key=key, placeholder=placeholder)
