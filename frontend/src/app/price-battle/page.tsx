"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchBattle, searchPrices } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { useDebounce } from "@/hooks/use-debounce";
import { formatCurrency } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { KpiCard } from "@/components/layout/kpi-card";
import { ProductSearchInput } from "@/components/products/product-search-input";
import { PopularSearchGrid } from "@/components/battle/popular-search-grid";
import { PriceResultsTable } from "@/components/battle/price-results-table";
import { BestDealsList } from "@/components/battle/best-deals-list";
import { SearchAvgBarChart } from "@/components/charts/search-avg-bar-chart";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { getStoreColor } from "@/lib/store-colors";

export default function PriceBattlePage() {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search);

  const { data: battle } = useQuery({
    queryKey: queryKeys.battle(),
    queryFn: () => fetchBattle(),
    staleTime: staleTimes.battle,
  });

  const { data: searchResults, isLoading: searchLoading } = useQuery({
    queryKey: queryKeys.searchPrices(debouncedSearch, 60),
    queryFn: () => searchPrices(debouncedSearch, 60),
    staleTime: staleTimes.searchPrices,
    enabled: debouncedSearch.length >= 2,
  });

  const storesWithData = (battle?.results ?? []).filter(
    (r) => Number(r.avg_price) > 0
  );

  // Store counts for caption
  const storeCounts = searchResults
    ? searchResults.reduce<Record<string, number>>((acc, r) => {
        acc[r.store] = (acc[r.store] || 0) + 1;
        return acc;
      }, {})
    : {};

  return (
    <div>
      <PageHeader
        title="Price Battle"
        subtitle="Compare real product prices across Irish supermarkets."
      />

      {/* Store Overview */}
      {storesWithData.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-3">Store Overview</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
            {storesWithData.map((r) => (
              <div
                key={r.store.id}
                className="border-l-4 rounded-lg"
                style={{ borderLeftColor: getStoreColor(r.store.name) }}
              >
                <KpiCard
                  title={r.store.name}
                  value={`${formatCurrency(r.avg_price)} avg`}
                />
              </div>
            ))}
          </div>
          <Separator className="mb-6" />
        </>
      )}

      {/* Compare Products */}
      <h2 className="text-lg font-semibold mb-3">Compare Products</h2>

      <div className="space-y-4 mb-6">
        <PopularSearchGrid onSelect={setSearch} />
        <div className="max-w-md">
          <ProductSearchInput
            value={search}
            onChange={setSearch}
            placeholder="e.g. milk, bread, chicken ..."
          />
        </div>
      </div>

      {/* Search Results */}
      {debouncedSearch.length >= 2 && (
        <>
          {searchLoading ? (
            <Skeleton className="h-64" />
          ) : searchResults && searchResults.length > 0 ? (
            <div className="space-y-6">
              <p className="text-sm text-muted-foreground">
                Found {searchResults.length} products matching &quot;{debouncedSearch}&quot;:{" "}
                {Object.entries(storeCounts)
                  .map(([store, count]) => `${store} (${count})`)
                  .join(", ")}
              </p>

              <PriceResultsTable results={searchResults} />

              <h3 className="text-lg font-semibold">
                Average price for &quot;{debouncedSearch}&quot; by store
              </h3>
              <SearchAvgBarChart results={searchResults} />

              <BestDealsList results={searchResults} />
            </div>
          ) : (
            <p className="text-muted-foreground">
              No products found for &quot;{debouncedSearch}&quot;.
            </p>
          )}
        </>
      )}

      {!debouncedSearch && (
        <p className="text-muted-foreground">
          Search for a product above or click a popular category to compare
          prices across stores.
        </p>
      )}
    </div>
  );
}
