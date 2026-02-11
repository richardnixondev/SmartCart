// TypeScript interfaces mirroring src/api/schemas.py
// Decimal → number, datetime → string (ISO)

// ──────────────────────────── Stores / Categories ────────────────────────────

export interface StoreOut {
  id: number;
  name: string;
  slug: string;
  base_url: string;
  logo_url: string | null;
}

export interface CategoryOut {
  id: number;
  name: string;
  slug: string;
}

// ──────────────────────────── Products ───────────────────────────────────────

export interface ProductOut {
  id: number;
  name: string;
  brand: string | null;
  ean: string | null;
  category: CategoryOut | null;
  unit: string | null;
  unit_size: number | null;
  image_url: string | null;
}

export interface ProductListOut {
  items: ProductOut[];
  total: number;
}

// ──────────────────────────── Store Products & Prices ────────────────────────

export interface StoreProductOut {
  store: StoreOut;
  store_name: string;
  store_url: string | null;
  latest_price: number | null;
  promo_price: number | null;
  promo_label: string | null;
}

export interface PriceRecordOut {
  price: number;
  promo_price: number | null;
  promo_label: string | null;
  unit_price: number | null;
  in_stock: boolean;
  scraped_at: string;
}

export interface PriceHistoryOut {
  store: StoreOut;
  prices: PriceRecordOut[];
}

// ──────────────────────────── Comparison ─────────────────────────────────────

export interface ComparisonOut {
  product: ProductOut;
  stores: StoreProductOut[];
}

// ──────────────────────────── Store Battle ───────────────────────────────────

export interface BattleResult {
  store: StoreOut;
  wins: number;
  avg_price: number;
  cheapest_pct: number;
}

export interface BattleOut {
  category: string | null;
  results: BattleResult[];
}

// ──────────────────────────── Baskets ────────────────────────────────────────

export interface BasketItemIn {
  product_id: number;
  quantity: number;
}

export interface BasketIn {
  name: string;
  items: BasketItemIn[];
}

export interface BasketStoreTotal {
  store: StoreOut;
  total: number;
  items_found: number;
  items_missing: number;
}

export interface BasketCompareOut {
  basket_name: string;
  stores: BasketStoreTotal[];
}

// ──────────────────────────── Stats / KPIs ───────────────────────────────────

export interface AvgPriceByStore {
  store: StoreOut;
  avg_price: number;
}

export interface StatsOut {
  total_products: number;
  total_stores: number;
  total_price_records: number;
  last_scrape: string | null;
  avg_prices_by_store: AvgPriceByStore[];
}

// ──────────────────────────── Search Prices ──────────────────────────────────

export interface SearchPriceResult {
  product_name: string;
  store: string;
  store_slug: string;
  price: number;
  promo_price: number | null;
  promo_label: string | null;
  effective_price: number;
  unit_price: number | null;
  image_url: string | null;
  product_url: string | null;
}

// ──────────────────────────── Admin ─────────────────────────────────────────

export interface AdminStoreProductOut {
  id: number;
  store: StoreOut;
  store_sku: string | null;
  store_name: string;
  store_url: string | null;
  is_active: boolean;
  latest_price: number | null;
  promo_price: number | null;
}

export interface AdminProductOut {
  id: number;
  name: string;
  brand: string | null;
  ean: string | null;
  category: CategoryOut | null;
  unit: string | null;
  unit_size: number | null;
  image_url: string | null;
  store_product_count: number;
  store_products: AdminStoreProductOut[];
}

export interface AdminProductListOut {
  items: AdminProductOut[];
  total: number;
}

export interface ProductUpdateIn {
  name?: string;
  brand?: string | null;
  ean?: string | null;
  unit?: string | null;
  unit_size?: number | null;
  image_url?: string | null;
  category_id?: number | null;
}

export interface MergeProductsIn {
  product_ids: number[];
  target_id?: number;
}

export interface MergeProductsOut {
  kept_product_id: number;
  merged_product_ids: number[];
  store_products_moved: number;
}

export interface UnlinkOut {
  new_product_id: number;
  store_product_id: number;
}
