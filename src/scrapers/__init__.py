"""SmartCart scrapers for Irish supermarkets."""

from src.scrapers.aldi import AldiScraper
from src.scrapers.base import BaseScraper, RawProduct, ScrapeResult
from src.scrapers.dunnes import DunnesScraper
from src.scrapers.lidl import LidlScraper
from src.scrapers.supervalu import SuperValuScraper
from src.scrapers.tesco import TescoScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "tesco": TescoScraper,
    "dunnes": DunnesScraper,
    "supervalu": SuperValuScraper,
    "aldi": AldiScraper,
    "lidl": LidlScraper,
}

__all__ = [
    "BaseScraper",
    "RawProduct",
    "ScrapeResult",
    "TescoScraper",
    "DunnesScraper",
    "SuperValuScraper",
    "AldiScraper",
    "LidlScraper",
    "SCRAPERS",
]
