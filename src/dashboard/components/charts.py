"""Reusable Plotly chart helpers for the SmartCart dashboard."""

from __future__ import annotations

from typing import Any

import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Consistent colour palette keyed by store name
# ---------------------------------------------------------------------------
STORE_COLOURS: dict[str, str] = {
    "Tesco": "#00539F",
    "Dunnes": "#6B2D5B",
    "SuperValu": "#E31837",
    "Aldi": "#00205B",
    "Lidl": "#0050AA",
}

_DEFAULT_COLOUR_SEQUENCE = list(STORE_COLOURS.values())


def _colour_map(stores: list[str]) -> dict[str, str]:
    """Return a colour mapping, falling back to the palette for unknown stores."""
    palette_iter = iter(_DEFAULT_COLOUR_SEQUENCE)
    mapping: dict[str, str] = {}
    for s in stores:
        if s in STORE_COLOURS:
            mapping[s] = STORE_COLOURS[s]
        else:
            mapping[s] = next(palette_iter, "#888888")
    return mapping


# ---------------------------------------------------------------------------
# 1. Price history line chart
# ---------------------------------------------------------------------------
def price_history_chart(data: list[dict[str, Any]]) -> go.Figure:
    """Line chart showing price over time, one line per store.

    *data* is expected to be a list of dicts with keys:
        ``date``, ``price``, ``store_name``, and optionally ``is_promo``.
    """
    if not data:
        fig = go.Figure()
        fig.update_layout(title="No price history data available")
        return fig

    import pandas as pd

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    stores = sorted(df["store_name"].unique())
    colour_map = _colour_map(stores)

    fig = go.Figure()
    for store in stores:
        sdf = df[df["store_name"] == store].sort_values("date")
        fig.add_trace(
            go.Scatter(
                x=sdf["date"],
                y=sdf["price"],
                mode="lines+markers",
                name=store,
                line=dict(color=colour_map[store], width=2),
                marker=dict(size=5),
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Date: %{x|%d %b %Y}<br>"
                    "Price: \u20ac%{y:.2f}<extra></extra>"
                ),
            )
        )

        # Overlay promo markers if the field exists
        if "is_promo" in sdf.columns:
            promo = sdf[sdf["is_promo"] == True]  # noqa: E712
            if not promo.empty:
                fig.add_trace(
                    go.Scatter(
                        x=promo["date"],
                        y=promo["price"],
                        mode="markers",
                        name=f"{store} (promo)",
                        marker=dict(
                            symbol="star",
                            size=12,
                            color=colour_map[store],
                            line=dict(width=1, color="gold"),
                        ),
                        hovertemplate=(
                            "<b>%{fullData.name}</b><br>"
                            "Date: %{x|%d %b %Y}<br>"
                            "Promo price: \u20ac%{y:.2f}<extra></extra>"
                        ),
                        showlegend=False,
                    )
                )

    fig.update_layout(
        title="Price History",
        xaxis_title="Date",
        yaxis_title="Price (\u20ac)",
        yaxis_tickprefix="\u20ac",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=60, b=40),
        template="plotly_white",
    )
    return fig


