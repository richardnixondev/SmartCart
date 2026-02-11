"""Scraper for Aldi Ireland (aldi.ie).

Aldi has a simpler, more static site compared to other supermarkets.  We
prefer httpx for the main product catalogue and fall back to Playwright for
special-offers pages that require JavaScript rendering.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Page, Response

from src.scrapers.base import (
    BaseScraper,
    RawProduct,
    DEFAULT_HEADERS,
    random_delay,
    random_user_agent,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.aldi.ie"

# Aldi Ireland product category paths
CATEGORY_PATHS = [
    "/products/fresh-meat/",
    "/products/fresh-food/",
    "/products/bakery/",
    "/products/chilled-food/",
    "/products/frozen/",
    "/products/fruit-and-vegetables/",
    "/products/drinks/",
    "/products/food-cupboard/",
    "/products/snacks-and-sweets/",
    "/products/baby-and-toddler/",
    "/products/health-and-beauty/",
    "/products/household/",
    "/products/pet-care/",
]

# Special offers page (rendered with JS, needs Playwright)
SPECIAL_OFFERS_URL = f"{BASE_URL}/specials"


class AldiScraper(BaseScraper):
    store_slug = "aldi"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Category URLs
    # ------------------------------------------------------------------
    async def get_category_urls(self) -> list[str]:
        urls = [f"{BASE_URL}{path}" for path in CATEGORY_PATHS]
        # Include special offers (will be handled differently)
        urls.append(SPECIAL_OFFERS_URL)
        return urls

    # ------------------------------------------------------------------
    # Scrape one category
    # ------------------------------------------------------------------
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        # Special offers page needs Playwright
        if "/specials" in category_url:
            return await self._scrape_special_offers(category_url)

        # Standard category pages — try httpx first
        try:
            return await self._scrape_with_httpx(category_url)
        except Exception as exc:
            logger.warning(
                "[aldi] httpx scrape failed for %s (%s), falling back to Playwright",
                category_url,
                exc,
            )
            return await self._scrape_with_playwright(category_url)

    # ------------------------------------------------------------------
    # httpx-based scraping (preferred for standard pages)
    # ------------------------------------------------------------------
    async def _scrape_with_httpx(self, category_url: str) -> list[RawProduct]:
        """Fetch the category page with httpx and parse with BeautifulSoup."""
        products: list[RawProduct] = []

        headers = {**DEFAULT_HEADERS, "User-Agent": random_user_agent()}

        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            page_num = 1
            current_url = category_url

            while current_url:
                logger.info("[aldi] Fetching %s", current_url)
                response = await client.get(current_url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                batch = self._parse_html(soup, category_url)
                products.extend(batch)

                logger.info(
                    "[aldi] Page %d: parsed %d products (total %d)",
                    page_num,
                    len(batch),
                    len(products),
                )

                # Check for next page
                next_link = soup.select_one(
                    "a[rel='next'], "
                    "a.pagination__next, "
                    "li.next a, "
                    "a[aria-label='Next page']"
                )
                if next_link and next_link.get("href"):
                    next_href = next_link["href"]
                    if not next_href.startswith("http"):
                        next_href = f"{BASE_URL}{next_href}"
                    current_url = next_href
                    page_num += 1
                    await random_delay(1.0, 2.5)
                else:
                    current_url = None

        return products

    def _parse_html(self, soup: BeautifulSoup, category_url: str) -> list[RawProduct]:
        """Parse product data from a BeautifulSoup-parsed Aldi category page."""
        products: list[RawProduct] = []

        # Aldi uses product tiles / boxes
        tiles = soup.select(
            "div.product-tile, "
            "div[class*='ProductTile'], "
            "article[class*='product'], "
            "div[data-qa='product-tile'], "
            "a[class*='ProductTile']"
        )

        if not tiles:
            # Fallback: try broader selectors
            tiles = soup.select(
                "div[class*='mod-article-tile'], "
                "div.box--product, "
                "div[class*='product-card']"
            )

        for tile in tiles:
            try:
                # --- Name + link ---
                name_el = (
                    tile.select_one("a[class*='Title'], h4 a, h3 a, p[class*='title']")
                    or tile.select_one("a")
                )
                if not name_el:
                    continue

                name = name_el.get_text(strip=True)
                href = name_el.get("href", "")
                if not name:
                    continue

                # --- SKU ---
                sku = tile.get("data-product-id", "") or tile.get("data-sku", "")
                if not sku and href:
                    sku_match = re.search(r"/p/(\d+)", href) or re.search(r"/(\w+-\d+)", href)
                    sku = sku_match.group(1) if sku_match else ""
                if not sku:
                    sku = f"aldi-{hash(name) % 1000000}"

                # --- Price ---
                price_el = tile.select_one(
                    "span[class*='price'], "
                    "span[class*='Price'], "
                    "div[class*='price'], "
                    "p[class*='price']"
                )
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = self._parse_price(price_text)
                if price is None or price == 0:
                    continue

                # --- Promo ---
                promo_label = None
                promo_el = tile.select_one(
                    "span[class*='offer'], "
                    "span[class*='badge'], "
                    "div[class*='badge'], "
                    "span[class*='promo']"
                )
                if promo_el:
                    promo_label = promo_el.get_text(strip=True) or None

                # --- Image ---
                image_url = None
                img_el = tile.select_one("img")
                if img_el:
                    image_url = img_el.get("src") or img_el.get("data-src")
                    if image_url and image_url.startswith("//"):
                        image_url = f"https:{image_url}"
                    elif image_url and image_url.startswith("/"):
                        image_url = f"{BASE_URL}{image_url}"

                # --- Unit size from name ---
                unit_size = None
                unit = None
                size_match = re.search(
                    r"(\d+(?:\.\d+)?)\s*(ml|l|g|kg|cl|pk|pack)\b", name, re.IGNORECASE
                )
                if size_match:
                    try:
                        unit_size = Decimal(size_match.group(1))
                        unit = size_match.group(2).lower()
                    except (InvalidOperation, ValueError):
                        pass

                product_url = href
                if product_url and not product_url.startswith("http"):
                    product_url = f"{BASE_URL}{product_url}"

                # --- Brand ---
                brand = None
                brand_el = tile.select_one("span[class*='brand'], span[class*='Brand']")
                if brand_el:
                    brand = brand_el.get_text(strip=True)

                products.append(
                    RawProduct(
                        store_sku=sku,
                        name=name,
                        price=price,
                        promo_label=promo_label,
                        unit_size=unit_size,
                        unit=unit,
                        brand=brand,
                        image_url=image_url,
                        product_url=product_url or None,
                    )
                )

            except Exception:
                logger.debug("[aldi] Failed to parse tile", exc_info=True)

        return products

    # ------------------------------------------------------------------
    # SAP Commerce OCC API interception
    # ------------------------------------------------------------------
    async def _intercept_api(self, page: Page, url: str) -> list[dict]:
        """Load a page while intercepting SAP Commerce OCC API responses."""
        api_products: list[dict] = []

        async def handle_response(response: Response) -> None:
            resp_url = response.url
            if "/occ/" in resp_url or "/rest/" in resp_url:
                try:
                    content_type = response.headers.get("content-type", "")
                    if "application/json" not in content_type:
                        return
                    data = await response.json()
                    if isinstance(data, dict):
                        products = data.get("products", [])
                        if isinstance(products, list) and products:
                            api_products.extend(products)
                except Exception:
                    pass

        page.on("response", handle_response)
        await page.goto(url, wait_until="networkidle", timeout=60_000)
        return api_products

    def _parse_occ_product(self, item: dict) -> RawProduct | None:
        """Parse a product from SAP Commerce OCC API response."""
        code = item.get("code", "")
        name = item.get("name", "")
        if not code or not name:
            return None

        price_data = item.get("price", {})
        price_val = price_data.get("value")
        if price_val is None:
            return None

        try:
            price = Decimal(str(price_val))
        except (InvalidOperation, TypeError, ValueError):
            return None

        if price == 0:
            return None

        # Promo / was-price
        promo_price = None
        promo_label = None
        was_price_data = item.get("wasPrice", {})
        if was_price_data and was_price_data.get("value") is not None:
            try:
                promo_price = price  # current price is the promo
                price = Decimal(str(was_price_data["value"]))
                promo_label = item.get("promotionText") or "Special Offer"
            except (InvalidOperation, TypeError, ValueError):
                promo_price = None
                promo_label = None

        # Unit price
        unit_price = None
        unit = None
        unit_price_data = item.get("basePrice") or item.get("unitPrice")
        if isinstance(unit_price_data, dict):
            try:
                unit_price = Decimal(str(unit_price_data.get("value", "")))
            except (InvalidOperation, TypeError, ValueError):
                pass
            unit = unit_price_data.get("unit", unit_price_data.get("currencyIso"))

        # Unit size from name
        unit_size = None
        size_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(ml|l|g|kg|cl|pk|pack)\b", name, re.IGNORECASE
        )
        if size_match:
            try:
                unit_size = Decimal(size_match.group(1))
                unit = unit or size_match.group(2).lower()
            except (InvalidOperation, ValueError):
                pass

        # Image
        image_url = None
        images = item.get("images", [])
        if isinstance(images, list) and images:
            for img in images:
                if isinstance(img, dict) and img.get("url"):
                    image_url = img["url"]
                    if image_url.startswith("//"):
                        image_url = f"https:{image_url}"
                    elif image_url.startswith("/"):
                        image_url = f"{BASE_URL}{image_url}"
                    break

        # Product URL
        product_url = item.get("url", "")
        if product_url and not product_url.startswith("http"):
            product_url = f"{BASE_URL}{product_url}"

        # Brand
        brand = None
        brand_data = item.get("brand")
        if isinstance(brand_data, dict):
            brand = brand_data.get("name")
        elif isinstance(brand_data, str):
            brand = brand_data

        return RawProduct(
            store_sku=str(code),
            name=name.strip(),
            price=price,
            promo_price=promo_price,
            promo_label=promo_label,
            unit_price=unit_price,
            unit=unit,
            unit_size=unit_size,
            brand=brand,
            image_url=image_url or None,
            product_url=product_url or None,
        )

    # ------------------------------------------------------------------
    # Playwright-based scraping (fallback for standard pages)
    # ------------------------------------------------------------------
    async def _scrape_with_playwright(self, category_url: str) -> list[RawProduct]:
        """Fall back to Playwright when httpx cannot get the data."""
        products: list[RawProduct] = []

        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()
            logger.info("[aldi] Playwright loading %s", category_url)

            # Try to intercept OCC API responses while loading the page
            api_products = await self._intercept_api(page, category_url)
            await asyncio.sleep(3)

            await self._dismiss_overlays(page)
            await self._scroll_page(page)

            # Parse products from intercepted API data first
            if api_products:
                logger.info("[aldi] Intercepted %d OCC API products", len(api_products))
                for item in api_products:
                    try:
                        product = self._parse_occ_product(item)
                        if product:
                            products.append(product)
                    except Exception:
                        logger.debug("[aldi] Failed to parse OCC product", exc_info=True)

            # Fall back to DOM scraping if API interception yielded nothing
            if not products:
                logger.info("[aldi] Falling back to DOM scraping for %s", category_url)
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                products = self._parse_html(soup, category_url)

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

        return products

    # ------------------------------------------------------------------
    # Special offers scraping (always Playwright)
    # ------------------------------------------------------------------
    async def _scrape_special_offers(self, url: str) -> list[RawProduct]:
        """Scrape the Aldi specials page (JS-rendered)."""
        products: list[RawProduct] = []

        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()
            logger.info("[aldi] Loading special offers %s", url)

            # Try to intercept OCC API responses while loading the page
            api_products = await self._intercept_api(page, url)
            await asyncio.sleep(3)

            await self._dismiss_overlays(page)
            await self._scroll_page(page, scrolls=8)

            # Parse products from intercepted API data first
            if api_products:
                logger.info("[aldi] Intercepted %d OCC API special offer products", len(api_products))
                for item in api_products:
                    try:
                        product = self._parse_occ_product(item)
                        if product:
                            # Override promo label for special offers
                            product.promo_label = product.promo_label or "Special Offer"
                            products.append(product)
                    except Exception:
                        logger.debug("[aldi] Failed to parse OCC special offer product", exc_info=True)

            # Fall back to DOM scraping if API interception yielded nothing
            if not products:
                logger.info("[aldi] Falling back to DOM scraping for specials")
                # Special offer tiles
                tiles = page.locator(
                    "div[class*='SpecialBuy'], "
                    "div[class*='product-tile'], "
                    "div[data-qa='special-buy-tile'], "
                    "article[class*='product']"
                )
                count = await tiles.count()
                logger.info("[aldi] Found %d special offer tiles", count)

                for i in range(count):
                    try:
                        tile = tiles.nth(i)

                        name_el = tile.locator("h4, h3, a[class*='Title'], p[class*='title']")
                        name = ""
                        if await name_el.count() > 0:
                            name = (await name_el.first.inner_text()).strip()
                        if not name:
                            continue

                        price_el = tile.locator("span[class*='price'], span[class*='Price']")
                        price_text = ""
                        if await price_el.count() > 0:
                            price_text = await price_el.first.inner_text()
                        price = self._parse_price(price_text)
                        if price is None or price == 0:
                            continue

                        sku = f"aldi-offer-{hash(name) % 1000000}"

                        # Image
                        image_url = None
                        img_el = tile.locator("img")
                        if await img_el.count() > 0:
                            image_url = await img_el.first.get_attribute("src")
                            if image_url and not image_url.startswith("http"):
                                image_url = f"{BASE_URL}{image_url}"

                        products.append(
                            RawProduct(
                                store_sku=sku,
                                name=name,
                                price=price,
                                promo_label="Special Offer",
                                image_url=image_url,
                            )
                        )
                    except Exception:
                        logger.debug("[aldi] Failed to parse special offer tile %d", i, exc_info=True)

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

        return products

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_price(text: str) -> Decimal | None:
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
        for selector in [
            "button:has-text('Accept All')",
            "button:has-text('Accept Cookies')",
            "button:has-text('Accept')",
            "button[id*='onetrust-accept']",
            "button[class*='cookie-accept']",
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
    async def _scroll_page(page: Page, scrolls: int = 5) -> None:
        for _ in range(scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(0.6)


# ------------------------------------------------------------------
# Standalone entry point
# ------------------------------------------------------------------
async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    )

    dry_run = "--dry-run" in sys.argv

    if dry_run:
        # Dry-run mode: scrape categories and print products without hitting the DB
        scraper = AldiScraper()
        category_urls = await scraper.get_category_urls()
        all_products: list[RawProduct] = []
        for url in category_urls:
            try:
                products = await scraper.scrape_category(url)
                all_products.extend(products)
                print(f"[dry-run] {url} -> {len(products)} products")
            except Exception as exc:
                print(f"[dry-run] {url} -> ERROR: {exc}")
            await random_delay(1.0, 3.0)

        print(f"\n[dry-run] Total products scraped: {len(all_products)}")
        for p in all_products[:20]:
            print(f"  {p.store_sku:>12s}  {str(p.price):>8s}  {p.name}")
        if len(all_products) > 20:
            print(f"  ... and {len(all_products) - 20} more")
    else:
        scraper = AldiScraper()
        result = await scraper.run()
        print(f"\nDone: {result.status}")
        print(f"Products scraped: {len(result.products)}")
        if result.errors:
            print(f"Errors ({len(result.errors)}):")
            for err in result.errors:
                print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
