"""Pydantic schemas for the SmartCart API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ──────────────────────────── Stores / Categories ────────────────────────────


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    base_url: str
    logo_url: str | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


# ──────────────────────────── Products ───────────────────────────────────────


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None = None
    ean: str | None = None
    category: CategoryOut | None = None
    unit: str | None = None
    unit_size: Decimal | None = None
    image_url: str | None = None


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int


# ──────────────────────────── Store Products & Prices ────────────────────────


class StoreProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store: StoreOut
    store_name: str
    store_url: str | None = None
    latest_price: Decimal | None = None
    promo_price: Decimal | None = None
    promo_label: str | None = None


class PriceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price: Decimal
    promo_price: Decimal | None = None
    promo_label: str | None = None
    unit_price: Decimal | None = None
    in_stock: bool
    scraped_at: datetime


class PriceHistoryOut(BaseModel):
    store: StoreOut
    prices: list[PriceRecordOut]


# ──────────────────────────── Comparison ─────────────────────────────────────


class ComparisonOut(BaseModel):
    product: ProductOut
    stores: list[StoreProductOut]


# ──────────────────────────── Store Battle ───────────────────────────────────


class BattleResult(BaseModel):
    store: StoreOut
    wins: int
    avg_price: Decimal
    cheapest_pct: float


class BattleOut(BaseModel):
    category: str | None = None
    results: list[BattleResult]


# ──────────────────────────── Baskets ────────────────────────────────────────


class BasketItemIn(BaseModel):
    product_id: int
    quantity: int = 1


class BasketIn(BaseModel):
    name: str
    items: list[BasketItemIn]


class BasketStoreTotal(BaseModel):
    store: StoreOut
    total: Decimal
    items_found: int
    items_missing: int


class BasketCompareOut(BaseModel):
    basket_name: str
    stores: list[BasketStoreTotal]


# ──────────────────────────── Stats / KPIs ───────────────────────────────────


class AvgPriceByStore(BaseModel):
    store: StoreOut
    avg_price: Decimal


class StatsOut(BaseModel):
    total_products: int
    total_stores: int
    total_price_records: int
    last_scrape: datetime | None = None
    avg_prices_by_store: list[AvgPriceByStore]
