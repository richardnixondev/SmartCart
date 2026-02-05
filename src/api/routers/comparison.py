"""Comparison and store-battle endpoints."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    BattleOut,
    BattleResult,
    ComparisonOut,
    ProductOut,
    StoreOut,
    StoreProductOut,
)
from src.core.database import get_session
from src.core.models import Category, PriceRecord, Product, Store, StoreProduct

router = APIRouter(prefix="/api", tags=["comparison"])


# ──────────────────────── helpers ────────────────────────────────────────────


async def _latest_price(session: AsyncSession, store_product_id: int) -> PriceRecord | None:
    """Fetch the most recent PriceRecord for a given StoreProduct."""
    stmt = (
        select(PriceRecord)
        .where(PriceRecord.store_product_id == store_product_id)
        .order_by(PriceRecord.scraped_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ──────────────────────── compare ────────────────────────────────────────────


@router.get("/products/{product_id}/compare", response_model=ComparisonOut)
async def compare_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Compare prices across stores for a single product."""
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.store_products).selectinload(StoreProduct.store),
        )
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    store_items: list[StoreProductOut] = []
    for sp in product.store_products:
        latest = await _latest_price(session, sp.id)
        store_items.append(
            StoreProductOut(
                store=StoreOut.model_validate(sp.store),
                store_name=sp.store_name,
                store_url=sp.store_url,
                latest_price=latest.price if latest else None,
                promo_price=latest.promo_price if latest else None,
                promo_label=latest.promo_label if latest else None,
            )
        )

    # Sort cheapest first (use promo price if present, else regular)
    def _effective_price(item: StoreProductOut) -> Decimal:
        if item.promo_price is not None:
            return item.promo_price
        if item.latest_price is not None:
            return item.latest_price
        return Decimal("99999")

    store_items.sort(key=_effective_price)

    return ComparisonOut(
        product=ProductOut.model_validate(product),
        stores=store_items,
    )


# ──────────────────────── battle ─────────────────────────────────────────────


@router.get("/battle", response_model=BattleOut)
async def store_battle(
    category_id: int | None = Query(None, description="Optional category filter"),
    session: AsyncSession = Depends(get_session),
):
    """Store battle: rank stores by how often they are cheapest.

    For each product that appears in multiple stores, we determine which store
    has the lowest effective price (promo or regular).  The store with the most
    "wins" is ranked highest.
    """
    # Resolve category name for response
    category_name: str | None = None
    if category_id is not None:
        cat = await session.get(Category, category_id)
        if cat is None:
            raise HTTPException(status_code=404, detail="Category not found")
        category_name = cat.name

    # ── Build a subquery for the latest price per store product ────────
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

    # ── Join store products with their latest price ───────────────────
    sp_query = (
        select(
            StoreProduct.product_id,
            StoreProduct.store_id,
            latest_prices.c.price,
            latest_prices.c.promo_price,
        )
        .join(latest_prices, latest_prices.c.store_product_id == StoreProduct.id)
    )

    if category_id is not None:
        sp_query = sp_query.join(Product, Product.id == StoreProduct.product_id).where(
            Product.category_id == category_id
        )

    rows = (await session.execute(sp_query)).all()

    # Group by product_id -> list of (store_id, effective_price)
    product_store_prices: dict[int, list[tuple[int, Decimal]]] = defaultdict(list)
    store_prices_all: dict[int, list[Decimal]] = defaultdict(list)

    for product_id, store_id, price, promo_price in rows:
        effective = promo_price if promo_price is not None else price
        product_store_prices[product_id].append((store_id, effective))
        store_prices_all[store_id].append(effective)

    # Count wins per store
    wins: dict[int, int] = defaultdict(int)
    total_compared = 0

    for product_id, entries in product_store_prices.items():
        if len(entries) < 2:
            continue  # Need at least 2 stores to compare
        total_compared += 1
        cheapest_price = min(e[1] for e in entries)
        for store_id, ep in entries:
            if ep == cheapest_price:
                wins[store_id] += 1

    # Load stores
    store_result = await session.execute(select(Store).order_by(Store.name))
    stores: list[Store] = list(store_result.scalars().all())

    results: list[BattleResult] = []
    for store in stores:
        store_win_count = wins.get(store.id, 0)
        prices_list = store_prices_all.get(store.id, [])
        avg = (
            Decimal(str(round(sum(prices_list) / len(prices_list), 2)))
            if prices_list
            else Decimal("0")
        )
        cheapest_pct = (
            round(store_win_count / total_compared * 100, 1) if total_compared else 0.0
        )

        results.append(
            BattleResult(
                store=StoreOut.model_validate(store),
                wins=store_win_count,
                avg_price=avg,
                cheapest_pct=cheapest_pct,
            )
        )

    # Sort by wins descending
    results.sort(key=lambda r: r.wins, reverse=True)

    return BattleOut(category=category_name, results=results)
