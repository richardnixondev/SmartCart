"""APScheduler setup for SmartCart.

Runs all scrapers daily at the configured hour and triggers product
matching once scraping completes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from src.core.config import settings
from src.core.database import async_session
from src.core.models import ScrapeRun, Store
from src.matcher.matcher import run_matching

logger = logging.getLogger(__name__)


async def _run_scraper(store_slug: str) -> None:
    """Dynamically import and execute a scraper for the given store slug.

    Each scraper module is expected to live at ``src.scrapers.<slug>`` and
    expose an async ``run()`` coroutine.
    """
    module_name = f"src.scrapers.{store_slug}"
    try:
        import importlib

        mod = importlib.import_module(module_name)
        run_fn = getattr(mod, "run", None)
        if run_fn is None:
            logger.warning("Scraper module %s has no run() function -- skipping", module_name)
            return
        logger.info("Starting scraper for %s", store_slug)
        await run_fn()
        logger.info("Scraper for %s completed successfully", store_slug)
    except ModuleNotFoundError:
        logger.warning("No scraper module found at %s -- skipping", module_name)
    except Exception:
        logger.exception("Scraper for %s failed", store_slug)


async def scrape_all() -> None:
    """Run every registered scraper, then run product matching."""
    logger.info("=== Starting daily scrape run at %s ===", datetime.now(timezone.utc).isoformat())

    async with async_session() as session:
        result = await session.execute(select(Store).order_by(Store.name))
        stores: list[Store] = list(result.scalars().all())

    for store in stores:
        await _run_scraper(store.slug)

    # Run matching after all scrapers complete
    logger.info("All scrapers finished -- starting product matching")
    async with async_session() as session:
        try:
            merges = await run_matching(session)
            logger.info("Matching complete: %d merges", merges)
        except Exception:
            logger.exception("Matching failed")

    logger.info("=== Daily scrape run finished ===")


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone="Europe/Dublin")

    scheduler.add_job(
        scrape_all,
        trigger=CronTrigger(hour=settings.scrape_hour, minute=settings.scrape_minute),
        id="daily_scrape",
        name="Daily scrape and match",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1 hour late
    )

    logger.info(
        "Scheduler configured: daily scrape at %02d:%02d Europe/Dublin",
        settings.scrape_hour,
        settings.scrape_minute,
    )
    return scheduler


async def _main() -> None:
    """Entry point for running the scheduler standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started. Press Ctrl+C to exit.")

    try:
        # Keep the event loop alive
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(_main())
