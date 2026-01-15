"""Scraper for Lidl Ireland (lidl.ie).

Similar to Aldi, Lidl has a relatively static product catalogue that we can
scrape with httpx + BeautifulSoup.  Weekly special offers are rendered with
JavaScript, so we fall back to Playwright for those pages.
"""

from __future__ import annotations

import asyncio
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

# Lidl Ireland product category paths
CATEGORY_PATHS = [
    "/products/fruit-and-vegetables/",
    "/products/bakery/",
    "/products/meat-and-fish/",
    "/products/dairy-and-eggs/",
    "/products/chilled/",
    "/products/frozen/",
    "/products/drinks/",
    "/products/food-cupboard/",
    "/products/snacks-and-sweets/",
    "/products/baby-and-toddler/",
    "/products/health-and-beauty/",
    "/products/household/",
    "/products/pet/",
]

# Weekly specials — JS-rendered, needs Playwright
WEEKLY_OFFERS_URLS = [
    f"{BASE_URL}/our-offers",
    f"{BASE_URL}/our-offers/this-week",
    f"{BASE_URL}/our-offers/next-week",
]


class LidlScraper(BaseScraper):
    store_slug = "lidl"

    # ------------------------------------------------------------------
    # Category URLs
    # ------------------------------------------------------------------
    async def get_category_urls(self) -> list[str]:
        urls = [f"{BASE_URL}{path}" for path in CATEGORY_PATHS]
        urls.extend(WEEKLY_OFFERS_URLS)
        return urls

    # ------------------------------------------------------------------
    # Scrape one category
    # ------------------------------------------------------------------
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        # Weekly offers pages need Playwright
        if "/our-offers" in category_url:
            return await self._scrape_offers_page(category_url)

        # Standard category — try httpx first
        try:
            return await self._scrape_with_httpx(category_url)
        except Exception as exc:
            logger.warning(
                "[lidl] httpx failed for %s (%s), falling back to Playwright",
                category_url,
                exc,
            )
            return await self._scrape_with_playwright(category_url)

    # ------------------------------------------------------------------
    # httpx-based scraping
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

                # Pagination
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

    def _parse_html(self, soup: BeautifulSoup) -> list[RawProduct]:
        """Parse product tiles from a Lidl category page."""
        products: list[RawProduct] = []

        # Lidl product grid items
        tiles = soup.select(
            "div[class*='product-grid-box'], "
            "div[class*='ACampaignGrid__item'], "
            "article[class*='product'], "
            "div[class*='ProductTile'], "
            "div.ret-o-card"
        )

        if not tiles:
            tiles = soup.select(
                "div[class*='product-item'], "
                "li[class*='product-item'], "
                "div[class*='product-card']"
            )

        for tile in tiles:
            try:
                # --- Name + link ---
                name_el = (
                    tile.select_one(
                        "h3[class*='product-title'], "
                        "a[class*='product-title'], "
                        "h2[class*='title'], "
                        "p[class*='product-grid-box__title'], "
                        "strong[class*='title']"
                    )
                    or tile.select_one("h3, h2, a")
                )
                if not name_el:
                    continue

                name = name_el.get_text(strip=True)
                if not name:
                    continue

                # Try to get link
                link_el = tile.select_one("a[href]") or name_el
                href = link_el.get("href", "") if link_el else ""

                # --- SKU ---
                sku = tile.get("data-product-id", "") or tile.get("data-id", "")
                if not sku and href:
                    sku_match = re.search(r"/p(\d+)", href) or re.search(r"/(\d{4,})", href)
                    sku = sku_match.group(1) if sku_match else ""
                if not sku:
                    sku = f"lidl-{hash(name) % 1000000}"

                # --- Price ---
                price_el = tile.select_one(
                    "span[class*='price'], "
                    "span[class*='pricebox__price'], "
                    "div[class*='price'], "
                    "strong[class*='price']"
                )
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = self._parse_price(price_text)
                if price is None or price == 0:
                    continue

                # --- Strikethrough / original price ---
                promo_price = None
                promo_label = None
                was_el = tile.select_one(
                    "del, "
                    "s, "
                    "span[class*='strikethrough'], "
                    "span[class*='pricebox__old-price']"
                )
                if was_el:
                    original = self._parse_price(was_el.get_text(strip=True))
                    if original and original > price:
                        promo_price = price
                        price = original

                # Promo badge text
                badge_el = tile.select_one(
                    "span[class*='badge'], "
                    "div[class*='ribbon'], "
                    "span[class*='sticker']"
                )
                if badge_el:
                    promo_label = badge_el.get_text(strip=True) or promo_label

                # --- Image ---
                image_url = None
                img_el = tile.select_one("img")
                if img_el:
                    image_url = (
                        img_el.get("src")
                        or img_el.get("data-src")
                        or img_el.get("srcset", "").split(",")[0].split(" ")[0]
                    )
                    if image_url and image_url.startswith("//"):
                        image_url = f"https:{image_url}"
                    elif image_url and image_url.startswith("/"):
                        image_url = f"{BASE_URL}{image_url}"

                # --- Unit / size from name ---
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

                # --- Unit price ---
                unit_price = None
                unit_price_el = tile.select_one(
                    "span[class*='unit-price'], "
                    "span[class*='pricebox__basic-quantity'], "
                    "div[class*='unit-price']"
                )
                if unit_price_el:
                    up_text = unit_price_el.get_text(strip=True)
                    up_match = re.search(r"([\d.,]+)\s*/\s*(\w+)", up_text)
                    if up_match:
                        cleaned = up_match.group(1).replace(",", ".")
                        try:
                            unit_price = Decimal(cleaned)
                            unit = unit or up_match.group(2).lower()
                        except (InvalidOperation, ValueError):
                            pass

                # --- Brand ---
                brand = None
                brand_el = tile.select_one(
                    "span[class*='brand'], "
                    "p[class*='brand'], "
                    "span[class*='keyfact']"
                )
                if brand_el:
                    brand = brand_el.get_text(strip=True) or None

                product_url = href
                if product_url and not product_url.startswith("http"):
                    product_url = f"{BASE_URL}{product_url}"

                products.append(
                    RawProduct(
                        store_sku=sku,
                        name=name,
                        price=price,
                        promo_price=promo_price,
                        promo_label=promo_label,
                        unit_price=unit_price,
                        unit=unit,
                        unit_size=unit_size,
                        brand=brand,
                        image_url=image_url,
                        product_url=product_url or None,
                    )
                )

            except Exception:
                logger.debug("[lidl] Failed to parse product tile", exc_info=True)

        return products

    # ------------------------------------------------------------------
    # Playwright-based scraping (fallback / offers)
    # ------------------------------------------------------------------
    async def _scrape_with_playwright(self, url: str) -> list[RawProduct]:
        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()
            logger.info("[lidl] Playwright loading %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)

            await self._dismiss_overlays(page)
            await self._scroll_page(page)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            return self._parse_html(soup)

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

    async def _scrape_offers_page(self, url: str) -> list[RawProduct]:
        """Scrape Lidl weekly offers page (JS-rendered)."""
        products: list[RawProduct] = []

        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()
            logger.info("[lidl] Loading offers page %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)

            await self._dismiss_overlays(page)
            await self._scroll_page(page, scrolls=10)

            # Offer tiles may use different markup to the main catalogue
            tiles = page.locator(
                "div[class*='AOfferCard'], "
                "div[class*='OfferCard'], "
                "div[class*='product-grid-box'], "
                "article[class*='product'], "
                "a[class*='ret-o-card']"
            )
            count = await tiles.count()
            logger.info("[lidl] Found %d offer tiles", count)

            for i in range(count):
                try:
                    tile = tiles.nth(i)

                    name_el = tile.locator(
                        "h3, h2, "
                        "strong[class*='title'], "
                        "p[class*='title'], "
                        "span[class*='title']"
                    )
                    name = ""
                    if await name_el.count() > 0:
                        name = (await name_el.first.inner_text()).strip()
                    if not name:
                        continue

                    price_el = tile.locator(
                        "span[class*='price'], "
                        "strong[class*='price'], "
                        "div[class*='pricebox__price']"
                    )
                    price_text = ""
                    if await price_el.count() > 0:
                        price_text = await price_el.first.inner_text()
                    price = self._parse_price(price_text)
                    if price is None or price == 0:
                        continue

                    sku = f"lidl-offer-{hash(name) % 1000000}"

                    # Was price
                    promo_price = None
                    promo_label = "Weekly Offer"
                    was_el = tile.locator("del, s, span[class*='old-price']")
                    if await was_el.count() > 0:
                        was_text = await was_el.first.inner_text()
                        original = self._parse_price(was_text)
                        if original and original > price:
                            promo_price = price
                            price = original

                    # Dates / availability label
                    date_el = tile.locator(
                        "span[class*='date'], "
                        "span[class*='availability']"
                    )
                    if await date_el.count() > 0:
                        avail = (await date_el.first.inner_text()).strip()
                        if avail:
                            promo_label = f"Weekly Offer - {avail}"

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
                            promo_price=promo_price,
                            promo_label=promo_label,
                            image_url=image_url,
                        )
                    )
                except Exception:
                    logger.debug("[lidl] Failed to parse offer tile %d", i, exc_info=True)

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
