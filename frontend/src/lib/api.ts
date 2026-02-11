import type {
  AdminProductListOut,
  AdminProductOut,
  AdminStoreProductOut,
  BasketCompareOut,
  BasketIn,
  BattleOut,
  CategoryOut,
  ComparisonOut,
  MergeProductsIn,
  MergeProductsOut,
  PriceHistoryOut,
  ProductListOut,
  ProductUpdateIn,
  SearchPriceResult,
  StatsOut,
  StoreOut,
  UnlinkOut,
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

// ──────────────────────────── Admin ─────────────────────────────────────────

export function fetchUnmatched(params: {
  search?: string;
  store_id?: number;
  page?: number;
  limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params.search) sp.set("search", params.search);
  if (params.store_id) sp.set("store_id", String(params.store_id));
  if (params.page) sp.set("page", String(params.page));
  if (params.limit) sp.set("limit", String(params.limit));
  return fetchApi<AdminProductListOut>(`/api/admin/unmatched?${sp.toString()}`);
}

export function fetchAdminStoreProducts(productId: number) {
  return fetchApi<AdminStoreProductOut[]>(
    `/api/admin/products/${productId}/store-products`
  );
}

export function updateProduct(productId: number, data: ProductUpdateIn) {
  return fetchApi<AdminProductOut>(`/api/admin/products/${productId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function mergeProducts(data: MergeProductsIn) {
  return fetchApi<MergeProductsOut>("/api/admin/products/merge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function unlinkStoreProduct(productId: number, storeProductId: number) {
  return fetchApi<UnlinkOut>(
    `/api/admin/products/${productId}/unlink/${storeProductId}`,
    { method: "POST" }
  );
}
