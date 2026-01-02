"""Seed stores and categories into the database."""

import asyncio

from sqlalchemy import select

from src.core.database import async_session
from src.core.models import Category, Store

STORES = [
    {
        "name": "Tesco Ireland",
        "slug": "tesco",
        "base_url": "https://www.tesco.ie",
        "logo_url": "https://www.tesco.ie/favicon.ico",
    },
    {
        "name": "Dunnes Stores",
        "slug": "dunnes",
        "base_url": "https://www.dunnesstores.com",
        "logo_url": "https://www.dunnesstores.com/favicon.ico",
    },
    {
        "name": "SuperValu",
        "slug": "supervalu",
        "base_url": "https://shop.supervalu.ie",
        "logo_url": "https://shop.supervalu.ie/favicon.ico",
    },
    {
        "name": "Aldi Ireland",
        "slug": "aldi",
        "base_url": "https://www.aldi.ie",
        "logo_url": "https://www.aldi.ie/favicon.ico",
    },
    {
        "name": "Lidl Ireland",
        "slug": "lidl",
        "base_url": "https://www.lidl.ie",
        "logo_url": "https://www.lidl.ie/favicon.ico",
    },
]

CATEGORIES = [
    {"name": "Dairy", "slug": "dairy"},
    {"name": "Meat & Poultry", "slug": "meat-poultry"},
    {"name": "Bakery", "slug": "bakery"},
    {"name": "Fruit & Vegetables", "slug": "fruit-vegetables"},
    {"name": "Frozen", "slug": "frozen"},
    {"name": "Drinks", "slug": "drinks"},
    {"name": "Snacks & Confectionery", "slug": "snacks-confectionery"},
    {"name": "Household", "slug": "household"},
    {"name": "Personal Care", "slug": "personal-care"},
    {"name": "Baby", "slug": "baby"},
    {"name": "Deli & Ready Meals", "slug": "deli-ready-meals"},
    {"name": "Pantry & Cooking", "slug": "pantry-cooking"},
    {"name": "Cereals & Breakfast", "slug": "cereals-breakfast"},
    {"name": "Pet Care", "slug": "pet-care"},
    {"name": "Alcohol", "slug": "alcohol"},
]


async def seed():
    async with async_session() as session:
        # Seed stores
        for store_data in STORES:
            existing = await session.execute(
                select(Store).where(Store.slug == store_data["slug"])
            )
            if not existing.scalar_one_or_none():
                session.add(Store(**store_data))

        # Seed categories
        for cat_data in CATEGORIES:
            existing = await session.execute(
                select(Category).where(Category.slug == cat_data["slug"])
            )
            if not existing.scalar_one_or_none():
                session.add(Category(**cat_data))

        await session.commit()
        print("Seed complete: stores and categories loaded.")


if __name__ == "__main__":
    asyncio.run(seed())
