from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(255))

    store_products: Mapped[list["StoreProduct"]] = relationship(back_populates="store")
    scrape_runs: Mapped[list["ScrapeRun"]] = relationship(back_populates="store")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100))
    ean: Mapped[str | None] = mapped_column(String(13), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_size: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    image_url: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    category: Mapped[Category | None] = relationship(back_populates="products")
    store_products: Mapped[list["StoreProduct"]] = relationship(back_populates="product")


class StoreProduct(Base):
    __tablename__ = "store_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    store_sku: Mapped[str | None] = mapped_column(String(100))
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    store_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped[Product] = relationship(back_populates="store_products")
    store: Mapped[Store] = relationship(back_populates="store_products")
    price_records: Mapped[list["PriceRecord"]] = relationship(back_populates="store_product")


class PriceRecord(Base):
    __tablename__ = "price_records"
    __table_args__ = (
        Index("ix_price_records_store_product_scraped", "store_product_id", "scraped_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_product_id: Mapped[int] = mapped_column(
        ForeignKey("store_products.id"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    promo_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    promo_label: Mapped[str | None] = mapped_column(String(100))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    store_product: Mapped[StoreProduct] = relationship(back_populates="price_records")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")
    products_scraped: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[str | None] = mapped_column(Text)

    store: Mapped[Store] = relationship(back_populates="scrape_runs")
