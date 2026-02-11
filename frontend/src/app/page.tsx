"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStats, fetchBattle, fetchProducts } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { useDebounce } from "@/hooks/use-debounce";
import { formatCurrency, formatNumber } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { KpiCard } from "@/components/layout/kpi-card";
import { BattlePieChart } from "@/components/charts/battle-pie-chart";
import { ProductSearchInput } from "@/components/products/product-search-input";
import { ProductTable } from "@/components/products/product-table";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Package, Store, Database } from "lucide-react";
import { getStoreColor } from "@/lib/store-colors";

const PAGE_SIZE = 25;

export default function OverviewPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebounce(search);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: queryKeys.stats,
    queryFn: fetchStats,
    staleTime: staleTimes.stats,
  });

  const { data: battle } = useQuery({
    queryKey: queryKeys.battle(),
    queryFn: () => fetchBattle(),
    staleTime: staleTimes.battle,
  });

  const { data: products, isLoading: productsLoading } = useQuery({
    queryKey: queryKeys.products({ page, limit: PAGE_SIZE, search: debouncedSearch }),
    queryFn: () =>
      fetchProducts({ page, limit: PAGE_SIZE, search: debouncedSearch || undefined }),
    staleTime: staleTimes.products,
  });

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  const battleResults = battle?.results ?? [];
  const storesWithWins = battleResults.filter((r) => r.wins > 0);

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle="Key performance indicators and product catalogue."
      />

      {/* KPI Cards */}
      {statsLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : stats ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <KpiCard
            title="Products Tracked"
            value={formatNumber(stats.total_products)}
            icon={<Package className="h-4 w-4" />}
          />
          <KpiCard
            title="Stores"
            value={formatNumber(stats.total_stores)}
            icon={<Store className="h-4 w-4" />}
          />
          <KpiCard
            title="Price Records"
            value={formatNumber(stats.total_price_records)}
            icon={<Database className="h-4 w-4" />}
          />
        </div>
      ) : (
        <p className="text-destructive mb-6">
          Unable to reach the SmartCart API. Please ensure the backend is running.
        </p>
      )}

      {/* Average Price by Store */}
      {stats && stats.avg_prices_by_store.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-3">Average Price by Store</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
            {stats.avg_prices_by_store.map((entry) => (
              <div
                key={entry.store.id}
                className="border-l-4 rounded-lg"
                style={{ borderLeftColor: getStoreColor(entry.store.name) }}
              >
                <KpiCard
                  title={entry.store.name}
                  value={formatCurrency(entry.avg_price)}
                />
              </div>
            ))}
          </div>
          <Separator className="mb-6" />
        </>
      )}

      {/* Cheapest Store Breakdown */}
      {storesWithWins.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-3">
            Cheapest Store Breakdown
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <BattlePieChart results={battleResults} />
            <div className="space-y-2">
              {battleResults
                .filter((r) => r.wins > 0 || Number(r.avg_price) > 0)
                .map((r) => (
                  <div
                    key={r.store.id}
                    className="flex items-center gap-2 text-sm"
                  >
                    <div
                      className="h-3 w-3 rounded-full shrink-0"
                      style={{ backgroundColor: getStoreColor(r.store.name) }}
                    />
                    <span className="font-medium">{r.store.name}:</span>
                    <span>
                      {r.wins} wins ({r.cheapest_pct.toFixed(1)}%) | avg{" "}
                      {formatCurrency(r.avg_price)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
          <Separator className="mb-6" />
        </>
      )}

      {/* Product Catalogue */}
      <h2 className="text-lg font-semibold mb-3">Product Catalogue</h2>
      <div className="mb-4 max-w-md">
        <ProductSearchInput
          value={search}
          onChange={handleSearchChange}
          placeholder="e.g. milk, bread, chicken ..."
        />
      </div>

      {productsLoading ? (
        <Skeleton className="h-64" />
      ) : products && products.items.length > 0 ? (
        <ProductTable
          products={products.items}
          total={products.total}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
        />
      ) : (
        <p className="text-muted-foreground">
          {search
            ? "No products found for your search."
            : "No products in the database yet. Run a scraper first!"}
        </p>
      )}
    </div>
  );
}
