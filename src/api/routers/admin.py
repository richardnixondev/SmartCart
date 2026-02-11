"""Admin endpoints for product management: merge, edit, unlink."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    AdminProductListOut,
    AdminProductOut,
    AdminStoreProductOut,
    MergeProductsIn,
    MergeProductsOut,
    ProductUpdateIn,
    UnlinkOut,
)
from src.core.database import get_session
from src.core.models import Category, PriceRecord, Product, StoreProduct

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── helpers ──────────────────────────────────────────────────────────────────


def _build_admin_store_product(sp: StoreProduct) -> AdminStoreProductOut:
    """Convert a StoreProduct ORM object (with eager-loaded relations) to schema."""
    latest = None
    promo = None
    if sp.price_records:
        rec = max(sp.price_records, key=lambda r: r.scraped_at)
        latest = rec.price
        promo = rec.promo_price
    return AdminStoreProductOut(
        id=sp.id,
        store=sp.store,
        store_sku=sp.store_sku,
        store_name=sp.store_name,
        store_url=sp.store_url,
        is_active=sp.is_active,
        latest_price=latest,
        promo_price=promo,
    )


def _build_admin_product(
    product: Product, *, include_store_products: bool = True
) -> AdminProductOut:
    sps = (
        [_build_admin_store_product(sp) for sp in product.store_products]
        if include_store_products
        else []
    )
    return AdminProductOut(
        id=product.id,
        name=product.name,
        brand=product.brand,
        ean=product.ean,
        category=product.category,
        unit=product.unit,
        unit_size=product.unit_size,
        image_url=product.image_url,
        store_product_count=len(product.store_products),
        store_products=sps,
    )


# ── 1. GET /api/admin/unmatched ──────────────────────────────────────────────


@router.get("/unmatched", response_model=AdminProductListOut)
async def list_unmatched(
    search: str | None = Query(None),
    store_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List singleton products (exactly 1 StoreProduct)."""
    # Subquery: product_ids with exactly 1 store_product
    singleton_sq = (
        select(StoreProduct.product_id)
        .group_by(StoreProduct.product_id)
        .having(func.count() == 1)
        .subquery()
    )

    stmt = (
        select(Product)
        .join(singleton_sq, Product.id == singleton_sq.c.product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.store_products).selectinload(StoreProduct.store),
            selectinload(Product.store_products).selectinload(
                StoreProduct.price_records
            ),
        )
    )

    if search:
        stmt = stmt.where(Product.name.ilike(f"%{search}%"))

    if store_id is not None:
        stmt = stmt.join(
            StoreProduct, StoreProduct.product_id == Product.id
        ).where(StoreProduct.store_id == store_id)

    # Total count
    count_stmt = select(func.count()).select_from(
        select(Product.id)
        .join(singleton_sq, Product.id == singleton_sq.c.product_id)
        .where(Product.name.ilike(f"%{search}%") if search else True)
        .subquery()
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Pagination
    offset = (page - 1) * limit
    stmt = stmt.order_by(Product.name).offset(offset).limit(limit)

    result = await session.execute(stmt)
    products = list(result.scalars().unique().all())

    return AdminProductListOut(
        items=[_build_admin_product(p) for p in products],
        total=total,
    )


# ── 2. GET /api/admin/products/{id}/store-products ───────────────────────────


@router.get(
    "/products/{product_id}/store-products",
    response_model=list[AdminStoreProductOut],
)
async def list_store_products(
    product_id: int,
    session: AsyncSession = Depends(get_session),
):
    """List all StoreProducts for a given Product, with latest price."""
    stmt = (
        select(StoreProduct)
        .where(StoreProduct.product_id == product_id)
        .options(
            selectinload(StoreProduct.store),
            selectinload(StoreProduct.price_records),
        )
    )
    result = await session.execute(stmt)
    sps = list(result.scalars().all())
    if not sps:
        raise HTTPException(404, "Product not found or has no store products")
    return [_build_admin_store_product(sp) for sp in sps]


# ── 3. PATCH /api/admin/products/{id} ───────────────────────────────────────


@router.patch("/products/{product_id}", response_model=AdminProductOut)
async def update_product(
    product_id: int,
    body: ProductUpdateIn,
    session: AsyncSession = Depends(get_session),
):
    """Update product metadata (PATCH semantics — only set fields are applied)."""
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.store_products).selectinload(StoreProduct.store),
            selectinload(Product.store_products).selectinload(
                StoreProduct.price_records
            ),
        )
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "Product not found")

    update_data = body.model_dump(exclude_unset=True)

    # If category_id changed, validate it exists
    if "category_id" in update_data and update_data["category_id"] is not None:
        cat = await session.get(Category, update_data["category_id"])
        if cat is None:
            raise HTTPException(400, "Category not found")

    for field, value in update_data.items():
        setattr(product, field, value)

    await session.commit()
    await session.refresh(product)

    # Re-load relations after commit
    stmt2 = (
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.store_products).selectinload(StoreProduct.store),
            selectinload(Product.store_products).selectinload(
                StoreProduct.price_records
            ),
        )
    )
    result2 = await session.execute(stmt2)
    product = result2.scalar_one()

    return _build_admin_product(product)


