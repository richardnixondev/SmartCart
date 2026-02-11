"""Tests for src.scrapers.base data structures and utilities."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.scrapers.base import (
    DEFAULT_HEADERS,
    USER_AGENTS,
    RawProduct,
    ScrapeResult,
    random_user_agent,
)


# =========================================================================
# RawProduct
# =========================================================================


class TestRawProduct:
    """Tests for the ``RawProduct`` dataclass."""

    def test_raw_product_creation_minimal(self):
        """Create a RawProduct with only the required fields."""
        rp = RawProduct(
            store_sku="SKU-001",
            name="Avonmore Milk 2L",
            price=Decimal("2.49"),
        )
        assert rp.store_sku == "SKU-001"
        assert rp.name == "Avonmore Milk 2L"
        assert rp.price == Decimal("2.49")
        # Defaults
        assert rp.promo_price is None
        assert rp.promo_label is None
        assert rp.unit_price is None
        assert rp.unit is None
        assert rp.unit_size is None
        assert rp.brand is None
        assert rp.ean is None
        assert rp.category is None
        assert rp.image_url is None
        assert rp.product_url is None
        assert rp.in_stock is True

    def test_raw_product_creation_full(self):
        """Create a RawProduct with all fields specified."""
        rp = RawProduct(
            store_sku="SKU-002",
            name="Kerrygold Butter 250g",
            price=Decimal("3.99"),
            promo_price=Decimal("2.99"),
            promo_label="Save 1 Euro",
            unit_price=Decimal("11.96"),
            unit="g",
            unit_size=Decimal("250"),
            brand="Kerrygold",
            ean="5011038123456",
            category="Dairy",
            image_url="https://example.com/butter.jpg",
            product_url="https://store.com/butter",
            in_stock=False,
        )
        assert rp.store_sku == "SKU-002"
        assert rp.name == "Kerrygold Butter 250g"
        assert rp.price == Decimal("3.99")
        assert rp.promo_price == Decimal("2.99")
        assert rp.promo_label == "Save 1 Euro"
        assert rp.unit_price == Decimal("11.96")
        assert rp.unit == "g"
        assert rp.unit_size == Decimal("250")
        assert rp.brand == "Kerrygold"
        assert rp.ean == "5011038123456"
        assert rp.category == "Dairy"
        assert rp.image_url == "https://example.com/butter.jpg"
        assert rp.product_url == "https://store.com/butter"
        assert rp.in_stock is False

    def test_raw_product_default_in_stock_is_true(self):
        rp = RawProduct(store_sku="X", name="Y", price=Decimal("1"))
        assert rp.in_stock is True


# =========================================================================
# ScrapeResult
# =========================================================================


class TestScrapeResult:
    """Tests for the ``ScrapeResult`` dataclass and its properties."""

    def test_status_success(self):
        """Products present and no errors -> 'success'."""
        result = ScrapeResult(
            store_slug="tesco",
            products=[RawProduct(store_sku="A", name="A", price=Decimal("1"))],
            errors=[],
        )
        assert result.status == "success"

    def test_status_failed(self):
        """No products and at least one error -> 'failed'."""
        result = ScrapeResult(
            store_slug="tesco",
            products=[],
            errors=["Connection timeout"],
        )
        assert result.status == "failed"

    def test_status_partial(self):
        """Some products and some errors -> 'partial'."""
        result = ScrapeResult(
            store_slug="tesco",
            products=[RawProduct(store_sku="A", name="A", price=Decimal("1"))],
            errors=["One category failed"],
        )
        assert result.status == "partial"

    def test_status_success_no_products_no_errors(self):
        """No products and no errors -> 'success' (degenerate but valid)."""
        result = ScrapeResult(store_slug="tesco", products=[], errors=[])
        assert result.status == "success"

    def test_duration_seconds(self):
        start = datetime(2025, 6, 1, 10, 0, 0)
        end = datetime(2025, 6, 1, 10, 5, 30)
        result = ScrapeResult(
            store_slug="tesco",
            started_at=start,
            finished_at=end,
        )
        assert result.duration_seconds == 330.0

    def test_duration_zero(self):
        now = datetime(2025, 6, 1, 10, 0, 0)
        result = ScrapeResult(
            store_slug="tesco",
            started_at=now,
            finished_at=now,
        )
        assert result.duration_seconds == 0.0

    def test_default_factory_products(self):
        """products and errors should default to empty lists."""
        result = ScrapeResult(store_slug="supervalu")
        assert result.products == []
        assert result.errors == []

    def test_store_slug_stored(self):
        result = ScrapeResult(store_slug="dunnes")
        assert result.store_slug == "dunnes"


# =========================================================================
# random_user_agent
# =========================================================================


class TestRandomUserAgent:
    """Tests for ``random_user_agent``."""

    def test_returns_string(self):
        ua = random_user_agent()
        assert isinstance(ua, str)

    def test_returns_non_empty(self):
        ua = random_user_agent()
        assert len(ua) > 0

    def test_returns_from_user_agents_list(self):
        ua = random_user_agent()
        assert ua in USER_AGENTS

    def test_returns_vary(self):
        """Over many calls we should see more than one unique value
        (with very high probability given 5 agents)."""
        results = {random_user_agent() for _ in range(50)}
        assert len(results) > 1


# =========================================================================
# Module-level constants
# =========================================================================


class TestConstants:
    """Sanity checks on module-level constants."""

    def test_user_agents_not_empty(self):
        assert len(USER_AGENTS) > 0

    def test_default_headers_has_accept(self):
        assert "Accept" in DEFAULT_HEADERS

    def test_default_headers_has_accept_language(self):
        assert "Accept-Language" in DEFAULT_HEADERS
