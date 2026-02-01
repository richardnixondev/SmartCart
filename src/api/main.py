"""FastAPI application entry point for SmartCart."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.api.routers import baskets, comparison, prices, products

app = FastAPI(
    title="SmartCart API",
    description="Price comparison API for Irish supermarkets",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS - allow all origins during development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(products.router)
app.include_router(prices.router)
app.include_router(comparison.router)
app.include_router(baskets.router)


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")
