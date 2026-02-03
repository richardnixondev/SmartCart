"""Product, store, and category listing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import CategoryOut, ProductListOut, ProductOut, StoreOut, StoreProductOut
from src.core.database import get_session
from src.core.models import Category, PriceRecord, Product, Store, StoreProduct

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products", response_model=ProductListOut)
async def list_products(
    category_id: int | None = Query(None, description="Filter by category ID"),
    store_id: int | None = Query(None, description="Filter by store ID"),
    search: str | None = Query(None, description="Search query against product name"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_session),
):
    """List products with optional filters and pagination."""
    stmt = select(Product).options(selectinload(Product.category))

    # Apply filters
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)

    if store_id is not None:
        stmt = stmt.join(StoreProduct, StoreProduct.product_id == Product.id).where(
            StoreProduct.store_id == store_id
        )

    if search:
        stmt = stmt.where(Product.name.ilike(f"%{search}%"))

    # Total count (before pagination)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # Pagination
    offset = (page - 1) * limit
    stmt = stmt.order_by(Product.name).offset(offset).limit(limit)

    result = await session.execute(stmt)
    products = list(result.scalars().all())

    return ProductListOut(
        items=[ProductOut.model_validate(p) for p in products],
        total=total,
    )


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single product by ID, including its store products."""
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.store_products).selectinload(StoreProduct.store),
            selectinload(Product.store_products).selectinload(StoreProduct.price_records),
        )
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductOut.model_validate(product)


@router.get("/stores", response_model=list[StoreOut])
async def list_stores(
    session: AsyncSession = Depends(get_session),
):
    """List all stores."""
    result = await session.execute(select(Store).order_by(Store.name))
    stores = list(result.scalars().all())
    return [StoreOut.model_validate(s) for s in stores]


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    session: AsyncSession = Depends(get_session),
):
    """List all categories."""
    result = await session.execute(select(Category).order_by(Category.name))
    categories = list(result.scalars().all())
    return [CategoryOut.model_validate(c) for c in categories]
