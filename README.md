# SmartCart

Price comparison engine for Irish supermarkets. Scrapes five major stores daily, matches identical products across them, and surfaces the cheapest option through a dashboard and REST API.

## Stores Tracked

| Store | Method |
|-------|--------|
| Tesco Ireland | Playwright (XHR intercept) |
| Dunnes Stores | Playwright (JS rendering) |
| SuperValu | Playwright (authenticated) |
| Aldi Ireland | HTTP + Playwright fallback |
| Lidl Ireland | HTTP + Playwright fallback |

## Features

**Scrapers** — Automated daily collection via APScheduler. Each scraper handles store-specific anti-bot measures (Akamai WAF, JS rendering, cookie walls). Raw products are normalized and persisted with full price history.

**Product Matcher** — Three-level cross-store matching: exact EAN barcode, fuzzy name matching (rapidfuzz) with unit-size validation, and batch singleton merging.

**REST API** (FastAPI) — Product listing with filters, cross-store price comparison, store battle rankings, basket cost comparison, search-prices endpoint, and admin endpoints for manual matching.

**Dashboard** (Next.js + shadcn/ui)
- **Overview** — KPI cards, cheapest store indicator, average prices by store
- **Price Battle** — Store vs store ranking with win percentages and category filter
- **Product History** — Per-product price trend charts across stores over time
- **Basket Compare** — Build a shopping list, compare total cost across all stores
- **Product Admin** — Manual merge/unlink of mismatched products, inline metadata editing

## Tech Stack

| Layer | Stack |
|-------|-------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), PostgreSQL, Alembic |
| Scrapers | Playwright, httpx, BeautifulSoup |
| Matching | rapidfuzz, custom normalizer |
| Frontend | Next.js 16, TypeScript, Tailwind CSS, shadcn/ui, Recharts, TanStack Query |
| Infra | Docker Compose (db + api + frontend) |

## Quick Start

```bash
# Start all services
docker compose up -d

# Or run locally
cp .env.example .env          # edit DB credentials
pip install -e ".[dev]"
alembic upgrade head
python -m src.core.seed        # seed stores & categories
uvicorn src.api.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## Project Structure

```
src/
  api/            # FastAPI app, routers, schemas
  core/           # Config, database, ORM models
  scrapers/       # Per-store scraper implementations
  matcher/        # Cross-store product matching
  scheduler/      # APScheduler daily job
frontend/         # Next.js dashboard
tests/            # Pytest suite
alembic/          # Database migrations
```

## Status

- [x] Scrapers for all 5 stores
- [x] Product matcher (EAN + fuzzy)
- [x] REST API with comparison, battle, basket endpoints
- [x] Next.js dashboard (5 pages)
- [x] Product Admin (merge, edit, unlink)
- [x] Docker Compose deployment
- [x] Test suite
- [ ] Automated CI/CD pipeline
- [ ] User accounts & saved baskets
- [ ] Price drop notifications
- [ ] Mobile-responsive PWA
