"""Product matcher across stores.

Finds duplicate products listed under different stores and merges them
into a single canonical Product record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.models import Product, StoreProduct
from src.matcher.normalizer import extract_brand, extract_unit_info, normalize_name

logger = logging.getLogger(__name__)


@dataclass
class RawProduct:
    """Lightweight carrier for an incoming scraped product before it has a
    canonical Product row."""

    name: str
    ean: str | None = None
    brand: str | None = None
    store_product_id: int | None = None


def ean_match(product: Product, candidates: list[Product]) -> Product | None:
    """Return the first candidate with an identical EAN, or None."""
    if not product.ean:
        return None
    for c in candidates:
        if c.ean and c.ean == product.ean and c.id != product.id:
            return c
    return None


def fuzzy_match(
    name: str,
    candidates: list[Product],
    threshold: float = 85.0,
) -> Product | None:
    """Return the best fuzzy match above *threshold* using token-sort ratio.

    Uses ``rapidfuzz.fuzz.token_sort_ratio`` which is robust to word-order
    differences (e.g. "Avonmore Milk 2L" vs "Milk Avonmore 2L").
    """
    normalised = normalize_name(name)
    if not normalised:
        return None

    best_score: float = 0.0
    best_match: Product | None = None

    for candidate in candidates:
        candidate_norm = normalize_name(candidate.name)
        if not candidate_norm:
            continue

        score = fuzz.token_sort_ratio(normalised, candidate_norm)
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= threshold and best_match is not None:
        return best_match
    return None


def find_match(
    raw_product: RawProduct,
    existing_products: list[Product],
) -> Product | None:
    """Try to match a raw scraped product against existing canonical products.

    Strategy:
    1. EAN exact match (fastest, most reliable).
    2. Fuzzy name match with unit-info cross-check.
    """
    # Build a temporary Product-like object for ean_match
    if raw_product.ean:
        for p in existing_products:
            if p.ean and p.ean == raw_product.ean:
                return p

    # Fuzzy name match
    match = fuzzy_match(raw_product.name, existing_products)
    if match is None:
        return None

    # Cross-check unit info when available to reduce false positives
    raw_unit, raw_size = extract_unit_info(raw_product.name)
    match_unit, match_size = extract_unit_info(match.name)

    if raw_unit and match_unit:
        if raw_unit != match_unit or raw_size != match_size:
            # Units differ -- likely a different product size
            return None

    return match


async def run_matching(session: AsyncSession) -> int:
    """Run matching across all unmatched store products.

    An *unmatched* store product is one whose Product row is only linked to
    that single StoreProduct (i.e. a singleton).  We try to merge these
    singletons into an existing canonical Product that is already linked to
    other stores.

    Returns the number of merges performed.
    """
    logger.info("Starting product matching run")

    # ------------------------------------------------------------------
    # Step 1: Find singleton products (only one store product references them)
    # ------------------------------------------------------------------
    singleton_subq = (
        select(Product.id)
        .join(StoreProduct, StoreProduct.product_id == Product.id)
        .group_by(Product.id)
        .having(func.count(StoreProduct.id) == 1)
        .subquery()
    )

    singleton_sps_result = await session.execute(
        select(StoreProduct)
        .where(StoreProduct.product_id.in_(select(singleton_subq.c.id)))
        .options(selectinload(StoreProduct.product))
    )
    singleton_sps: list[StoreProduct] = list(singleton_sps_result.scalars().all())

    if not singleton_sps:
        logger.info("No singleton store products found -- nothing to match")
        return 0

    # ------------------------------------------------------------------
    # Step 2: Load canonical products that already span multiple stores
    # ------------------------------------------------------------------
    multi_subq = (
        select(Product.id)
        .join(StoreProduct, StoreProduct.product_id == Product.id)
        .group_by(Product.id)
        .having(func.count(StoreProduct.id) > 1)
        .subquery()
    )

    canonical_result = await session.execute(
        select(Product).where(Product.id.in_(select(multi_subq.c.id)))
    )
    canonical_products: list[Product] = list(canonical_result.scalars().all())

    # Also include other singletons as potential merge targets (two singletons
    # from different stores can be merged together).
    all_singleton_products = [sp.product for sp in singleton_sps]

    # Build a combined candidate list
    candidates = canonical_products + all_singleton_products

    # Deduplicate by product id
    seen_ids: set[int] = set()
    unique_candidates: list[Product] = []
    for p in candidates:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            unique_candidates.append(p)

    merges = 0

    for sp in singleton_sps:
        product = sp.product
        raw = RawProduct(
            name=product.name,
            ean=product.ean,
            brand=product.brand,
            store_product_id=sp.id,
        )

        # Remove the product itself from candidates to avoid self-match
        filtered = [c for c in unique_candidates if c.id != product.id]
        match = find_match(raw, filtered)

        if match is None:
            continue

        logger.info(
            "Merging product %d (%s) into %d (%s)",
            product.id,
            product.name,
            match.id,
            match.name,
        )

        # Re-point the store product to the canonical match
        sp.product_id = match.id

        # Enrich the canonical product with any missing info
        if not match.ean and product.ean:
            match.ean = product.ean
        if not match.brand and product.brand:
            match.brand = product.brand
        if not match.brand:
            extracted = extract_brand(product.name)
            if extracted:
                match.brand = extracted
        if not match.unit and product.unit:
            match.unit = product.unit
        if not match.unit_size and product.unit_size:
            match.unit_size = product.unit_size
        if not match.image_url and product.image_url:
            match.image_url = product.image_url

        merges += 1

    if merges:
        await session.commit()
        logger.info("Matching complete: %d merges performed", merges)
    else:
        logger.info("Matching complete: no merges found")

    return merges
