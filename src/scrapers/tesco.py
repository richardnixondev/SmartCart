"""Scraper for Tesco Ireland (tesco.ie).

Tesco's grocery site relies heavily on XHR calls to internal APIs.  We use
Playwright to load category pages and intercept the JSON API responses that
contain the product listings.  If interception fails we fall back to DOM
scraping.
"""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal, InvalidOperation

from playwright.async_api import Page, Response

from src.scrapers.base import (
    BaseScraper,
    RawProduct,
    ScrapeResult,
    random_delay,
    random_user_agent,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tesco.ie"
GROCERIES_BASE = f"{BASE_URL}/groceries/en-IE"

# Top-level grocery categories on Tesco Ireland
CATEGORY_SLUGS = [
    "fresh-food",
    "bakery",
    "frozen-food",
    "food-cupboard",
    "drinks",
    "baby",
    "health-and-beauty",
    "household",
    "pets",
    "dairy-eggs-and-chilled",
]


class TescoScraper(BaseScraper):
    store_slug = "tesco"

    # ------------------------------------------------------------------
    # Category discovery
    # ------------------------------------------------------------------
    async def get_category_urls(self) -> list[str]:
        """Return top-level Tesco grocery category URLs."""
        return [f"{GROCERIES_BASE}/shop/{slug}/all" for slug in CATEGORY_SLUGS]

    # ------------------------------------------------------------------
    # Scrape a single category
    # ------------------------------------------------------------------
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        """Load a Tesco category page, intercept API responses, and parse products."""
        products: list[RawProduct] = []
        api_products: list[dict] = []

        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()

            # Intercept the product listing API response
            async def _handle_response(response: Response) -> None:
                url = response.url
                if "/resources/products/" in url or "/search?" in url:
                    try:
                        body = await response.json()
                        if isinstance(body, dict):
                            # Tesco returns products under "results" or "productItems"
                            items = (
                                body.get("results", [])
                                or body.get("productItems", [])
                                or body.get("data", {}).get("results", {}).get("productItems", [])
                            )
                            if isinstance(items, list):
                                api_products.extend(items)
                    except Exception:
                        pass

            page.on("response", _handle_response)

            logger.info("[tesco] Loading %s", category_url)
            await page.goto(category_url, wait_until="networkidle", timeout=60_000)
            await asyncio.sleep(2)

            # Handle cookie consent banner if present
            try:
                accept_btn = page.locator("button:has-text('Accept All Cookies')")
                if await accept_btn.count() > 0:
                    await accept_btn.first.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Scroll down to trigger lazy-loading of additional products
            await self._scroll_page(page)

            # Attempt pagination — Tesco uses "Show more" or numbered pages
            while True:
                try:
                    show_more = page.locator(
                        "a[data-auto='load-more'], "
                        "button[data-auto='load-more'], "
                        "a.pagination--page-selector-next"
                    )
                    if await show_more.count() > 0 and await show_more.first.is_visible():
                        await show_more.first.click()
                        await page.wait_for_load_state("networkidle", timeout=15_000)
                        await asyncio.sleep(1.5)
                        await self._scroll_page(page)
                    else:
                        break
                except Exception:
                    break

            # --- Parse products from intercepted API data ---
            if api_products:
                logger.info("[tesco] Intercepted %d API product items", len(api_products))
                for item in api_products:
                    try:
                        product = self._parse_api_product(item)
                        if product:
                            products.append(product)
                    except Exception:
                        logger.debug("[tesco] Failed to parse API product item", exc_info=True)

            # --- Fallback: DOM scraping if we got nothing from the API ---
            if not products:
                logger.info("[tesco] Falling back to DOM scraping for %s", category_url)
                products = await self._scrape_dom(page, category_url)

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

        return products

    # ------------------------------------------------------------------
    # API response parser
    # ------------------------------------------------------------------
    def _parse_api_product(self, item: dict) -> RawProduct | None:
        """Parse a product dict from Tesco's API response."""
        # Tesco wraps product data in different shapes depending on the endpoint
        product_data = item.get("product", item)

        sku = str(product_data.get("id", product_data.get("tpnb", "")))
        name = product_data.get("title", product_data.get("name", ""))
        if not sku or not name:
            return None

        price_str = (
            product_data.get("price", "")
            or product_data.get("retailPrice", {}).get("price", "")
        )
        try:
            price = Decimal(str(price_str))
        except (InvalidOperation, TypeError, ValueError):
            return None

        # Promo / clubcard price
        promo_price = None
        promo_label = None
        offer = product_data.get("promotions") or product_data.get("offers") or []
        if isinstance(offer, list) and offer:
            first_offer = offer[0] if isinstance(offer[0], dict) else {}
            promo_label = first_offer.get("offerText", first_offer.get("description"))
            promo_price_val = first_offer.get("price")
            if promo_price_val is not None:
                try:
                    promo_price = Decimal(str(promo_price_val))
                except (InvalidOperation, TypeError):
                    pass

        # Unit price
        unit_price = None
        unit = None
        unit_price_raw = product_data.get("unitPrice", product_data.get("unitOfMeasurePrice"))
        if isinstance(unit_price_raw, dict):
            try:
                unit_price = Decimal(str(unit_price_raw.get("price", "")))
            except (InvalidOperation, TypeError, ValueError):
                pass
            unit = unit_price_raw.get("unit", unit_price_raw.get("measure"))
        elif unit_price_raw is not None:
            try:
                unit_price = Decimal(str(unit_price_raw))
            except (InvalidOperation, TypeError, ValueError):
                pass

        # Unit size from the title  e.g. "Avonmore Milk 2L"
        unit_size = None
        size_match = re.search(r"(\d+(?:\.\d+)?)\s*(ml|l|g|kg|cl)\b", name, re.IGNORECASE)
        if size_match:
            try:
                unit_size = Decimal(size_match.group(1))
                unit = unit or size_match.group(2).lower()
            except (InvalidOperation, ValueError):
                pass

        brand = product_data.get("brand", product_data.get("brandName"))
        ean = product_data.get("ean", product_data.get("gtin"))
        image_url = product_data.get("defaultImageUrl", product_data.get("imageUrl", ""))
        if image_url and image_url.startswith("//"):
            image_url = f"https:{image_url}"

        product_url = product_data.get("productUrl", product_data.get("href", ""))
        if product_url and not product_url.startswith("http"):
            product_url = f"{BASE_URL}{product_url}"

        in_stock = product_data.get("isAvailable", product_data.get("status", "")) != "OutOfStock"
        if isinstance(in_stock, str):
            in_stock = in_stock.lower() not in ("false", "outofstock", "unavailable")

        return RawProduct(
            store_sku=sku,
            name=name.strip(),
            price=price,
            promo_price=promo_price,
            promo_label=promo_label,
            unit_price=unit_price,
            unit=unit,
            unit_size=unit_size,
            brand=brand,
            ean=str(ean) if ean else None,
            image_url=image_url or None,
            product_url=product_url or None,
            in_stock=bool(in_stock),
        )

    # ------------------------------------------------------------------
    # DOM fallback
    # ------------------------------------------------------------------
    async def _scrape_dom(self, page: Page, category_url: str) -> list[RawProduct]:
        """Scrape product data directly from the rendered DOM."""
        products: list[RawProduct] = []

        # Tesco uses product tiles in the category listing
        product_tiles = page.locator(
            "li[class*='product-list--list-item'], "
            "div[data-auto='product-tile'], "
            "div[class*='product-tile-wrapper']"
        )
        count = await product_tiles.count()
        logger.info("[tesco] Found %d product tiles in DOM", count)

        for i in range(count):
            try:
                tile = product_tiles.nth(i)

                # Product name / link
                name_el = tile.locator(
                    "a[data-auto='product-tile--title'], "
                    "a[class*='product-tile--title'], "
                    "h3 a, "
                    "a.product-title"
                )
                name = (await name_el.first.inner_text()).strip() if await name_el.count() > 0 else ""
                href = await name_el.first.get_attribute("href") if await name_el.count() > 0 else ""
                if not name:
                    continue

                # SKU from href  e.g. /groceries/en-IE/products/123456789
                sku = ""
                if href:
                    sku_match = re.search(r"/products/(\d+)", href)
                    sku = sku_match.group(1) if sku_match else ""
                if not sku:
                    sku = f"tesco-{i}-{hash(name) % 100000}"

                # Price
                price_el = tile.locator(
                    "span[data-auto='price-value'], "
                    "p[class*='price-per-sellable-unit'], "
                    "span.value"
                )
                price_text = ""
                if await price_el.count() > 0:
                    price_text = await price_el.first.inner_text()
                price_text = re.sub(r"[^\d.]", "", price_text)
                try:
                    price = Decimal(price_text) if price_text else Decimal("0")
                except InvalidOperation:
                    price = Decimal("0")

                if price == 0:
                    continue

                # Promo
                promo_label = None
                promo_el = tile.locator(
                    "span[data-auto='offer-text'], "
                    "div[class*='offer-text'], "
                    "span[class*='promo-content-small']"
                )
                if await promo_el.count() > 0:
                    promo_label = (await promo_el.first.inner_text()).strip() or None

                # Image
                img_el = tile.locator("img")
                image_url = None
                if await img_el.count() > 0:
                    image_url = await img_el.first.get_attribute("src")
                    if image_url and image_url.startswith("//"):
                        image_url = f"https:{image_url}"

                product_url = f"{BASE_URL}{href}" if href and not href.startswith("http") else href

                products.append(
                    RawProduct(
                        store_sku=sku,
                        name=name,
                        price=price,
                        promo_label=promo_label,
                        image_url=image_url,
                        product_url=product_url or None,
                    )
                )
            except Exception:
                logger.debug("[tesco] Failed to parse tile %d", i, exc_info=True)

        return products

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _scroll_page(page: Page, scrolls: int = 5) -> None:
        """Scroll down the page to trigger lazy-loading."""
        for _ in range(scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(0.5)


# ------------------------------------------------------------------
# Standalone entry point
# ------------------------------------------------------------------
async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    )
    scraper = TescoScraper()
    result = await scraper.run()
    print(f"\nDone: {result.status}")
    print(f"Products scraped: {len(result.products)}")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
