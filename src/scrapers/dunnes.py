"""Scraper for Dunnes Stores (dunnesstores.com).

Dunnes has a JavaScript-heavy storefront with anti-bot protections.
We use Playwright exclusively, with user-agent rotation, random delays,
and careful DOM extraction.
"""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal, InvalidOperation

from playwright.async_api import Page

from src.scrapers.base import (
    BaseScraper,
    RawProduct,
    random_delay,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dunnesstores.com"

# Top-level food / grocery categories on Dunnes Stores
CATEGORY_PATHS = [
    "/c/food/fruit-and-vegetables",
    "/c/food/dairy",
    "/c/food/meat-poultry-and-fish",
    "/c/food/bakery",
    "/c/food/frozen",
    "/c/food/drinks",
    "/c/food/snacks-and-confectionery",
    "/c/food/cupboard-essentials",
    "/c/food/baby-and-toddler",
    "/c/food/household",
    "/c/food/health-and-beauty",
    "/c/food/deli-and-prepared-food",
    "/c/food/world-foods",
]


class DunnesScraper(BaseScraper):
    store_slug = "dunnes"

    # ------------------------------------------------------------------
    # Category URLs
    # ------------------------------------------------------------------
    async def get_category_urls(self) -> list[str]:
        return [f"{BASE_URL}{path}" for path in CATEGORY_PATHS]

    # ------------------------------------------------------------------
    # Scrape one category page (with pagination)
    # ------------------------------------------------------------------
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        products: list[RawProduct] = []

        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()

            logger.info("[dunnes] Loading %s", category_url)
            await page.goto(category_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)

            # Dismiss cookie / overlay banners
            await self._dismiss_overlays(page)

            # Keep loading more products until there is no "Load More" button
            page_num = 0
            while True:
                page_num += 1
                await self._scroll_page(page)
                await asyncio.sleep(1)

                batch = await self._extract_products(page, category_url)
                new_count = 0
                seen_skus = {p.store_sku for p in products}
                for p in batch:
                    if p.store_sku not in seen_skus:
                        products.append(p)
                        seen_skus.add(p.store_sku)
                        new_count += 1

                logger.info(
                    "[dunnes] Page %d: found %d tiles, %d new (total %d)",
                    page_num,
                    len(batch),
                    new_count,
                    len(products),
                )

                # Try clicking "Load More" or next-page button
                loaded_more = await self._click_load_more(page)
                if not loaded_more:
                    break

                await random_delay(1.5, 3.0)

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

        return products

    # ------------------------------------------------------------------
    # DOM extraction
    # ------------------------------------------------------------------
    async def _extract_products(self, page: Page, category_url: str) -> list[RawProduct]:
        """Extract product data from the currently loaded DOM."""
        products: list[RawProduct] = []

        # Dunnes uses product cards / tiles in their listing pages
        tiles = page.locator(
            "div[data-ref='productListItem'], "
            "div[class*='ProductCard'], "
            "li[class*='ProductCard'], "
            "article[class*='product-card'], "
            "div[class*='product-list-item']"
        )
        count = await tiles.count()

        for i in range(count):
            try:
                tile = tiles.nth(i)

                # --- Name + link ---
                name_el = tile.locator(
                    "a[class*='ProductCard__title'], "
                    "a[class*='product-card__title'], "
                    "a[data-ref='productCardTitle'], "
                    "p[class*='ProductCard__title'], "
                    "h3 a, "
                    "a[class*='Title']"
                )
                name = ""
                href = ""
                if await name_el.count() > 0:
                    name = (await name_el.first.inner_text()).strip()
                    href = await name_el.first.get_attribute("href") or ""

                if not name:
                    # Try alternative: any <a> with inner text
                    fallback_a = tile.locator("a")
                    if await fallback_a.count() > 0:
                        name = (await fallback_a.first.inner_text()).strip()
                        href = await fallback_a.first.get_attribute("href") or ""

                if not name:
                    continue

                # --- SKU ---
                sku = ""
                data_id = await tile.get_attribute("data-product-id") or ""
                data_sku = await tile.get_attribute("data-sku") or ""
                sku = data_id or data_sku
                if not sku and href:
                    sku_match = re.search(r"/p/(\d+)", href) or re.search(r"/(\d+)(?:\?|$)", href)
                    sku = sku_match.group(1) if sku_match else ""
                if not sku:
                    sku = f"dunnes-{hash(name) % 1000000}"

                # --- Price ---
                price_el = tile.locator(
                    "span[class*='Price__current'], "
                    "span[class*='ProductCard__price'], "
                    "span[data-ref='productCardPrice'], "
                    "span[class*='price-value'], "
                    "span.price"
                )
                price_text = ""
                if await price_el.count() > 0:
                    price_text = await price_el.first.inner_text()

                price = self._parse_price(price_text)
                if price is None or price == 0:
                    continue

                # --- Promo / was price ---
                promo_price = None
                promo_label = None
                promo_el = tile.locator(
                    "span[class*='Price__was'], "
                    "span[class*='price-was'], "
                    "span[class*='offer'], "
                    "div[class*='PromoBadge'], "
                    "span[data-ref='productCardPromo']"
                )
                if await promo_el.count() > 0:
                    promo_label = (await promo_el.first.inner_text()).strip() or None
                    # If there is a was-price, the current price is the promo price
                    was_text = promo_label or ""
                    was_match = re.search(r"(\d+[.,]\d{2})", was_text)
                    if was_match:
                        original = self._parse_price(was_match.group(1))
                        if original and original > price:
                            promo_price = price
                            price = original

                # --- Image ---
                image_url = None
                img_el = tile.locator("img")
                if await img_el.count() > 0:
                    image_url = (
                        await img_el.first.get_attribute("src")
                        or await img_el.first.get_attribute("data-src")
                    )
                    if image_url and image_url.startswith("//"):
                        image_url = f"https:{image_url}"

                # --- Unit price ---
                unit_price = None
                unit = None
                unit_el = tile.locator(
                    "span[class*='UnitPrice'], "
                    "span[class*='unit-price'], "
                    "span[data-ref='productCardUnitPrice']"
                )
                if await unit_el.count() > 0:
                    unit_text = await unit_el.first.inner_text()
                    up_match = re.search(r"([\d.]+)\s*/\s*(\w+)", unit_text)
                    if up_match:
                        try:
                            unit_price = Decimal(up_match.group(1))
                            unit = up_match.group(2).lower()
                        except (InvalidOperation, ValueError):
                            pass

                product_url = href
                if product_url and not product_url.startswith("http"):
                    product_url = f"{BASE_URL}{product_url}"

                # --- Brand (from name heuristic: first word(s) before product type) ---
                brand = None
                # Dunnes own-brand appears as "Dunnes Stores" in the name
                if name.lower().startswith("dunnes stores"):
                    brand = "Dunnes Stores"

                products.append(
                    RawProduct(
                        store_sku=sku,
                        name=name,
                        price=price,
                        promo_price=promo_price,
                        promo_label=promo_label,
                        unit_price=unit_price,
                        unit=unit,
                        brand=brand,
                        image_url=image_url,
                        product_url=product_url or None,
                    )
                )

            except Exception:
                logger.debug("[dunnes] Failed to parse tile %d", i, exc_info=True)

        return products

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_price(text: str) -> Decimal | None:
        """Extract a decimal price from text like '€3.49' or '3,49'."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", text.strip())
        cleaned = cleaned.replace(",", ".")
        try:
            return Decimal(cleaned) if cleaned else None
        except InvalidOperation:
            return None

    @staticmethod
    async def _dismiss_overlays(page: Page) -> None:
        """Click away cookie consent and other overlay banners."""
        for selector in [
            "button:has-text('Accept All')",
            "button:has-text('Accept Cookies')",
            "button:has-text('Accept')",
            "button[id*='cookie'] >> text=Accept",
            "button[class*='cookie'] >> text=Accept",
            "button[aria-label='Close']",
        ]:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                pass

    @staticmethod
    async def _scroll_page(page: Page, scrolls: int = 6) -> None:
        """Progressively scroll down to load lazy content."""
        for _ in range(scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(0.6)

    @staticmethod
    async def _click_load_more(page: Page) -> bool:
        """Try clicking a 'Load More' / pagination button. Return True if successful."""
        for selector in [
            "button:has-text('Load More')",
            "button:has-text('Show More')",
            "a:has-text('Load More')",
            "button[data-ref='loadMore']",
            "a[class*='pagination__next']",
            "a[rel='next']",
        ]:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                    return True
            except Exception:
                pass
        return False


# ------------------------------------------------------------------
# Standalone entry point
# ------------------------------------------------------------------
async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    )
    scraper = DunnesScraper()
    result = await scraper.run()
    print(f"\nDone: {result.status}")
    print(f"Products scraped: {len(result.products)}")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
