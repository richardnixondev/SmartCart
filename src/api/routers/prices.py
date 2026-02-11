"""Price history and statistics endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    AvgPriceByStore,
    PriceHistoryOut,
    PriceRecordOut,
    StatsOut,
    StoreOut,
)
from src.core.database import get_session
from src.core.models import PriceRecord, Product, ScrapeRun, Store, StoreProduct

router = APIRouter(prefix="/api", tags=["prices"])


@router.get("/products/{product_id}/prices", response_model=list[PriceHistoryOut])
async def price_history(
    product_id: int,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    session: AsyncSession = Depends(get_session),
):
    """Get price history for a product across all stores."""
    # Verify product exists
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    since = datetime.utcnow() - timedelta(days=days)

    # Fetch store products with their stores
    sp_stmt = (
        select(StoreProduct)
        .where(StoreProduct.product_id == product_id)
        .options(selectinload(StoreProduct.store))
    )
    sp_result = await session.execute(sp_stmt)
    store_products: list[StoreProduct] = list(sp_result.scalars().all())

    histories: list[PriceHistoryOut] = []

    for sp in store_products:
        pr_stmt = (
            select(PriceRecord)
            .where(
                PriceRecord.store_product_id == sp.id,
                PriceRecord.scraped_at >= since,
            )
            .order_by(PriceRecord.scraped_at.asc())
        )
        pr_result = await session.execute(pr_stmt)
        records = list(pr_result.scalars().all())

        histories.append(
            PriceHistoryOut(
                store=StoreOut.model_validate(sp.store),
                prices=[PriceRecordOut.model_validate(r) for r in records],
            )
        )

    return histories


@router.get("/search-prices")
async def search_prices(
    q: str = Query(..., min_length=2, description="Search term"),
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Search products by name and return their latest prices grouped by store.

    This is useful for cross-store comparison: search 'milk' to see milk prices
    across Tesco, Aldi, Dunnes, etc.
    """
    # Latest price per store_product (window function)
    latest_price_subq = (
        select(
            PriceRecord.store_product_id,
            PriceRecord.price,
            PriceRecord.promo_price,
            PriceRecord.promo_label,
            PriceRecord.unit_price,
            func.row_number()
            .over(
                partition_by=PriceRecord.store_product_id,
                order_by=PriceRecord.scraped_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    latest = (
        select(
            latest_price_subq.c.store_product_id,
            latest_price_subq.c.price,
            latest_price_subq.c.promo_price,
            latest_price_subq.c.promo_label,
            latest_price_subq.c.unit_price,
        )
        .where(latest_price_subq.c.rn == 1)
        .subquery()
    )

    # Join store_products -> stores -> latest prices, filter by name
    stmt = (
        select(
            StoreProduct.store_name,
            Store.name.label("store"),
            Store.slug.label("store_slug"),
            latest.c.price,
            latest.c.promo_price,
            latest.c.promo_label,
            latest.c.unit_price,
            Product.image_url,
            StoreProduct.store_url,
        )
        .join(Store, Store.id == StoreProduct.store_id)
        .join(Product, Product.id == StoreProduct.product_id)
        .join(latest, latest.c.store_product_id == StoreProduct.id)
        .where(StoreProduct.store_name.ilike(f"%{q}%"))
        .order_by(StoreProduct.store_name, Store.name)
        .limit(limit)
    )

    rows = (await session.execute(stmt)).all()

    results = []
    for row in rows:
        effective = float(row.promo_price) if row.promo_price else float(row.price)
        results.append({
            "product_name": row.store_name,
            "store": row.store,
            "store_slug": row.store_slug,
            "price": float(row.price),
            "promo_price": float(row.promo_price) if row.promo_price else None,
            "promo_label": row.promo_label,
            "effective_price": effective,
            "unit_price": float(row.unit_price) if row.unit_price else None,
            "image_url": row.image_url,
            "product_url": row.store_url,
        })

    return results


@router.get("/stats", response_model=StatsOut)
async def stats(
    session: AsyncSession = Depends(get_session),
):
    """General KPIs: total products, stores, price records, last scrape, average prices."""
    total_products = (await session.execute(select(func.count(Product.id)))).scalar_one()
    total_stores = (await session.execute(select(func.count(Store.id)))).scalar_one()
    total_price_records = (
        await session.execute(select(func.count(PriceRecord.id)))
    ).scalar_one()

    # Last scrape time
    last_scrape_row = await session.execute(
        select(ScrapeRun.finished_at)
        .where(ScrapeRun.status.in_(["success", "partial"]))
        .order_by(ScrapeRun.finished_at.desc())
        .limit(1)
    )
    last_scrape = last_scrape_row.scalar_one_or_none()

    # Average latest price per store
    # Use a lateral / window approach: for each store product pick the most
    # recent price record, then average per store.
    latest_price_subq = (
        select(
            PriceRecord.store_product_id,
            PriceRecord.price,
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
        select(latest_price_subq.c.store_product_id, latest_price_subq.c.price)
        .where(latest_price_subq.c.rn == 1)
        .subquery()
    )

    avg_stmt = (
        select(
            Store,
            func.round(func.avg(latest_prices.c.price), 2).label("avg_price"),
        )
        .join(StoreProduct, StoreProduct.store_id == Store.id)
        .join(latest_prices, latest_prices.c.store_product_id == StoreProduct.id)
        .group_by(Store.id)
        .order_by(Store.name)
    )
    avg_result = await session.execute(avg_stmt)
    avg_rows = avg_result.all()

    avg_prices_by_store = [
        AvgPriceByStore(
            store=StoreOut.model_validate(row[0]),
            avg_price=Decimal(str(row[1])) if row[1] is not None else Decimal("0"),
        )
        for row in avg_rows
    ]

    return StatsOut(
        total_products=total_products,
        total_stores=total_stores,
        total_price_records=total_price_records,
        last_scrape=last_scrape,
        avg_prices_by_store=avg_prices_by_store,
    )
