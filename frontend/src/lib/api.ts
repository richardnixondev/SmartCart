import type {
  BasketCompareOut,
  BasketIn,
  BattleOut,
  CategoryOut,
  ComparisonOut,
  PriceHistoryOut,
  ProductListOut,
  SearchPriceResult,
  StatsOut,
  StoreOut,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ──────────────────────────── Stores / Categories ────────────────────────────

export function fetchStores() {
  return fetchApi<StoreOut[]>("/api/stores");
}

export function fetchCategories() {
  return fetchApi<CategoryOut[]>("/api/categories");
}

// ──────────────────────────── Products ───────────────────────────────────────

export function fetchProducts(params: {
  page?: number;
  limit?: number;
  search?: string;
  category_id?: number;
  store_id?: number;
}) {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.search) sp.set("search", params.search);
  if (params.category_id) sp.set("category_id", String(params.category_id));
  if (params.store_id) sp.set("store_id", String(params.store_id));
  return fetchApi<ProductListOut>(`/api/products?${sp.toString()}`);
}

// ──────────────────────────── Prices ─────────────────────────────────────────

export function fetchPriceHistory(productId: number, days = 30) {
  return fetchApi<PriceHistoryOut[]>(
    `/api/products/${productId}/prices?days=${days}`
  );
}

export function searchPrices(q: string, limit = 60) {
  return fetchApi<SearchPriceResult[]>(
    `/api/search-prices?q=${encodeURIComponent(q)}&limit=${limit}`
  );
}

export function fetchStats() {
  return fetchApi<StatsOut>("/api/stats");
}

// ──────────────────────────── Comparison ─────────────────────────────────────

export function fetchComparison(productId: number) {
  return fetchApi<ComparisonOut>(`/api/products/${productId}/compare`);
}

export function fetchBattle(categoryId?: number) {
  const params = categoryId ? `?category_id=${categoryId}` : "";
  return fetchApi<BattleOut>(`/api/battle${params}`);
}

// ──────────────────────────── Baskets ────────────────────────────────────────

export function compareBasket(basket: BasketIn) {
  return fetchApi<BasketCompareOut>("/api/baskets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(basket),
  });
}
