export const queryKeys = {
  stats: ["stats"] as const,
  stores: ["stores"] as const,
  categories: ["categories"] as const,
  battle: (categoryId?: number) =>
    categoryId ? (["battle", categoryId] as const) : (["battle"] as const),
  products: (params: {
    page?: number;
    limit?: number;
    search?: string;
  }) => ["products", params] as const,
  searchPrices: (q: string, limit?: number) =>
    ["search-prices", q, limit] as const,
  priceHistory: (productId: number, days?: number) =>
    ["price-history", productId, days] as const,
  comparison: (productId: number) => ["comparison", productId] as const,
};

// Stale time config (mirrors Streamlit TTLs)
export const staleTimes = {
  stats: 2 * 60 * 1000,         // 2 min
  battle: 2 * 60 * 1000,        // 2 min
  products: 2 * 60 * 1000,      // 2 min
  searchPrices: 1 * 60 * 1000,  // 1 min
  priceHistory: 1 * 60 * 1000,  // 1 min
  comparison: 1 * 60 * 1000,    // 1 min
  stores: 5 * 60 * 1000,        // 5 min
  categories: 5 * 60 * 1000,    // 5 min
};
