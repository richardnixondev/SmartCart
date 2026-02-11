"""Shared fixtures for SmartCart tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.core.database import get_session
from src.core.models import Category, PriceRecord, Product, ScrapeRun, Store, StoreProduct


# ---------------------------------------------------------------------------
# Mock async session
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_session():
    """Return an ``AsyncMock`` that behaves like an ``AsyncSession``.

    Individual tests can configure ``session.execute.return_value`` to
    control query results.
    """
    session = AsyncMock()
    # By default .execute() returns a result whose .scalars().all() is empty
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalar_one.return_value = 0
    session.execute.return_value = result_mock
    session.get.return_value = None
    return session


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest.fixture()
async def client(mock_session):
    """Provide an ``httpx.AsyncClient`` wired to the FastAPI app with the
    database session dependency overridden by ``mock_session``."""

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample domain objects
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_store() -> Store:
    store = Store(
        id=1,
        name="Tesco",
        slug="tesco",
        base_url="https://www.tesco.ie",
        logo_url="https://www.tesco.ie/logo.png",
    )
    return store


@pytest.fixture()
def sample_store_2() -> Store:
    store = Store(
        id=2,
        name="SuperValu",
        slug="supervalu",
        base_url="https://www.supervalu.ie",
        logo_url=None,
    )
    return store


@pytest.fixture()
def sample_category() -> Category:
    return Category(
        id=1,
        name="Dairy",
        slug="dairy",
    )


@pytest.fixture()
def sample_product(sample_category) -> Product:
    product = Product(
        id=1,
        name="Avonmore Full Cream Milk 2L",
        brand="Avonmore",
        ean="5391516590123",
        category_id=sample_category.id,
        unit="l",
        unit_size=Decimal("2"),
        image_url="https://example.com/milk.jpg",
        created_at=datetime(2025, 1, 1),
    )
    product.category = sample_category
    return product


@pytest.fixture()
def sample_product_no_ean() -> Product:
    product = Product(
        id=2,
        name="Kerrygold Butter 250g",
        brand="Kerrygold",
        ean=None,
        category_id=None,
        unit="g",
        unit_size=Decimal("250"),
        image_url=None,
        created_at=datetime(2025, 1, 2),
    )
    product.category = None
    return product


@pytest.fixture()
def sample_store_product(sample_product, sample_store) -> StoreProduct:
    sp = StoreProduct(
        id=1,
        product_id=sample_product.id,
        store_id=sample_store.id,
        store_sku="TESCO-12345",
        store_name="Avonmore Fresh Milk 2 Litre",
        store_url="https://www.tesco.ie/product/12345",
        is_active=True,
    )
    sp.product = sample_product
    sp.store = sample_store
    return sp


@pytest.fixture()
def sample_price_record(sample_store_product) -> PriceRecord:
    return PriceRecord(
        id=1,
        store_product_id=sample_store_product.id,
        price=Decimal("2.49"),
        promo_price=Decimal("1.99"),
        promo_label="Save 50c",
        unit_price=Decimal("0.9950"),
        in_stock=True,
        scraped_at=datetime(2025, 6, 1, 10, 0, 0),
    )


@pytest.fixture()
def sample_scrape_run(sample_store) -> ScrapeRun:
    return ScrapeRun(
        id=1,
        store_id=sample_store.id,
        started_at=datetime(2025, 6, 1, 22, 0, 0),
        finished_at=datetime(2025, 6, 1, 22, 15, 0),
        status="done",
        products_scraped=150,
        errors=None,
    )
