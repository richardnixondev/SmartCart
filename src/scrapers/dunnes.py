"""Scraper for Dunnes Stores Grocery (dunnesstoresgrocery.com).

Dunnes has a JavaScript-heavy storefront with anti-bot protections.
We use Playwright exclusively, with user-agent rotation, random delays,
and careful DOM extraction.

IMPORTANT: The grocery site is at www.dunnesstoresgrocery.com (NOT dunnesstores.com).
Category URLs use the format /categories/{slug}-id-{numeric_id}.
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

BASE_URL = "https://www.dunnesstoresgrocery.com"

# Confirmed category paths on dunnesstoresgrocery.com
# Format: /categories/{slug}-id-{id}
# We keep a small seed list of confirmed categories; the rest are
# discovered dynamically from the site navigation.
CATEGORY_PATHS = [
    "/categories/fresh-meat-poultry-id-47181",
    "/categories/bakery-id-47171",
]


class DunnesScraper(BaseScraper):
    store_slug = "dunnes"

    # ------------------------------------------------------------------
    # Category URLs
    # ------------------------------------------------------------------
    async def get_category_urls(self) -> list[str]:
        """Return category URLs, preferring dynamic discovery.

        Falls back to the static seed list if discovery finds nothing.
        """
        discovered = await self._discover_categories()
        if discovered:
            logger.info("[dunnes] Discovered %d category URLs from navigation", len(discovered))
            return discovered

        logger.warning("[dunnes] Category discovery found nothing; using static seed list")
        return [f"{BASE_URL}{path}" for path in CATEGORY_PATHS]

    async def _discover_categories(self) -> list[str]:
        """Discover category URLs from the site navigation."""
        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()
            logger.info("[dunnes] Discovering categories from %s", BASE_URL)
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)
            await self._dismiss_overlays(page)

            links = await page.evaluate('''() => {
                return [...document.querySelectorAll('a[href*="/categories/"]')]
                    .map(a => a.href)
                    .filter(href => {
                        // Only keep top-level categories: /categories/{slug}-id-{id}
                        // Skip deep subcategories: /categories/{parent}/{child}-id-{id}
                        try {
                            const path = new URL(href).pathname;
                            const parts = path.split('/').filter(Boolean);
                            return parts.length === 2
                                && parts[0] === 'categories'
                                && parts[1].includes('-id-');
                        } catch(e) { return false; }
                    });
            }''')
            unique = list(set(links))

            # If homepage didn't yield enough, also try interacting with nav menus
            if len(unique) < 5:
                logger.debug("[dunnes] Few links found, attempting to expand nav menus")
                nav_triggers = page.locator(
                    "button[class*='nav'], "
                    "a[class*='nav'], "
                    "button[aria-expanded='false'], "
                    "li[class*='menu'] > a"
                )
                trigger_count = await nav_triggers.count()
                for idx in range(min(trigger_count, 10)):
                    try:
                        trigger = nav_triggers.nth(idx)
                        if await trigger.is_visible():
                            await trigger.click()
                            await asyncio.sleep(0.5)
                    except Exception:
                        pass

                more_links = await page.evaluate('''() => {
                    return [...document.querySelectorAll('a[href*="/categories/"]')]
                        .map(a => a.href)
                        .filter(href => {
                            try {
                                const path = new URL(href).pathname;
                                const parts = path.split('/').filter(Boolean);
                                return parts.length === 2
                                    && parts[0] === 'categories'
                                    && parts[1].includes('-id-');
                            } catch(e) { return false; }
                        });
                }''')
                unique = list(set(unique + more_links))

            return unique

        except Exception:
            logger.warning("[dunnes] Category discovery failed", exc_info=True)
            return []
        finally:
            await context.close()
            await browser.close()
            await pw.stop()

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
        """Extract product data from the currently loaded DOM.

        Uses a two-pass approach:
        1. Try extracting structured data from the page's JS state (dataLayer,
           __NEXT_DATA__, or similar embedded JSON).
        2. Fall back to broad CSS-selector scraping of product tiles.
        """
        # --- Pass 1: try to pull data from JS state ---
        js_products = await self._extract_from_js_state(page, category_url)
        if js_products:
            logger.info("[dunnes] Extracted %d products from JS state", len(js_products))
            return js_products

        # --- Pass 2: DOM selector scraping ---
        products: list[RawProduct] = []

        # dunnesstoresgrocery.com may use different class names;
        # cast a wide net with multiple selector patterns
        tiles = page.locator(
            "div[data-ref='productListItem'], "
            "div[class*='ProductCard'], "
            "li[class*='ProductCard'], "
            "article[class*='product-card'], "
            "div[class*='product-list-item'], "
            "div[class*='product-tile'], "
            "div[class*='productTile'], "
            "a[class*='product-card'], "
            "div[data-product-id]"
        )
        count = await tiles.count()

        if count == 0:
            # Broader fallback: look for any repeated card-like structure
            logger.debug("[dunnes] Primary selectors found 0 tiles; trying broader selectors")
            tiles = page.locator(
                "[class*='product'] a[href*='/'], "
                "[class*='card'][class*='product'], "
                "[class*='item'][data-product-id]"
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
                    "h3 a, h2 a, h3, h2, "
                    "a[class*='Title'], "
                    "span[class*='title'], "
                    "p[class*='title']"
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
                data_ref = await tile.get_attribute("data-ref") or ""
                sku = data_id or data_sku or data_ref
                if not sku and href:
                    sku_match = (
                        re.search(r"/p/(\d+)", href)
                        or re.search(r"-id-(\d+)", href)
                        or re.search(r"/(\d+)(?:\?|$)", href)
                    )
                    sku = sku_match.group(1) if sku_match else ""
                if not sku:
                    sku = f"dunnes-{hash(name) % 1000000}"

                # --- Price ---
                price_el = tile.locator(
                    "span[class*='Price__current'], "
                    "span[class*='ProductCard__price'], "
                    "span[data-ref='productCardPrice'], "
                    "span[class*='price-value'], "
                    "span[class*='price'], "
                    "span.price, "
                    "div[class*='price']"
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
                    "span[data-ref='productCardPromo'], "
                    "del, s, "
                    "span[class*='was']"
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
                    elif image_url and image_url.startswith("/"):
                        image_url = f"{BASE_URL}{image_url}"

                # --- Unit price ---
                unit_price = None
                unit = None
                unit_el = tile.locator(
                    "span[class*='UnitPrice'], "
                    "span[class*='unit-price'], "
                    "span[data-ref='productCardUnitPrice'], "
                    "span[class*='per-unit']"
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

    async def _extract_from_js_state(
        self, page: Page, category_url: str
    ) -> list[RawProduct]:
        """Try to extract product data from embedded JS state on the page.

        Many modern grocery sites embed product data in __NEXT_DATA__,
        dataLayer, or similar global JS objects. This is more reliable
        than scraping CSS selectors when it works.
        """
        try:
            js_data = await page.evaluate('''() => {
                // Attempt 1: __NEXT_DATA__ (Next.js)
                if (window.__NEXT_DATA__) {
                    try {
                        const props = window.__NEXT_DATA__.props;
                        if (props && props.pageProps && props.pageProps.products) {
                            return { source: 'next', items: props.pageProps.products };
                        }
                        if (props && props.pageProps && props.pageProps.category
                            && props.pageProps.category.products) {
                            return { source: 'next', items: props.pageProps.category.products };
                        }
                        // Recurse one level into pageProps looking for product arrays
                        if (props && props.pageProps) {
                            for (const [key, val] of Object.entries(props.pageProps)) {
                                if (Array.isArray(val) && val.length > 0 && val[0].name) {
                                    return { source: 'next', items: val };
                                }
                            }
                        }
                    } catch (e) {}
                }
                // Attempt 2: dataLayer product impressions
                if (window.dataLayer) {
                    for (const entry of window.dataLayer) {
                        if (entry.ecommerce && entry.ecommerce.impressions) {
                            return { source: 'dl', items: entry.ecommerce.impressions };
                        }
                    }
                }
                // Attempt 3: look for JSON-LD structured data
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const s of scripts) {
                    try {
                        const d = JSON.parse(s.textContent);
                        if (d['@type'] === 'ItemList' && d.itemListElement) {
                            return { source: 'ld', items: d.itemListElement };
                        }
                    } catch (e) {}
                }
                return null;
            }''')

            if not js_data or not js_data.get("items"):
                return []

            products: list[RawProduct] = []
            source = js_data.get("source", "unknown")
            logger.debug("[dunnes] Found JS product data via %s", source)

            for item in js_data["items"]:
                try:
                    name = str(item.get("name") or item.get("title") or "").strip()
                    if not name:
                        continue

                    price_raw = item.get("price") or item.get("current_price") or 0
                    price = self._parse_price(str(price_raw))
                    if price is None or price == 0:
                        continue

                    sku = str(
                        item.get("id")
                        or item.get("sku")
                        or item.get("product_id")
                        or f"dunnes-{hash(name) % 1000000}"
                    )

                    brand = item.get("brand") or None
                    image_url = item.get("image") or item.get("image_url") or None
                    product_url = item.get("url") or item.get("link") or None
                    if product_url and not product_url.startswith("http"):
                        product_url = f"{BASE_URL}{product_url}"

                    # Promo handling
                    promo_price = None
                    promo_label = None
                    original_price = item.get("original_price") or item.get("was_price")
                    if original_price:
                        op = self._parse_price(str(original_price))
                        if op and op > price:
                            promo_price = price
                            price = op

                    products.append(
                        RawProduct(
                            store_sku=sku,
                            name=name,
                            price=price,
                            promo_price=promo_price,
                            promo_label=promo_label,
                            brand=brand,
                            image_url=image_url,
                            product_url=product_url,
                        )
                    )
                except Exception:
                    logger.debug("[dunnes] Failed to parse JS product item", exc_info=True)

            return products

        except Exception:
            logger.debug("[dunnes] JS state extraction failed", exc_info=True)
            return []

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
