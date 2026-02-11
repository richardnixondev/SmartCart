"""Scraper for SuperValu Ireland (shop.supervalu.ie).

SuperValu requires authentication to browse the full catalogue.  We use
Playwright to log in with the credentials from settings and then browse
each category.

IMPORTANT: Login URL is at supervalu.ie/login/ (NOT shop.supervalu.ie/login).
Category URLs use the format /categories/{slug}-id-{code}.
After login, a store must be selected before browsing products.
"""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal, InvalidOperation

from playwright.async_api import Page

from src.core.config import settings
from src.scrapers.base import (
    BaseScraper,
    RawProduct,
    random_delay,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://shop.supervalu.ie"
LOGIN_URL = "https://supervalu.ie/login/"

# Confirmed SuperValu category paths (format: /categories/{slug}-id-{code})
CATEGORY_PATHS = [
    "/categories/fruit-vegetables-id-O100001",
    "/categories/meat-%26-poultry-id-O100015",
    "/categories/chilled-food-id-O100030",
    "/categories/frozen-foods-id-O100045",
]


class SuperValuScraper(BaseScraper):
    store_slug = "supervalu"

    def __init__(self) -> None:
        self._email = settings.supervalu_email
        self._password = settings.supervalu_password
        if not self._email or not self._password:
            logger.warning(
                "[supervalu] Missing SUPERVALU_EMAIL / SUPERVALU_PASSWORD in settings. "
                "Login will likely fail."
            )

    # ------------------------------------------------------------------
    # Category URLs
    # ------------------------------------------------------------------
    async def get_category_urls(self) -> list[str]:
        """Return category URLs, preferring dynamic discovery.

        Falls back to the static seed list if discovery finds nothing.
        """
        discovered = await self._discover_categories()
        if discovered:
            logger.info(
                "[supervalu] Discovered %d category URLs from allaisles", len(discovered)
            )
            return discovered

        logger.warning("[supervalu] Category discovery found nothing; using static seed list")
        return [f"{BASE_URL}{path}" for path in CATEGORY_PATHS]

    async def _discover_categories(self) -> list[str]:
        """Discover category URLs from /shopping/allaisles."""
        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()

            # Must log in first to access the catalogue
            await self._login(page)
            await self._select_store(page)
            await random_delay(1.0, 2.0)

            logger.info("[supervalu] Discovering categories from allaisles page")
            await page.goto(
                f"{BASE_URL}/shopping/allaisles",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            await asyncio.sleep(3)

            links = await page.evaluate('''() => {
                return [...document.querySelectorAll('a[href*="/categories/"]')]
                    .map(a => a.href)
                    .filter(href => href.includes('-id-'));
            }''')
            unique = list(set(links))
            return unique

        except Exception:
            logger.warning("[supervalu] Category discovery failed", exc_info=True)
            return []
        finally:
            await context.close()
            await browser.close()
            await pw.stop()

    # ------------------------------------------------------------------
    # Scrape one category
    # ------------------------------------------------------------------
    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        products: list[RawProduct] = []

        pw, browser, context = await self._get_browser_context(headless=True)
        try:
            page = await context.new_page()

            # Authenticate
            await self._login(page)
            await random_delay(1.0, 2.0)

            # Select a store (required before browsing products)
            await self._select_store(page)
            await random_delay(0.5, 1.0)

            # Navigate to category
            logger.info("[supervalu] Loading category %s", category_url)
            await page.goto(category_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)

            # Dismiss overlays
            await self._dismiss_overlays(page)

            # Paginate through results
            page_num = 0
            while True:
                page_num += 1
                await self._scroll_page(page)
                await asyncio.sleep(1)

                batch = await self._extract_products(page)
                seen_skus = {p.store_sku for p in products}
                new_count = 0
                for p in batch:
                    if p.store_sku not in seen_skus:
                        products.append(p)
                        seen_skus.add(p.store_sku)
                        new_count += 1

                logger.info(
                    "[supervalu] Page %d: %d tiles, %d new (total %d)",
                    page_num,
                    len(batch),
                    new_count,
                    len(products),
                )

                if not await self._go_next_page(page):
                    break

                await random_delay(1.5, 3.0)

        finally:
            await context.close()
            await browser.close()
            await pw.stop()

        return products

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    async def _login(self, page: Page) -> None:
        """Log in to SuperValu using stored credentials."""
        logger.info("[supervalu] Logging in at %s", LOGIN_URL)
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(2)

        # Dismiss cookie consent
        await self._dismiss_overlays(page)

        # Fill login form — SuperValu uses a standard email/password form
        email_input = page.locator(
            "input[type='email'], "
            "input[name='email'], "
            "input[id*='email'], "
            "input[placeholder*='email' i]"
        )
        password_input = page.locator(
            "input[type='password'], "
            "input[name='password'], "
            "input[id*='password']"
        )

        if await email_input.count() == 0 or await password_input.count() == 0:
            logger.error("[supervalu] Could not find login form fields")
            return

        await email_input.first.fill(self._email)
        await asyncio.sleep(0.3)
        await password_input.first.fill(self._password)
        await asyncio.sleep(0.3)

        # Submit
        submit_btn = page.locator(
            "button[type='submit'], "
            "button:has-text('Sign In'), "
            "button:has-text('Log In'), "
            "button:has-text('Login'), "
            "input[type='submit']"
        )
        if await submit_btn.count() > 0:
            await submit_btn.first.click()
        else:
            await password_input.first.press("Enter")

        # Wait for navigation after login
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        await asyncio.sleep(2)

        # Verify login succeeded — check for account indicator or absence of login form
        if "/login" in page.url:
            logger.warning("[supervalu] Still on login page after submission — login may have failed")
        else:
            logger.info("[supervalu] Login appears successful (now at %s)", page.url)

    async def _select_store(self, page: Page) -> None:
        """After login, select a store by navigating to allaisles or entering Eircode.

        SuperValu requires a store/delivery area to be selected before
        product prices and availability are shown.
        """
        try:
            # First check if we're already on a page that has store selected
            # (i.e., products are visible)
            product_check = page.locator("[class*='ProductCard'], [class*='product-card']")
            if await product_check.count() > 0:
                logger.debug("[supervalu] Store appears already selected")
                return

            # Look for Eircode / postcode input (store selection modal or page)
            eircode_input = page.locator(
                "input[placeholder*='Eircode' i], "
                "input[name*='eircode' i], "
                "input[placeholder*='postcode' i], "
                "input[placeholder*='Enter your area' i], "
                "input[id*='eircode' i], "
                "input[id*='postcode' i]"
            )
            if await eircode_input.count() > 0:
                logger.info("[supervalu] Found Eircode input, entering D01 F5P2")
                await eircode_input.first.fill("D01 F5P2")  # Dublin city center
                await asyncio.sleep(1)

                # Click search/submit button
                submit = page.locator(
                    "button[type='submit'], "
                    "button:has-text('Find'), "
                    "button:has-text('Search'), "
                    "button:has-text('Go'), "
                    "button[aria-label*='search' i]"
                )
                if await submit.count() > 0:
                    await submit.first.click()
                    await asyncio.sleep(2)

                    # If a store list appears, pick the first one
                    store_option = page.locator(
                        "button:has-text('Select'), "
                        "a:has-text('Select Store'), "
                        "button:has-text('Choose'), "
                        "li[class*='store'] button, "
                        "div[class*='store-item'] button"
                    )
                    if await store_option.count() > 0:
                        await store_option.first.click()
                        await asyncio.sleep(2)
                        logger.info("[supervalu] Store selected via Eircode search")
            else:
                logger.debug("[supervalu] No Eircode input found; store may already be set")

        except Exception:
            logger.debug("[supervalu] Store selection handling failed", exc_info=True)

    # ------------------------------------------------------------------
    # DOM extraction
    # ------------------------------------------------------------------
    async def _extract_products(self, page: Page) -> list[RawProduct]:
        """Parse product data from the current SuperValu page."""
        products: list[RawProduct] = []

        # SuperValu product tiles
        tiles = page.locator(
            "div[class*='ProductCard'], "
            "div[class*='product-card'], "
            "div[data-testid='product-card'], "
            "li[class*='ProductCard'], "
            "div[class*='ColListing'] > div"
        )
        count = await tiles.count()

        for i in range(count):
            try:
                tile = tiles.nth(i)

                # --- Name + Link ---
                name_el = tile.locator(
                    "a[class*='ProductCard__title'], "
                    "a[class*='product-card__title'], "
                    "h2 a, h3 a, "
                    "a[data-testid='product-title'], "
                    "span[class*='ProductCardTitle']"
                )
                name = ""
                href = ""
                if await name_el.count() > 0:
                    name = (await name_el.first.inner_text()).strip()
                    href = await name_el.first.get_attribute("href") or ""
                else:
                    # Try any anchor
                    any_a = tile.locator("a")
                    if await any_a.count() > 0:
                        name = (await any_a.first.inner_text()).strip()
                        href = await any_a.first.get_attribute("href") or ""

                if not name:
                    continue

                # --- SKU ---
                sku = ""
                data_id = (
                    await tile.get_attribute("data-product-id")
                    or await tile.get_attribute("data-sku")
                    or await tile.get_attribute("data-product-ean")
                    or ""
                )
                sku = data_id
                if not sku and href:
                    sku_match = re.search(r"/(\d{5,})", href)
                    sku = sku_match.group(1) if sku_match else ""
                if not sku:
                    sku = f"sv-{hash(name) % 1000000}"

                # --- EAN (SuperValu sometimes exposes it) ---
                ean = await tile.get_attribute("data-product-ean") or None

                # --- Price ---
                price_el = tile.locator(
                    "span[class*='ProductCardPrice'], "
                    "span[class*='price-value'], "
                    "span[data-testid='product-price'], "
                    "span[class*='Price__current'], "
                    "span.price"
                )
                price_text = ""
                if await price_el.count() > 0:
                    price_text = await price_el.first.inner_text()

                price = self._parse_price(price_text)
                if price is None or price == 0:
                    continue

                # --- Promo / special ---
                promo_price = None
                promo_label = None
                promo_el = tile.locator(
                    "span[class*='ProductCardPromo'], "
                    "span[class*='offer-badge'], "
                    "div[class*='PromoBadge'], "
                    "span[class*='was-price'], "
                    "span[data-testid='product-promo']"
                )
                if await promo_el.count() > 0:
                    promo_label = (await promo_el.first.inner_text()).strip() or None

                # --- Unit price ---
                unit_price = None
                unit = None
                unit_el = tile.locator(
                    "span[class*='UnitPrice'], "
                    "span[class*='unit-price'], "
                    "span[data-testid='unit-price']"
                )
                if await unit_el.count() > 0:
                    unit_text = await unit_el.first.inner_text()
                    up_match = re.search(r"[€]?\s*([\d.]+)\s*/\s*(\w+)", unit_text)
                    if up_match:
                        try:
                            unit_price = Decimal(up_match.group(1))
                            unit = up_match.group(2).lower()
                        except (InvalidOperation, ValueError):
                            pass

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

                # --- Brand (heuristic) ---
                brand = None
                brand_el = tile.locator(
                    "span[class*='Brand'], "
                    "span[data-testid='product-brand']"
                )
                if await brand_el.count() > 0:
                    brand = (await brand_el.first.inner_text()).strip() or None

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
                        brand=brand,
                        ean=ean,
                        image_url=image_url,
                        product_url=product_url or None,
                    )
                )

            except Exception:
                logger.debug("[supervalu] Failed to parse tile %d", i, exc_info=True)

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
    async def _scroll_page(page: Page, scrolls: int = 5) -> None:
        for _ in range(scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(0.6)

    @staticmethod
    async def _go_next_page(page: Page) -> bool:
        """Attempt to navigate to the next page of results. Return True on success."""
        for selector in [
            "a[aria-label='Next page']",
            "a[rel='next']",
            "button:has-text('Next')",
            "a:has-text('Next')",
            "li.next a",
            "a[class*='pagination__next']",
        ]:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=15_000)
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
    scraper = SuperValuScraper()
    result = await scraper.run()
    print(f"\nDone: {result.status}")
    print(f"Products scraped: {len(result.products)}")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
