"""Basket comparison endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BasketCompareOut,
    BasketIn,
    BasketItemIn,
    BasketStoreTotal,
    StoreOut,
)
from src.core.database import get_session
from src.core.models import PriceRecord, Store, StoreProduct

router = APIRouter(prefix="/api/baskets", tags=["baskets"])


async def _compare_basket(
    items: list[BasketItemIn],
    session: AsyncSession,
) -> list[BasketStoreTotal]:
    """Core comparison logic shared by both endpoints.

    For every store, calculate the total cost of the basket.  If a product is
    missing in a given store, it counts towards ``items_missing``.
    """
    # Build a subquery for the latest price per store product
    latest_price_subq = (
        select(
            PriceRecord.store_product_id,
            PriceRecord.price,
            PriceRecord.promo_price,
            func.row_number()
            .over(
                partition_by=PriceRecord.store_product_id,
                order_by=PriceRecord.scraped_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    latest_prices = (
        select(
            latest_price_subq.c.store_product_id,
            latest_price_subq.c.price,
            latest_price_subq.c.promo_price,
        )
        .where(latest_price_subq.c.rn == 1)
        .subquery()
    )

    # Collect product_ids and their quantities
    product_qty: dict[int, int] = {item.product_id: item.quantity for item in items}
    product_ids = list(product_qty.keys())

    # Get store products with their latest prices for the requested product IDs
    sp_stmt = (
        select(
            StoreProduct.product_id,
            StoreProduct.store_id,
            latest_prices.c.price,
            latest_prices.c.promo_price,
        )
        .join(latest_prices, latest_prices.c.store_product_id == StoreProduct.id)
        .where(StoreProduct.product_id.in_(product_ids))
    )

    rows = (await session.execute(sp_stmt)).all()

    # Group by store_id
    store_data: dict[int, dict[int, Decimal]] = {}  # store_id -> {product_id -> effective_price}
    for product_id, store_id, price, promo_price in rows:
        effective = promo_price if promo_price is not None else price
        if store_id not in store_data:
            store_data[store_id] = {}
        # If a product appears multiple times for one store, keep the cheapest
        if product_id not in store_data[store_id] or effective < store_data[store_id][product_id]:
            store_data[store_id][product_id] = effective

    # Load all stores
    stores_result = await session.execute(select(Store).order_by(Store.name))
    stores: list[Store] = list(stores_result.scalars().all())

    totals: list[BasketStoreTotal] = []
    for store in stores:
        prices_map = store_data.get(store.id, {})
        total = Decimal("0")
        found = 0
        missing = 0
        for pid, qty in product_qty.items():
            if pid in prices_map:
                total += prices_map[pid] * qty
                found += 1
            else:
                missing += 1

        totals.append(
            BasketStoreTotal(
                store=StoreOut.model_validate(store),
                total=total,
                items_found=found,
                items_missing=missing,
            )
        )

    # Sort by total ascending (cheapest first)
    totals.sort(key=lambda t: t.total)
    return totals


@router.post("", response_model=BasketCompareOut)
async def create_basket(
    basket: BasketIn,
    session: AsyncSession = Depends(get_session),
):
    """Create a basket and immediately return the cost comparison across stores.

    The basket is not persisted -- this is an in-memory comparison.
    """
    store_totals = await _compare_basket(basket.items, session)
    return BasketCompareOut(basket_name=basket.name, stores=store_totals)


@router.post("/compare", response_model=BasketCompareOut)
async def compare_basket(
    basket: BasketIn,
    session: AsyncSession = Depends(get_session),
):
    """Receive a list of product IDs with quantities and return cost comparison
    across all stores."""
    store_totals = await _compare_basket(basket.items, session)
    return BasketCompareOut(basket_name=basket.name, stores=store_totals)
