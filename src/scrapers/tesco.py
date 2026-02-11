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
import sys
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
        """Load a Tesco category page and extract products via JS evaluation.

        Tesco uses Akamai WAF + obfuscated CSS module class names.
        The most reliable approach is to use JavaScript evaluation to extract
        product data from the rendered DOM rather than relying on brittle
        CSS selectors.
        """
        # Tesco uses Akamai WAF — resource blocking triggers bot detection
        pw, browser, context = await self._get_browser_context(
            headless=True, block_resources=False
        )
        try:
            page = await context.new_page()

            logger.info("[tesco] Loading %s", category_url)
            await page.goto(category_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(5)

            # Handle cookie consent banner if present
            for sel in ["#onetrust-accept-btn-handler", "button:has-text('Accept All')"]:
                try:
                    btn = page.locator(sel)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click()
                        await asyncio.sleep(1)
                        break
                except Exception:
                    pass

            await asyncio.sleep(2)

            # Scroll to load lazy content
            await self._scroll_page(page, scrolls=6)

            # Extract products using JavaScript evaluation (bypasses CSS obfuscation)
            products = await self._extract_products_js(page)
            logger.info("[tesco] Extracted %d products from %s", len(products), category_url)

            return products

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

    # ------------------------------------------------------------------
    # JS-based product extraction (reliable against obfuscated CSS)
    # ------------------------------------------------------------------
    async def _extract_products_js(self, page: Page) -> list[RawProduct]:
        """Extract product data via JavaScript evaluation.

        Tesco uses obfuscated CSS module class names that change every build.
        Instead of brittle CSS selectors, we find product tiles by structural
        patterns: the product list ``ul#list-content``, product links matching
        ``/products/\\d+``, and nearby price elements.
        """
        raw_items = await page.evaluate("""() => {
            const results = [];
            // The product list container uses id="list-content"
            const list = document.getElementById('list-content');
            const tiles = list ? list.querySelectorAll(':scope > li') : [];

            for (const tile of tiles) {
                try {
                    // Find the product title link (href contains /products/{id})
                    const links = tile.querySelectorAll('a[href*="/products/"]');
                    let name = '';
                    let href = '';
                    for (const link of links) {
                        const text = link.textContent.trim();
                        if (text && text.length > 2) {
                            name = text;
                            href = link.href || link.getAttribute('href') || '';
                            break;
                        }
                    }
                    if (!name) continue;

                    // Extract SKU from href
                    const skuMatch = href.match(/\\/products\\/(\\d+)/);
                    const sku = skuMatch ? skuMatch[1] : '';
                    if (!sku) continue;

                    // Find price: look for the main price text (format: €X.XX)
                    // The price container has ddsweb-price or priceText in class
                    let priceText = '';
                    let unitPriceText = '';
                    const allPs = tile.querySelectorAll('p');
                    for (const p of allPs) {
                        const cls = p.className || '';
                        const text = p.textContent.trim();
                        if (text.startsWith('€') && !priceText) {
                            if (text.includes('/')) {
                                // Unit price like "€0.28/each" or "€1.55/kg"
                                if (!unitPriceText) unitPriceText = text;
                            } else {
                                priceText = text;
                            }
                        }
                    }

                    // Also check span elements for price
                    if (!priceText) {
                        const spans = tile.querySelectorAll('span');
                        for (const s of spans) {
                            const text = s.textContent.trim();
                            if (text.match(/^€\\d/) && !text.includes('/')) {
                                priceText = text;
                                break;
                            }
                        }
                    }

                    if (!priceText) continue;

                    // Find promo/offer text
                    let promoLabel = '';
                    const offerEl = tile.querySelector('[data-auto="offer-text"]');
                    if (offerEl) {
                        promoLabel = offerEl.textContent.trim();
                    }
                    // Also check for Aldi Price Match or Clubcard badges
                    if (!promoLabel) {
                        const badges = tile.querySelectorAll('span[class*="logo"], span[class*="promo"], span[class*="offer"]');
                        for (const b of badges) {
                            const t = b.textContent.trim();
                            if (t && t.length > 2 && t.length < 80) {
                                promoLabel = t;
                                break;
                            }
                        }
                    }

                    // Find image
                    let imageUrl = '';
                    const img = tile.querySelector('img');
                    if (img) {
                        imageUrl = img.src || img.getAttribute('data-src') || '';
                    }

                    results.push({
                        sku: sku,
                        name: name,
                        price: priceText,
                        unitPrice: unitPriceText,
                        promoLabel: promoLabel,
                        imageUrl: imageUrl,
                        href: href,
                    });
                } catch (e) {
                    // skip tile
                }
            }
            return results;
        }""")

        products: list[RawProduct] = []
        for item in raw_items:
            try:
                name = item.get("name", "").strip()
                sku = item.get("sku", "")
                if not name or not sku:
                    continue

                # Parse price
                price_text = re.sub(r"[^\d.]", "", item.get("price", ""))
                try:
                    price = Decimal(price_text) if price_text else None
                except InvalidOperation:
                    price = None
                if not price or price == 0:
                    continue

                # Parse unit price
                unit_price = None
                unit = None
                up_text = item.get("unitPrice", "")
                if up_text:
                    up_match = re.search(r"€([\d.]+)/([\w]+)", up_text)
                    if up_match:
                        try:
                            unit_price = Decimal(up_match.group(1))
                            unit = up_match.group(2).lower()
                        except (InvalidOperation, ValueError):
                            pass

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

                # Promo
                promo_label = item.get("promoLabel") or None

                # Image
                image_url = item.get("imageUrl") or None
                if image_url and image_url.startswith("//"):
                    image_url = f"https:{image_url}"

                # Product URL
                href = item.get("href", "")
                product_url = href if href.startswith("http") else f"{BASE_URL}{href}" if href else None

                products.append(
                    RawProduct(
                        store_sku=sku,
                        name=name,
                        price=price,
                        promo_label=promo_label,
                        unit_price=unit_price,
                        unit=unit,
                        unit_size=unit_size,
                        image_url=image_url,
                        product_url=product_url,
                    )
                )
            except Exception:
                logger.debug("[tesco] Failed to parse JS-extracted product", exc_info=True)

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

    dry_run = "--dry-run" in sys.argv

    if dry_run:
        # Dry-run mode: scrape categories and print products without hitting the DB
        scraper = TescoScraper()
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
