"""Product name normalizer for cross-store matching."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Common noise words to strip from product names
NOISE_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "&",
        "of",
        "for",
        "with",
        "in",
        "on",
        "at",
        "to",
        "from",
        "or",
        "fresh",
        "new",
        "best",
        "finest",
        "premium",
        "quality",
        "selected",
        "selection",
        "range",
        "irish",
        "ireland",
        "approx",
        "approximately",
        "min",
        "minimum",
        "each",
        "per",
        "pk",
        "pack",
        "pkt",
    }
)

# Unit aliases mapping to canonical forms
UNIT_ALIASES: dict[re.Pattern, str] = {
    re.compile(r"\blitres?\b", re.IGNORECASE): "l",
    re.compile(r"\bliters?\b", re.IGNORECASE): "l",
    re.compile(r"\bltr?\b", re.IGNORECASE): "l",
    re.compile(r"\bmillilitres?\b", re.IGNORECASE): "ml",
    re.compile(r"\bmilliliters?\b", re.IGNORECASE): "ml",
    re.compile(r"\bkilograms?\b", re.IGNORECASE): "kg",
    re.compile(r"\bkilos?\b", re.IGNORECASE): "kg",
    re.compile(r"\bgrams?\b", re.IGNORECASE): "g",
    re.compile(r"\bgms?\b", re.IGNORECASE): "g",
    re.compile(r"\bcentimetres?\b", re.IGNORECASE): "cm",
    re.compile(r"\bcentimeters?\b", re.IGNORECASE): "cm",
    re.compile(r"\bmillimetres?\b", re.IGNORECASE): "mm",
    re.compile(r"\bmillimeters?\b", re.IGNORECASE): "mm",
    re.compile(r"\bpieces?\b", re.IGNORECASE): "pcs",
    re.compile(r"\bsheets?\b", re.IGNORECASE): "sht",
    re.compile(r"\bcapsules?\b", re.IGNORECASE): "cap",
    re.compile(r"\btablets?\b", re.IGNORECASE): "tab",
}

# Pattern to detect quantity + unit (e.g., "500ml", "1.5 L", "2 Litres")
QUANTITY_UNIT_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(ml|l|kg|g|cl|oz|fl\s*oz|cm|mm|pcs|sht|cap|tab)\b",
    re.IGNORECASE,
)

# Known major brands in Irish supermarkets (non-exhaustive starter list)
KNOWN_BRANDS = [
    "Avonmore",
    "Brennans",
    "Barry's",
    "Bewley's",
    "Birds Eye",
    "Bord Bia",
    "Brady Family",
    "Cadbury",
    "Carte D'Or",
    "Chef",
    "Club",
    "Coca-Cola",
    "Coke",
    "Colgate",
    "Connacht Gold",
    "Dairygold",
    "Denny",
    "Dolmio",
    "Donegal Catch",
    "Dr Oetker",
    "Dunnes",
    "Fairy",
    "Flora",
    "Galtee",
    "Glenisk",
    "Goodfellas",
    "Green Isle",
    "Heinz",
    "HB",
    "Jacob's",
    "Keeling's",
    "Kellogg's",
    "Kerry Gold",
    "Kerrygold",
    "KitKat",
    "Knorr",
    "Lidl",
    "Lucozade",
    "Lyons",
    "Manor Farm",
    "McCain",
    "McVitie's",
    "Miwadi",
    "Muller",
    "Nestlé",
    "O'Brien's",
    "Odlums",
    "Paddy's",
    "Pepsi",
    "Pringles",
    "Richmond",
    "Roma",
    "Siucra",
    "SuperValu",
    "Tayto",
    "Tesco",
    "Weetabix",
    "Yoplait",
]

# Pre-compile brand patterns for performance
_BRAND_PATTERNS = [
    (brand, re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE)) for brand in KNOWN_BRANDS
]


def normalize_name(name: str) -> str:
    """Normalize a product name for comparison.

    - Lowercase
    - Standardize unit representations (1L -> 1l, 1 Litre -> 1l, 500ml -> 500ml, etc.)
    - Remove extra whitespace
    - Remove common noise words
    """
    if not name:
        return ""

    text = name.lower().strip()

    # Replace unit aliases with canonical forms
    for pattern, replacement in UNIT_ALIASES.items():
        text = pattern.sub(replacement, text)

    # Standardize quantity+unit patterns: remove spaces between number and unit
    # e.g., "1 l" -> "1l", "500 ml" -> "500ml"
    def _collapse_unit(match: re.Match) -> str:
        qty = match.group(1).replace(",", ".")
        unit = match.group(2).lower().replace(" ", "")
        return f"{qty}{unit}"

    text = QUANTITY_UNIT_PATTERN.sub(_collapse_unit, text)

    # Remove noise words
    tokens = text.split()
    tokens = [t for t in tokens if t not in NOISE_WORDS]

    # Collapse whitespace
    text = " ".join(tokens)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def extract_brand(name: str) -> str | None:
    """Try to extract a brand name from a product name.

    Returns the first known brand found, or None.
    """
    if not name:
        return None

    for brand, pattern in _BRAND_PATTERNS:
        if pattern.search(name):
            return brand

    # Heuristic: the first capitalised word might be a brand if it is not
    # a generic grocery term.
    tokens = name.split()
    if tokens and tokens[0][0:1].isupper() and tokens[0].lower() not in NOISE_WORDS:
        candidate = tokens[0]
        # Only accept if it looks like a proper noun (not a generic word)
        if len(candidate) >= 2 and not candidate.isupper():
            return candidate

    return None


def extract_unit_info(name: str) -> tuple[str | None, Decimal | None]:
    """Extract unit type and size from a product name.

    Examples:
        "Milk 2L"   -> ("l", Decimal("2"))
        "Rice 500g" -> ("g", Decimal("500"))
        "Juice 1.5 Litres" -> ("l", Decimal("1.5"))

    Returns (unit, size) or (None, None) if not found.
    """
    if not name:
        return None, None

    # Normalize unit words first so '1 Litre' becomes '1 l' etc.
    text = name
    for pattern, replacement in UNIT_ALIASES.items():
        text = pattern.sub(replacement, text)

    match = QUANTITY_UNIT_PATTERN.search(text)
    if not match:
        return None, None

    raw_qty = match.group(1).replace(",", ".")
    unit = match.group(2).lower().replace(" ", "")

    try:
        size = Decimal(raw_qty)
    except InvalidOperation:
        return None, None

    return unit, size
