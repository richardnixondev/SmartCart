"""Tests for src.matcher.matcher."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.core.models import Product
from src.matcher.matcher import RawProduct, ean_match, find_match, fuzzy_match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product(
    id: int,
    name: str,
    ean: str | None = None,
    brand: str | None = None,
    unit: str | None = None,
    unit_size: Decimal | None = None,
) -> Product:
    """Create a lightweight Product instance for testing without a database."""
    p = Product.__new__(Product)
    p.id = id
    p.name = name
    p.ean = ean
    p.brand = brand
    p.unit = unit
    p.unit_size = unit_size
    p.category_id = None
    p.image_url = None
    return p


# =========================================================================
# ean_match
# =========================================================================


class TestEanMatch:
    """Tests for ``ean_match``."""

    def test_ean_match_found(self):
        product = _make_product(1, "Milk 2L", ean="5391516590123")
        candidates = [
            _make_product(2, "Full Cream Milk 2L", ean="5391516590123"),
            _make_product(3, "Skimmed Milk 1L", ean="5391516590456"),
        ]
        result = ean_match(product, candidates)
        assert result is not None
        assert result.id == 2
        assert result.ean == "5391516590123"

    def test_ean_match_not_found(self):
        product = _make_product(1, "Milk 2L", ean="0000000000000")
        candidates = [
            _make_product(2, "Full Cream Milk 2L", ean="5391516590123"),
            _make_product(3, "Skimmed Milk 1L", ean="5391516590456"),
        ]
        result = ean_match(product, candidates)
        assert result is None

    def test_ean_match_no_ean_on_product(self):
        """If the product has no EAN, ean_match returns None immediately."""
        product = _make_product(1, "Milk 2L", ean=None)
        candidates = [
            _make_product(2, "Full Cream Milk 2L", ean="5391516590123"),
        ]
        result = ean_match(product, candidates)
        assert result is None

    def test_ean_match_skips_self(self):
        """ean_match should not match a product against itself."""
        product = _make_product(1, "Milk 2L", ean="5391516590123")
        candidates = [product]
        result = ean_match(product, candidates)
        assert result is None

    def test_ean_match_empty_candidates(self):
        product = _make_product(1, "Milk 2L", ean="5391516590123")
        result = ean_match(product, [])
        assert result is None

    def test_ean_match_candidate_no_ean(self):
        """Candidates without EANs should be skipped."""
        product = _make_product(1, "Milk 2L", ean="5391516590123")
        candidates = [
            _make_product(2, "Milk 2L", ean=None),
        ]
        result = ean_match(product, candidates)
        assert result is None


# =========================================================================
# fuzzy_match
# =========================================================================


class TestFuzzyMatch:
    """Tests for ``fuzzy_match``."""

    def test_fuzzy_match_above_threshold(self):
        """Very similar names should match above the default threshold."""
        candidates = [
            _make_product(1, "Avonmore Full Cream Milk 2L"),
        ]
        result = fuzzy_match("Avonmore Fresh Milk Full Cream 2L", candidates)
        assert result is not None
        assert result.id == 1

    def test_fuzzy_match_below_threshold(self):
        """Completely different names should not match."""
        candidates = [
            _make_product(1, "Heinz Baked Beans 415g"),
        ]
        result = fuzzy_match("Avonmore Full Cream Milk 2L", candidates)
        assert result is None

    def test_fuzzy_match_picks_best(self):
        """When multiple candidates exist, the best match should be returned."""
        candidates = [
            _make_product(1, "Brennans White Bread 800g"),
            _make_product(2, "Brennans Wholemeal Bread 800g"),
        ]
        result = fuzzy_match("Brennans White Sliced Pan 800g", candidates)
        assert result is not None
        # The white bread should be a closer match than wholemeal
        assert result.id == 1

    def test_fuzzy_match_custom_threshold(self):
        """A very high threshold should reject moderate matches."""
        candidates = [
            _make_product(1, "Avonmore Milk 2L"),
        ]
        result = fuzzy_match("Avonmore Super Milk 1L", candidates, threshold=99.0)
        assert result is None

    def test_fuzzy_match_empty_name(self):
        candidates = [_make_product(1, "Milk 2L")]
        result = fuzzy_match("", candidates)
        assert result is None

    def test_fuzzy_match_empty_candidates(self):
        result = fuzzy_match("Avonmore Milk 2L", [])
        assert result is None

    def test_fuzzy_match_word_order_invariant(self):
        """token_sort_ratio should handle reordered words."""
        candidates = [
            _make_product(1, "Kerrygold Irish Butter 250g"),
        ]
        result = fuzzy_match("Irish Butter Kerrygold 250g", candidates)
        assert result is not None
        assert result.id == 1


# =========================================================================
# find_match
# =========================================================================


class TestFindMatch:
    """Tests for ``find_match``."""

    def test_find_match_prefers_ean(self):
        """When EAN matches, it should be returned even if names differ."""
        raw = RawProduct(name="Completely Different Name", ean="5391516590123")
        existing = [
            _make_product(1, "Avonmore Milk 2L", ean="5391516590123"),
            _make_product(2, "Something Else 500ml", ean="9999999999999"),
        ]
        result = find_match(raw, existing)
        assert result is not None
        assert result.id == 1

    def test_find_match_falls_back_to_fuzzy(self):
        """With no EAN on the raw product, find_match should use fuzzy matching."""
        raw = RawProduct(name="Avonmore Full Cream Milk 2L", ean=None)
        existing = [
            _make_product(1, "Avonmore Fresh Full Cream Milk 2L", ean="5391516590123"),
        ]
        result = find_match(raw, existing)
        assert result is not None
        assert result.id == 1

    def test_find_match_no_match(self):
        """Completely unrelated products should not match."""
        raw = RawProduct(name="Heinz Baked Beans 415g", ean=None)
        existing = [
            _make_product(1, "Avonmore Milk 2L", ean="5391516590123"),
        ]
        result = find_match(raw, existing)
        assert result is None

    def test_find_match_rejects_unit_mismatch(self):
        """If names are similar but unit info differs, find_match should
        reject the match to avoid merging different sizes."""
        raw = RawProduct(name="Avonmore Milk 1L", ean=None)
        existing = [
            _make_product(1, "Avonmore Milk 2L"),
        ]
        result = find_match(raw, existing)
        assert result is None

    def test_find_match_ean_no_candidates(self):
        raw = RawProduct(name="Milk", ean="5391516590123")
        result = find_match(raw, [])
        assert result is None

    def test_find_match_accepts_matching_units(self):
        """When names and units both match, the product should be returned."""
        raw = RawProduct(name="Avonmore Milk 2L", ean=None)
        existing = [
            _make_product(1, "Avonmore Fresh Milk 2L"),
        ]
        result = find_match(raw, existing)
        assert result is not None
        assert result.id == 1