# ---------------------------------------------------------------------------
# 2. Store comparison horizontal bar chart
# ---------------------------------------------------------------------------
def store_comparison_bar(data: list[dict[str, Any]]) -> go.Figure:
    """Horizontal bar chart comparing stores for a single product.

    *data* is expected to be a list of dicts with keys:
        ``store_name`` and ``price``.
    """
    if not data:
        fig = go.Figure()
        fig.update_layout(title="No comparison data available")
        return fig

    import pandas as pd

    df = pd.DataFrame(data).sort_values("price", ascending=True)
    stores = df["store_name"].tolist()
    colour_map = _colour_map(stores)
    colours = [colour_map.get(s, "#888888") for s in stores]

    fig = go.Figure(
        go.Bar(
            y=df["store_name"],
            x=df["price"],
            orientation="h",
            marker_color=colours,
            text=df["price"].apply(lambda p: f"\u20ac{p:.2f}"),
            textposition="outside",
            hovertemplate="<b>%{y}</b>: \u20ac%{x:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Store Price Comparison",
        xaxis_title="Price (\u20ac)",
        xaxis_tickprefix="\u20ac",
        yaxis_title="",
        margin=dict(l=100, r=40, t=60, b=40),
        template="plotly_white",
    )
    return fig


# ---------------------------------------------------------------------------
# 3. Battle pie chart
# ---------------------------------------------------------------------------
def battle_pie_chart(data: dict[str, int]) -> go.Figure:
    """Pie chart showing % of times each store is cheapest.

    *data* is expected to be a dict mapping store name -> win count.
    """
    if not data:
        fig = go.Figure()
        fig.update_layout(title="No battle data available")
        return fig

    stores = list(data.keys())
    counts = list(data.values())
    colour_map = _colour_map(stores)
    colours = [colour_map.get(s, "#888888") for s in stores]

    fig = go.Figure(
        go.Pie(
            labels=stores,
            values=counts,
            marker=dict(colors=colours),
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>Wins: %{value}<br>%{percent}<extra></extra>",
            hole=0.35,
        )
    )
    fig.update_layout(
        title="Cheapest Store Breakdown",
        margin=dict(l=20, r=20, t=60, b=20),
        template="plotly_white",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
    )
    return fig


# ---------------------------------------------------------------------------
# 4. Basket comparison grouped bar chart
# ---------------------------------------------------------------------------
def basket_comparison_bar(data: list[dict[str, Any]]) -> go.Figure:
    """Grouped bar chart comparing basket cost per store.

    *data* is expected to be a list of dicts with keys:
        ``store_name`` and ``total``.
    """
    if not data:
        fig = go.Figure()
        fig.update_layout(title="No basket data available")
        return fig

    import pandas as pd

    df = pd.DataFrame(data).sort_values("total", ascending=True)
    stores = df["store_name"].tolist()
    colour_map = _colour_map(stores)
    colours = [colour_map.get(s, "#888888") for s in stores]

    min_total = df["total"].min()

    fig = go.Figure(
        go.Bar(
            x=df["store_name"],
            y=df["total"],
            marker_color=colours,
            text=df["total"].apply(lambda t: f"\u20ac{t:.2f}"),
            textposition="outside",
            hovertemplate="<b>%{x}</b>: \u20ac%{y:.2f}<extra></extra>",
        )
    )

    # Highlight the cheapest bar with a border
    bar_line_widths = [3 if t == min_total else 0 for t in df["total"]]
    fig.update_traces(
        marker_line_width=bar_line_widths,
        marker_line_color="gold",
    )

    fig.update_layout(
        title="Basket Total by Store",
        yaxis_title="Total Cost (\u20ac)",
        yaxis_tickprefix="\u20ac",
        xaxis_title="",
        margin=dict(l=40, r=20, t=60, b=40),
        template="plotly_white",
    )
    return fig


# ---------------------------------------------------------------------------
# 5. Price trend sparkline
# ---------------------------------------------------------------------------
def price_trend_sparkline(prices: list[float], width: int = 150, height: int = 40) -> go.Figure:
    """Tiny sparkline for inline use.

    *prices* is a simple list of price floats in chronological order.
    """
    if not prices:
        fig = go.Figure()
        fig.update_layout(width=width, height=height, margin=dict(l=0, r=0, t=0, b=0))
        return fig

    colour = "#00539F"
    if len(prices) >= 2:
        colour = "#2ecc71" if prices[-1] <= prices[0] else "#e74c3c"

    fig = go.Figure(
        go.Scatter(
            y=prices,
            mode="lines",
            line=dict(color=colour, width=1.5),
            fill="tozeroy",
            fillcolor=f"rgba({int(colour[1:3],16)},{int(colour[3:5],16)},{int(colour[5:7],16)},0.1)",
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        width=width,
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
