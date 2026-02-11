"""Scraper for Lidl Ireland (lidl.ie).

Lidl Ireland uses a Nuxt/Vue-based front-end.  Product data is embedded in
server-rendered HTML as JSON inside ``data-grid-data`` attributes on
``div.AProductGridbox__GridTilePlaceholder`` elements.

There are two flavours of category page:

* **Campaign / offer pages** (``/c/{slug}/a{id}``) -- these include product
  tiles in the initial SSR HTML and work with plain httpx.
* **Static range pages** (``/c/{slug}/s{id}``) -- these are fully
  client-rendered by JavaScript (Nuxt hydration) and return *no* product
  tiles with httpx.  They require Playwright to render the JS first.

The grocery landing page at ``/grocery-range`` contains links to both types.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Page

from src.scrapers.base import (
    BaseScraper,
    RawProduct,
    DEFAULT_HEADERS,
    random_delay,
    random_user_agent,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lidl.ie"

# Category URL format: /c/{slug}/{type}{id}
#   - 'a' prefix = campaign / offers page (SSR, works with httpx)
#   - 's' prefix = static range page (JS-rendered, needs Playwright)
# We keep a small seed list; remaining categories are discovered dynamically.
CATEGORY_PATHS = [
    "/grocery-range",  # Main grocery landing page (for discovery only)
]

# Weekly offer / campaign URLs (confirmed format -- httpx works)
WEEKLY_OFFERS_URLS = [
    f"{BASE_URL}/c/middle-aisle-highlights/a10027271",
    f"{BASE_URL}/c/super-savers/a10028883",
    f"{BASE_URL}/c/lidl-plus-offers/a10073407",
]


class LidlScraper(BaseScraper):
    store_slug = "lidl"

    # ------------------------------------------------------------------
    # Category URLs
    # ------------------------------------------------------------------
    async def get_category_urls(self) -> list[str]:
        """Return category URLs, preferring dynamic discovery.

        Falls back to the static seed list plus weekly offers if discovery
        finds nothing.
        """
        discovered = await self._discover_categories()
        if discovered:
            logger.info("[lidl] Discovered %d category URLs from /grocery-range", len(discovered))
            # Add weekly offer URLs that may not appear in discovery
            all_urls = list(set(discovered + WEEKLY_OFFERS_URLS))
            return all_urls

        logger.warning("[lidl] Category discovery found nothing; using static seed list")
        urls = [f"{BASE_URL}{path}" for path in CATEGORY_PATHS]
        urls.extend(WEEKLY_OFFERS_URLS)
        return urls

    async def _discover_categories(self) -> list[str]:
        """Discover category URLs from /grocery-range landing page.

        Uses httpx first (cheaper), falling back to Playwright if needed.
        """
        try:
            return await self._discover_categories_httpx()
        except Exception:
            logger.info("[lidl] httpx category discovery failed, trying Playwright")

        return await self._discover_categories_playwright()

    async def _discover_categories_httpx(self) -> list[str]:
        """Discover category links from /grocery-range using httpx."""
        headers = {**DEFAULT_HEADERS, "User-Agent": random_user_agent()}
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=30.0,
        ) as client:
            resp = await client.get(f"{BASE_URL}/grocery-range")
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        links: set[str] = set()
        for a_tag in soup.select("a[href*='/c/']"):
            href = a_tag.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = f"{BASE_URL}{href}"
            # Strip tracking query params for dedup
            href = href.split("?")[0]
            # Only keep Lidl Ireland links
            if href.startswith(BASE_URL):
                links.add(href)

        if not links:
            raise RuntimeError("No /c/ links found on /grocery-range")

        return list(links)

    async def _discover_categories_playwright(self) -> list[str]:
        """Discover category URLs from /grocery-range using Playwright."""
        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()
            logger.info("[lidl] Discovering categories from %s/grocery-range", BASE_URL)
            await page.goto(
                f"{BASE_URL}/grocery-range",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            await asyncio.sleep(3)
            await self._dismiss_overlays(page)

            links = await page.evaluate('''() => {
                return [...document.querySelectorAll('a[href*="/c/"]')]
                    .map(a => a.href.split("?")[0])
                    .filter((v, i, a) => a.indexOf(v) === i);
            }''')
            return list(set(links))

        except Exception:
            logger.warning("[lidl] Playwright category discovery failed", exc_info=True)
            return []
        finally:
            await context.close()
            await browser.close()
            await pw.stop()

    # ------------------------------------------------------------------
    # Scrape one category
    # ------------------------------------------------------------------
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        # Campaign / offer pages (/a{id}) have SSR product tiles -- try httpx
        if re.search(r"/c/.+/a\d+", category_url):
            return await self._scrape_with_httpx(category_url)

        # Static range pages (/s{id}) and other pages are JS-rendered
        # and require Playwright.
        return await self._scrape_with_playwright(category_url)

    # ------------------------------------------------------------------
    # httpx-based scraping (works for /a{id} campaign pages)
    # ------------------------------------------------------------------
    async def _scrape_with_httpx(self, category_url: str) -> list[RawProduct]:
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
                logger.info("[lidl] Fetching %s", current_url)
                response = await client.get(current_url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                batch = self._parse_html(soup)
                products.extend(batch)

                logger.info(
                    "[lidl] Page %d: parsed %d products (total %d)",
                    page_num,
                    len(batch),
                    len(products),
                )

                if not batch:
                    # No products found -- page may need JS rendering
                    logger.warning(
                        "[lidl] httpx returned 0 products for %s; "
                        "page may require Playwright",
                        current_url,
                    )

                # Pagination -- Lidl campaign pages do not typically paginate,
                # but we keep this in case they start.
                next_link = soup.select_one(
                    "a[rel='next'], "
                    "a.pagination__next, "
                    "a[aria-label='Next'], "
                    "li.next a"
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

    # ------------------------------------------------------------------
    # HTML parsing -- extract from data-grid-data JSON attributes
    # ------------------------------------------------------------------
    def _parse_html(self, soup: BeautifulSoup) -> list[RawProduct]:
        """Parse product tiles from a Lidl page.

        Lidl embeds product data as a JSON blob in the ``data-grid-data``
        attribute of ``div.AProductGridbox__GridTilePlaceholder`` elements.
        The inner HTML of these tiles is only skeleton/loading placeholders;
        all meaningful data lives in the attribute.
        """
        products: list[RawProduct] = []

        # Primary selector: the confirmed SSR tile class.
        # Also match any element with a data-grid-data attribute as fallback.
        tiles = soup.select(
            "div.AProductGridbox__GridTilePlaceholder, "
            "[data-grid-data]"
        )

        for tile in tiles:
            try:
                product = self._parse_tile(tile)
                if product is not None:
                    products.append(product)
            except Exception:
                logger.debug("[lidl] Failed to parse product tile", exc_info=True)

        return products

    def _parse_tile(self, tile) -> RawProduct | None:
        """Extract a RawProduct from a single tile element.

        Data is primarily extracted from the ``data-grid-data`` JSON
        attribute.  If that attribute is missing, we fall back to
        HTML attributes (``fulltitle``, ``productid``, ``canonicalurl``,
        ``image``) which Lidl also renders on the element.
        """
        grid_data_raw = tile.get("data-grid-data", "")
        grid_data: dict = {}
        if grid_data_raw:
            try:
                grid_data = json.loads(grid_data_raw)
            except (json.JSONDecodeError, TypeError):
                logger.debug("[lidl] Invalid JSON in data-grid-data")

        # --- Name ---
        name = (
            grid_data.get("fullTitle")
            or grid_data.get("title")
            or tile.get("fulltitle", "")
        )
        if not name:
            return None

        # --- Product ID / SKU ---
        product_id = str(
            grid_data.get("productId")
            or grid_data.get("itemId")
            or grid_data.get("erpNumber")
            or tile.get("productid", "")
            or tile.get("itemid", "")
        )
        if not product_id:
            product_id = f"lidl-{hash(name) % 1000000}"

        # --- Product URL ---
        canonical = (
            grid_data.get("canonicalUrl")
            or grid_data.get("canonicalPath")
            or tile.get("canonicalurl", "")
            or tile.get("canonicalpath", "")
        )
        product_url = None
        if canonical:
            product_url = canonical if canonical.startswith("http") else f"{BASE_URL}{canonical}"

        # --- Price ---
        # Price can come from two places:
        #   1. price.price (top-level, for regular / non-Lidl-Plus items)
        #   2. lidlPlus[0].price.price (for Lidl Plus offer items)
        price: Decimal | None = None
        promo_price: Decimal | None = None
        promo_label: str | None = None

        price_obj = grid_data.get("price", {})
        lidl_plus_list = grid_data.get("lidlPlus", [])

        top_level_price = price_obj.get("price")
        if top_level_price is not None:
            try:
                price = Decimal(str(top_level_price))
            except (InvalidOperation, ValueError):
                pass

        # Lidl Plus price data (often present for offer / campaign pages)
        if lidl_plus_list:
            lp_entry = lidl_plus_list[0] if isinstance(lidl_plus_list, list) else {}
            lp_price_obj = lp_entry.get("price", {})
            lp_price_val = lp_price_obj.get("price")

            lp_discount = lp_price_obj.get("discount", {})
            deleted_price = lp_discount.get("deletedPrice")
            old_price = lp_price_obj.get("oldPrice")
            highlight_text = lp_entry.get("highlightText", "")
            lidl_plus_text = lp_entry.get("lidlPlusText", "")

            if lp_price_val is not None:
                try:
                    lp_price = Decimal(str(lp_price_val))
                except (InvalidOperation, ValueError):
                    lp_price = None

                if lp_price is not None:
                    # Determine original / struck-through price
                    original = None
                    for candidate in (deleted_price, old_price):
                        if candidate is not None:
                            try:
                                original = Decimal(str(candidate))
                                break
                            except (InvalidOperation, ValueError):
                                pass

                    if original and original > lp_price:
                        # There IS a discount: original is the shelf price,
                        # lp_price is the promo price.
                        price = original
                        promo_price = lp_price
                        # Build a promo label from highlight / lidl plus text
                        parts = [p for p in (highlight_text, lidl_plus_text) if p]
                        promo_label = " - ".join(parts) if parts else "Lidl Plus Offer"
                    elif price is None:
                        # No top-level price, use Lidl Plus price as the base
                        price = lp_price
                        if highlight_text or lidl_plus_text:
                            parts = [p for p in (highlight_text, lidl_plus_text) if p]
                            promo_label = " - ".join(parts)

        if price is None or price == 0:
            return None

        # --- Image ---
        image_url = grid_data.get("image") or tile.get("image")
        if not image_url:
            image_list = grid_data.get("imageList") or grid_data.get("imageList_V1")
            if image_list and isinstance(image_list, list):
                first = image_list[0]
                if isinstance(first, dict):
                    image_url = first.get("image")
                elif isinstance(first, str):
                    image_url = first
        if image_url:
            if image_url.startswith("//"):
                image_url = f"https:{image_url}"
            elif image_url.startswith("/"):
                image_url = f"{BASE_URL}{image_url}"

        # --- Brand ---
        brand = None
        brand_obj = grid_data.get("brand", {})
        if isinstance(brand_obj, dict) and brand_obj.get("showBrand"):
            brand = brand_obj.get("name")

        # --- Category ---
        category = grid_data.get("category") or tile.get("category")

        # --- EAN ---
        ean = None
        ians = grid_data.get("ians")
        if ians and isinstance(ians, list) and ians[0]:
            ean = str(ians[0])

        # --- Unit / packaging from lidlPlus or price data ---
        unit_size: Decimal | None = None
        unit: str | None = None
        packaging_text = None

        # Try lidlPlus packaging first
        if lidl_plus_list:
            lp_entry = lidl_plus_list[0] if isinstance(lidl_plus_list, list) else {}
            packaging_text = (
                lp_entry.get("price", {}).get("packaging", {}).get("text")
            )
        # Fall back to top-level price packaging
        if not packaging_text:
            packaging_text = price_obj.get("packaging", {}).get("text")

        if packaging_text:
            size_match = re.search(
                r"(\d+(?:[.,]\d+)?)\s*(ml|l|g|kg|cl|pk|pack|cm)\b",
                packaging_text,
                re.IGNORECASE,
            )
            if size_match:
                try:
                    unit_size = Decimal(size_match.group(1).replace(",", "."))
                    unit = size_match.group(2).lower()
                except (InvalidOperation, ValueError):
                    pass

        # Fall back: extract unit/size from product name
        if unit_size is None:
            size_match = re.search(
                r"(\d+(?:[.,]\d+)?)\s*(ml|l|g|kg|cl|pk|pack)\b",
                name,
                re.IGNORECASE,
            )
            if size_match:
                try:
                    unit_size = Decimal(size_match.group(1).replace(",", "."))
                    unit = size_match.group(2).lower()
                except (InvalidOperation, ValueError):
                    pass

        # --- Unit price (base price) ---
        unit_price: Decimal | None = None
        base_price_obj = None
        if lidl_plus_list:
            lp_entry = lidl_plus_list[0] if isinstance(lidl_plus_list, list) else {}
            base_price_obj = lp_entry.get("price", {}).get("basePrice")
        if not base_price_obj:
            base_price_obj = price_obj.get("basePrice")
        if isinstance(base_price_obj, dict):
            bp_val = base_price_obj.get("price")
            if bp_val is not None:
                try:
                    unit_price = Decimal(str(bp_val))
                except (InvalidOperation, ValueError):
                    pass

        # --- In stock ---
        stock_info = grid_data.get("stockAvailability", {})
        in_stock = True
        if isinstance(stock_info, dict):
            indicator = stock_info.get("availabilityIndicator")
            # 0 = available, higher values indicate limited/out of stock
            if indicator is not None and indicator > 2:
                in_stock = False

        # --- Promo label from ribbons if not already set ---
        if not promo_label:
            ribbons = grid_data.get("ribbons", [])
            if ribbons and isinstance(ribbons, list):
                ribbon_texts = [r.get("text", "") for r in ribbons if isinstance(r, dict)]
                ribbon_str = " | ".join(t for t in ribbon_texts if t)
                if ribbon_str:
                    promo_label = ribbon_str

        return RawProduct(
            store_sku=product_id,
            name=name,
            price=price,
            promo_price=promo_price,
            promo_label=promo_label,
            unit_price=unit_price,
            unit=unit,
            unit_size=unit_size,
            brand=brand,
            ean=ean,
            category=category,
            image_url=image_url,
            product_url=product_url,
            in_stock=in_stock,
        )

    # ------------------------------------------------------------------
    # Playwright-based scraping (for /s{id} range pages and fallback)
    # ------------------------------------------------------------------
    async def _scrape_with_playwright(self, url: str) -> list[RawProduct]:
        """Scrape a page using Playwright.

        Required for ``/c/{slug}/s{id}`` range pages and the ``/grocery-range``
        landing page, which are fully JS-rendered (Nuxt hydration).
        After Playwright renders the page, we extract the same
        ``data-grid-data`` JSON that the httpx path uses.
        """
        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()
            logger.info("[lidl] Playwright loading %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)

            await self._dismiss_overlays(page)
            await self._scroll_page(page, scrolls=8)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            products = self._parse_html(soup)

            # If _parse_html found nothing, try extracting from Playwright
            # locators directly (the data-grid-data may also be available
            # on the live DOM even if not in the serialised HTML).
            if not products:
                products = await self._extract_from_playwright(page)

            return products

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

    async def _extract_from_playwright(self, page: Page) -> list[RawProduct]:
        """Extract products directly from the Playwright page DOM.

        Evaluates JS to pull data-grid-data JSON from all tile elements.
        """
        products: list[RawProduct] = []

        raw_items = await page.evaluate('''() => {
            const tiles = document.querySelectorAll(
                'div.AProductGridbox__GridTilePlaceholder, [data-grid-data]'
            );
            return [...tiles].map(el => {
                try {
                    const raw = el.getAttribute('data-grid-data');
                    return raw ? JSON.parse(raw) : null;
                } catch { return null; }
            }).filter(Boolean);
        }''')

        for gd in raw_items:
            try:
                product = self._parse_grid_data_dict(gd)
                if product is not None:
                    products.append(product)
            except Exception:
                logger.debug("[lidl] Failed to parse Playwright-extracted tile", exc_info=True)

        logger.info("[lidl] Playwright JS extraction found %d products", len(products))
        return products

    def _parse_grid_data_dict(self, grid_data: dict) -> RawProduct | None:
        """Parse a RawProduct from a pre-parsed data-grid-data dict.

        Shares logic with ``_parse_tile`` but takes a plain dict instead
        of a BeautifulSoup element.
        """
        # Build a minimal mock tag with the grid_data as attribute
        # so we can reuse _parse_tile.  This is a lightweight approach.
        from bs4 import Tag

        tag = Tag(name="div")
        tag["data-grid-data"] = json.dumps(grid_data)
        return self._parse_tile(tag)

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
            "button[class*='cookie-alert--accept']",
            "button[id*='onetrust-accept']",
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
    scraper = LidlScraper()
    result = await scraper.run()
    print(f"\nDone: {result.status}")
    print(f"Products scraped: {len(result.products)}")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