# ── 4. POST /api/admin/products/merge ────────────────────────────────────────


@router.post("/products/merge", response_model=MergeProductsOut)
async def merge_products(
    body: MergeProductsIn,
    session: AsyncSession = Depends(get_session),
):
    """Merge N products into 1. Re-points StoreProducts, enriches metadata, deletes losers."""
    if len(body.product_ids) < 2:
        raise HTTPException(400, "Need at least 2 product IDs to merge")

    # Load all products
    stmt = (
        select(Product)
        .where(Product.id.in_(body.product_ids))
        .options(selectinload(Product.store_products))
    )
    result = await session.execute(stmt)
    products = list(result.scalars().unique().all())

    found_ids = {p.id for p in products}
    missing = set(body.product_ids) - found_ids
    if missing:
        raise HTTPException(404, f"Products not found: {sorted(missing)}")

    # Determine target
    if body.target_id is not None:
        if body.target_id not in found_ids:
            raise HTTPException(400, "target_id must be one of product_ids")
        target = next(p for p in products if p.id == body.target_id)
    else:
        # Pick the one with most store products
        target = max(products, key=lambda p: len(p.store_products))

    losers = [p for p in products if p.id != target.id]

    # Re-point store products from losers to target
    moved = 0
    for loser in losers:
        for sp in loser.store_products:
            sp.product_id = target.id
            moved += 1

    # Enrich target metadata from losers
    for loser in losers:
        if not target.ean and loser.ean:
            target.ean = loser.ean
        if not target.brand and loser.brand:
            target.brand = loser.brand
        if not target.unit and loser.unit:
            target.unit = loser.unit
        if not target.unit_size and loser.unit_size:
            target.unit_size = loser.unit_size
        if not target.image_url and loser.image_url:
            target.image_url = loser.image_url
        if not target.category_id and loser.category_id:
            target.category_id = loser.category_id

    await session.flush()

    # Delete loser products
    loser_ids = [l.id for l in losers]
    await session.execute(delete(Product).where(Product.id.in_(loser_ids)))
    await session.commit()

    return MergeProductsOut(
        kept_product_id=target.id,
        merged_product_ids=loser_ids,
        store_products_moved=moved,
    )


# ── 5. POST /api/admin/products/{id}/unlink/{store_product_id} ──────────────


@router.post(
    "/products/{product_id}/unlink/{store_product_id}",
    response_model=UnlinkOut,
)
async def unlink_store_product(
    product_id: int,
    store_product_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Unlink a StoreProduct from its Product, creating a new singleton Product."""
    # Load the store product
    sp = await session.get(StoreProduct, store_product_id)
    if sp is None or sp.product_id != product_id:
        raise HTTPException(404, "StoreProduct not found for this product")

    # Count siblings
    count_stmt = select(func.count()).where(
        StoreProduct.product_id == product_id
    )
    sibling_count = (await session.execute(count_stmt)).scalar_one()

    if sibling_count <= 1:
        raise HTTPException(400, "Cannot unlink the last StoreProduct from a product")

    # Create a new singleton Product
    new_product = Product(name=sp.store_name)
    session.add(new_product)
    await session.flush()  # get new_product.id

    # Re-point the store product
    sp.product_id = new_product.id
    await session.commit()

    return UnlinkOut(
        new_product_id=new_product.id,
        store_product_id=sp.id,
    )
