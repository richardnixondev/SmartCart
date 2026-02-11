"""Tests for the SmartCart FastAPI endpoints."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.api.schemas import CategoryOut, ProductOut, StoreOut
from src.core.database import get_session
from src.core.models import Category, Product, Store


# =========================================================================
# /health
# =========================================================================


class TestHealthCheck:
    """Tests for ``GET /health``."""

    async def test_health_check(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok"}


# =========================================================================
# /
# =========================================================================


class TestRoot:
    """Tests for ``GET /`` redirect."""

    async def test_root_redirects_to_docs(self, client):
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"


# =========================================================================
# /api/stores
# =========================================================================


class TestListStores:
    """Tests for ``GET /api/stores``."""

    async def test_list_stores_empty(self, client, mock_session):
        """When the database has no stores, return an empty list."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/stores")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_stores(self, client, mock_session, sample_store, sample_store_2):
        """Return a list of stores from the database."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [sample_store, sample_store_2]
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/stores")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Tesco"
        assert data[0]["slug"] == "tesco"
        assert data[1]["name"] == "SuperValu"
        assert data[1]["slug"] == "supervalu"

    async def test_list_stores_schema(self, client, mock_session, sample_store):
        """Verify the response matches the StoreOut schema."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [sample_store]
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/stores")
        assert response.status_code == 200
        data = response.json()
        store = data[0]
        assert "id" in store
        assert "name" in store
        assert "slug" in store
        assert "base_url" in store
        assert "logo_url" in store


# =========================================================================
# /api/categories
# =========================================================================


class TestListCategories:
    """Tests for ``GET /api/categories``."""

    async def test_list_categories_empty(self, client, mock_session):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/categories")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_categories(self, client, mock_session, sample_category):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [sample_category]
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Dairy"
        assert data[0]["slug"] == "dairy"


# =========================================================================
# /api/products
# =========================================================================


class TestListProducts:
    """Tests for ``GET /api/products``."""

    async def test_list_products_empty(self, client, mock_session):
        """Empty database returns zero items."""
        # list_products calls execute twice: once for count, once for results
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, products_result]

        response = await client.get("/api/products")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_products(self, client, mock_session, sample_product):
        """Return a paginated list of products."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = [sample_product]

        mock_session.execute.side_effect = [count_result, products_result]

        response = await client.get("/api/products")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Avonmore Full Cream Milk 2L"

    async def test_list_products_pagination_params(self, client, mock_session):
        """Verify pagination query parameters are accepted."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, products_result]

        response = await client.get("/api/products?page=2&limit=10")
        assert response.status_code == 200

    async def test_list_products_search_param(self, client, mock_session):
        """Verify the search query parameter is accepted."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, products_result]

        response = await client.get("/api/products?search=milk")
        assert response.status_code == 200


# =========================================================================
# /api/products/{product_id}
# =========================================================================


class TestGetProduct:
    """Tests for ``GET /api/products/{product_id}``."""

    async def test_get_product_not_found(self, client, mock_session):
        """A non-existent product should return 404."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/products/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Product not found"

    async def test_get_product_found(self, client, mock_session, sample_product):
        """An existing product should return 200 with product data."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = sample_product
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/products/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Avonmore Full Cream Milk 2L"
        assert data["brand"] == "Avonmore"
        assert data["ean"] == "5391516590123"
        assert data["unit"] == "l"
        assert data["category"] is not None
        assert data["category"]["name"] == "Dairy"

    async def test_get_product_no_category(self, client, mock_session, sample_product_no_ean):
        """A product with no category should return null for category."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = sample_product_no_ean
        mock_session.execute.return_value = result_mock

        response = await client.get("/api/products/2")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 2
        assert data["category"] is None
        assert data["ean"] is None
