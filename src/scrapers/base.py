"""Base scraper abstract class and shared data structures."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from playwright.async_api import async_playwright, BrowserContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session
from src.core.models import Category, PriceRecord, Product, ScrapeRun, Store, StoreProduct

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common user-agent strings
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IE,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def random_user_agent() -> str:
    """Pick a random user-agent string."""
    return random.choice(USER_AGENTS)


async def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """Sleep for a random duration between *min_seconds* and *max_seconds*."""
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug("Sleeping for %.2f seconds", delay)
    await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class RawProduct:
    """Intermediate representation of a product scraped from a store."""

    store_sku: str
    name: str
    price: Decimal
    promo_price: Decimal | None = None
    promo_label: str | None = None
    unit_price: Decimal | None = None
    unit: str | None = None
    unit_size: Decimal | None = None
    brand: str | None = None
    ean: str | None = None
    category: str | None = None
    image_url: str | None = None
    product_url: str | None = None
    in_stock: bool = True


@dataclass
class ScrapeResult:
    """Container for the outcome of a full scrape run."""

    store_slug: str
    products: list[RawProduct] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def status(self) -> str:
        if not self.products and self.errors:
            return "failed"
        if self.products and self.errors:
            return "partial"
        return "success"

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


# ---------------------------------------------------------------------------
# Abstract base scraper
# ---------------------------------------------------------------------------
class BaseScraper(ABC):
    """Abstract base class that every store scraper inherits from.

    Sub-classes must define:
        * ``store_slug``  -- slug matching the ``stores`` table.
        * ``get_category_urls()``
        * ``scrape_category()``
    """

    store_slug: str

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def run(self) -> ScrapeResult:
        """Execute a full scrape and persist results."""
        result = ScrapeResult(
            store_slug=self.store_slug,
            started_at=datetime.utcnow(),
        )

        logger.info("[%s] Starting scrape run", self.store_slug)

        # Create a ScrapeRun record
        async with async_session() as session:
            store = await self._get_store(session)
            if store is None:
                msg = f"Store '{self.store_slug}' not found in database"
                logger.error(msg)
                result.errors.append(msg)
                result.finished_at = datetime.utcnow()
                return result

            scrape_run = ScrapeRun(store_id=store.id, status="running")
            session.add(scrape_run)
            await session.commit()
            scrape_run_id = scrape_run.id

        try:
            category_urls = await self.get_category_urls()
            logger.info("[%s] Found %d category URLs", self.store_slug, len(category_urls))

            for url in category_urls:
                try:
                    products = await self.scrape_category(url)
                    result.products.extend(products)
                    logger.info(
                        "[%s] Scraped %d products from %s",
                        self.store_slug,
                        len(products),
                        url,
                    )
                except Exception as exc:
                    msg = f"Error scraping {url}: {exc}"
                    logger.exception(msg)
                    result.errors.append(msg)

                await random_delay(1.0, 3.0)

        except Exception as exc:
            msg = f"Fatal error during scrape: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        result.finished_at = datetime.utcnow()

        # Persist products and update scrape run
        async with async_session() as session:
            try:
                await self.save_results(result.products, session)
            except Exception as exc:
                msg = f"Error saving results: {exc}"
                logger.exception(msg)
                result.errors.append(msg)

            # Update scrape run record
            run = await session.get(ScrapeRun, scrape_run_id)
            if run:
                run.finished_at = result.finished_at
                run.status = result.status
                run.products_scraped = len(result.products)
                run.errors = json.dumps(result.errors) if result.errors else None
                await session.commit()

        logger.info(
            "[%s] Scrape finished: status=%s  products=%d  errors=%d  duration=%.1fs",
            self.store_slug,
            result.status,
            len(result.products),
            len(result.errors),
            result.duration_seconds,
        )
        return result

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------
    @abstractmethod
    async def get_category_urls(self) -> list[str]:
        """Return the list of category page URLs to scrape."""

    @abstractmethod
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        """Scrape all products from a single category page/URL."""

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    async def save_results(
        self, products: list[RawProduct], session: AsyncSession
    ) -> None:
        """Persist scraped products.

        For each ``RawProduct``:
        1. Find the ``Store`` by *self.store_slug*.
        2. Try to find an existing ``StoreProduct`` by *(store_id, store_sku)*.
        3. If none exists, optionally try matching by EAN.
        4. Create ``Product`` / ``StoreProduct`` as needed.
        5. Always create a new ``PriceRecord``.
        """
        store = await self._get_store(session)
        if store is None:
            logger.error("Store '%s' not found – cannot save results", self.store_slug)
            return

        saved = 0
        for raw in products:
            try:
                # ---- try to find existing StoreProduct ----
                stmt = select(StoreProduct).where(
                    StoreProduct.store_id == store.id,
                    StoreProduct.store_sku == raw.store_sku,
                )
                result = await session.execute(stmt)
                store_product = result.scalar_one_or_none()

                if store_product is None:
                    # Try to match by EAN if available
                    product: Product | None = None
                    if raw.ean:
                        stmt_ean = select(Product).where(Product.ean == raw.ean)
                        res_ean = await session.execute(stmt_ean)
                        product = res_ean.scalar_one_or_none()

                    # Resolve category if given
                    category_id: int | None = None
                    if raw.category:
                        cat_slug = raw.category.lower().replace(" ", "-").replace("&", "and")
                        stmt_cat = select(Category).where(Category.slug == cat_slug)
                        res_cat = await session.execute(stmt_cat)
                        category = res_cat.scalar_one_or_none()
                        if category is None:
                            category = Category(name=raw.category, slug=cat_slug)
                            session.add(category)
                            await session.flush()
                        category_id = category.id

                    if product is None:
                        product = Product(
                            name=raw.name,
                            brand=raw.brand,
                            ean=raw.ean,
                            category_id=category_id,
                            unit=raw.unit,
                            unit_size=raw.unit_size,
                            image_url=raw.image_url,
                        )
                        session.add(product)
                        await session.flush()

                    store_product = StoreProduct(
                        product_id=product.id,
                        store_id=store.id,
                        store_sku=raw.store_sku,
                        store_name=raw.name,
                        store_url=raw.product_url,
                        is_active=True,
                    )
                    session.add(store_product)
                    await session.flush()
                else:
                    # Update existing StoreProduct metadata
                    store_product.store_name = raw.name
                    if raw.product_url:
                        store_product.store_url = raw.product_url
                    store_product.is_active = True

                # ---- Always create a price record ----
                price_record = PriceRecord(
                    store_product_id=store_product.id,
                    price=raw.price,
                    promo_price=raw.promo_price,
                    promo_label=raw.promo_label,
                    unit_price=raw.unit_price,
                    in_stock=raw.in_stock,
                )
                session.add(price_record)
                saved += 1

            except Exception:
                logger.exception(
                    "[%s] Failed to save product sku=%s name=%s",
                    self.store_slug,
                    raw.store_sku,
                    raw.name,
                )

        await session.commit()
        logger.info("[%s] Saved %d / %d products", self.store_slug, saved, len(products))

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    async def _get_store(self, session: AsyncSession) -> Store | None:
        stmt = select(Store).where(Store.slug == self.store_slug)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_browser_context(
        headless: bool = True,
        **extra_context_kwargs,
    ) -> tuple:
        """Create and return ``(playwright, browser, context)``.

        Caller is responsible for closing them via::

            await context.close()
            await browser.close()
            await pw.stop()
        """
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=random_user_agent(),
            viewport={"width": 1366, "height": 768},
            locale="en-IE",
            timezone_id="Europe/Dublin",
            **extra_context_kwargs,
        )
        # Block unnecessary resources to speed up scraping
        await context.route(
            "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )
        return pw, browser, context
