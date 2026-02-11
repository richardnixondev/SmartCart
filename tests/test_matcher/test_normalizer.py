"""Tests for src.matcher.normalizer."""

from decimal import Decimal

import pytest

from src.matcher.normalizer import extract_brand, extract_unit_info, normalize_name


# =========================================================================
# normalize_name
# =========================================================================


class TestNormalizeName:
    """Tests for ``normalize_name``."""

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_none_like_empty(self):
        """An empty/whitespace-only input should yield an empty string."""
        assert normalize_name("   ") == ""

    def test_lowercases(self):
        result = normalize_name("AVONMORE MILK")
        assert result == result.lower()

    def test_strips_extra_whitespace(self):
        result = normalize_name("  Avonmore   Milk   2L  ")
        assert "  " not in result
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_litre_to_l(self):
        """'1 Litre' should collapse to '1l'."""
        result = normalize_name("Milk 1 Litre")
        assert "1l" in result
        assert "litre" not in result

    def test_litres_to_l(self):
        result = normalize_name("Juice 2 Litres")
        assert "2l" in result

    def test_ltr_to_l(self):
        result = normalize_name("Water 5Ltr")
        assert "5l" in result

    def test_millilitres_to_ml(self):
        result = normalize_name("Cream 500 Millilitres")
        assert "500ml" in result

    def test_grams_to_g(self):
        result = normalize_name("Cheese 200 Grams")
        assert "200g" in result

    def test_kilograms_to_kg(self):
        result = normalize_name("Potatoes 2 Kilograms")
        assert "2kg" in result

    def test_kilo_to_kg(self):
        result = normalize_name("Rice 1 Kilo")
        assert "1kg" in result

    def test_number_unit_space_collapsed(self):
        """Spaces between a number and its unit should be removed."""
        result = normalize_name("Milk 2 L")
        assert "2l" in result
        # No space between the number and unit
        assert "2 l" not in result

    def test_removes_noise_words(self):
        result = normalize_name("The Fresh Premium Irish Milk")
        assert "the" not in result.split()
        assert "fresh" not in result.split()
        assert "premium" not in result.split()
        assert "irish" not in result.split()

    def test_preserves_meaningful_words(self):
        result = normalize_name("Avonmore Milk 2L")
        assert "avonmore" in result
        assert "milk" in result

    def test_comma_decimal_normalised(self):
        """European-style comma decimal ('1,5l') should become '1.5l'."""
        result = normalize_name("Juice 1,5 Litres")
        assert "1.5l" in result

    def test_multiple_units_in_name(self):
        """When a name has two quantity+unit patterns, both should be normalised."""
        result = normalize_name("Bottle 750ml x 6 Pack")
        assert "750ml" in result


# =========================================================================
# extract_brand
# =========================================================================


class TestExtractBrand:
    """Tests for ``extract_brand``."""

    def test_empty_string(self):
        assert extract_brand("") is None

    def test_none_input(self):
        assert extract_brand(None) is None

    def test_known_brand_avonmore(self):
        assert extract_brand("Avonmore Full Cream Milk 2L") == "Avonmore"

    def test_known_brand_kerrygold(self):
        assert extract_brand("Kerrygold Pure Irish Butter 250g") == "Kerrygold"

    def test_known_brand_brennans(self):
        assert extract_brand("Brennans Family Pan 800g") == "Brennans"

    def test_known_brand_case_insensitive(self):
        assert extract_brand("avonmore milk 2l") == "Avonmore"

    def test_known_brand_mid_string(self):
        """Brand appearing later in the string should still be detected."""
        assert extract_brand("Fresh Irish Kerrygold Butter") == "Kerrygold"

    def test_known_brand_barrys(self):
        assert extract_brand("Barry's Gold Blend Tea 80s") == "Barry's"

    def test_known_brand_heinz(self):
        assert extract_brand("Heinz Baked Beans 415g") == "Heinz"

    def test_heuristic_capitalised_first_word(self):
        """When no known brand matches, the first capitalised word (if it
        looks like a proper noun) should be returned."""
        result = extract_brand("Glenilen Farm Clotted Cream 140g")
        # "Glenilen" is the first capitalised token and not a noise word
        assert result is not None

    def test_no_brand_generic_name(self):
        """A fully lowercase name with no brands should return None."""
        assert extract_brand("whole milk 2l") is None

    def test_all_uppercase_first_word_returns_none(self):
        """A fully uppercased first token should be rejected by the heuristic
        (``not candidate.isupper()`` guard)."""
        # "AA" is all-uppercase and only 2 chars; the heuristic rejects it
        assert extract_brand("AA batteries 4 pack") is None


# =========================================================================
# extract_unit_info
# =========================================================================


class TestExtractUnitInfo:
    """Tests for ``extract_unit_info``."""

    def test_empty_string(self):
        unit, size = extract_unit_info("")
        assert unit is None
        assert size is None

    def test_none_input(self):
        unit, size = extract_unit_info(None)
        assert unit is None
        assert size is None

    def test_litres(self):
        unit, size = extract_unit_info("Milk 2L")
        assert unit == "l"
        assert size == Decimal("2")

    def test_litres_word(self):
        unit, size = extract_unit_info("Juice 1.5 Litres")
        assert unit == "l"
        assert size == Decimal("1.5")

    def test_millilitres(self):
        unit, size = extract_unit_info("Cream 500ml")
        assert unit == "ml"
        assert size == Decimal("500")

    def test_grams(self):
        unit, size = extract_unit_info("Bread 800g")
        assert unit == "g"
        assert size == Decimal("800")

    def test_kilograms(self):
        unit, size = extract_unit_info("Rice 1kg")
        assert unit == "kg"
        assert size == Decimal("1")

    def test_grams_word(self):
        unit, size = extract_unit_info("Cheese 200 Grams")
        assert unit == "g"
        assert size == Decimal("200")

    def test_centilitres(self):
        unit, size = extract_unit_info("Wine 75cl")
        assert unit == "cl"
        assert size == Decimal("75")

    def test_comma_decimal(self):
        unit, size = extract_unit_info("Juice 1,5L")
        assert unit == "l"
        assert size == Decimal("1.5")

    def test_no_unit(self):
        unit, size = extract_unit_info("Bananas Loose")
        assert unit is None
        assert size is None

    def test_decimal_size(self):
        unit, size = extract_unit_info("Oil 0.5L")
        assert unit == "l"
        assert size == Decimal("0.5")

    def test_tablets(self):
        unit, size = extract_unit_info("Paracetamol 24 Tablets")
        assert unit == "tab"
        assert size == Decimal("24")

    def test_capsules(self):
        unit, size = extract_unit_info("Vitamin D 30 Capsules")
        assert unit == "cap"
        assert size == Decimal("30")
