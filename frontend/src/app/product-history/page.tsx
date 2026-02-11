"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchProducts,
  fetchPriceHistory,
  fetchComparison,
  searchPrices,
} from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { useDebounce } from "@/hooks/use-debounce";
import { formatCurrency } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { ProductSearchInput } from "@/components/products/product-search-input";
import { ProductSelect } from "@/components/products/product-select";
import { PriceHistoryLineChart } from "@/components/charts/price-history-line-chart";
import { StoreComparisonBarChart } from "@/components/charts/store-comparison-bar-chart";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getStoreColor } from "@/lib/store-colors";

export default function ProductHistoryPage() {
  const [search, setSearch] = useState("");
  const [selectedProductId, setSelectedProductId] = useState<string>();
  const [days, setDays] = useState(90);
  const debouncedSearch = useDebounce(search);

  // Search for products
  const { data: productsData } = useQuery({
    queryKey: queryKeys.products({ search: debouncedSearch, limit: 50 }),
    queryFn: () => fetchProducts({ search: debouncedSearch, limit: 50 }),
    staleTime: staleTimes.products,
    enabled: debouncedSearch.length >= 2,
  });

  const products = productsData?.items ?? [];

  // Auto-select first product when search results change
  const productId = selectedProductId ? Number(selectedProductId) : undefined;

  // Price history
  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: queryKeys.priceHistory(productId!, days),
    queryFn: () => fetchPriceHistory(productId!, days),
    staleTime: staleTimes.priceHistory,
    enabled: !!productId,
  });

  // Comparison
  const { data: comparison } = useQuery({
    queryKey: queryKeys.comparison(productId!),
    queryFn: () => fetchComparison(productId!),
    staleTime: staleTimes.comparison,
    enabled: !!productId,
  });

  // Similar products
  const { data: similarResults } = useQuery({
    queryKey: queryKeys.searchPrices(debouncedSearch, 100),
    queryFn: () => searchPrices(debouncedSearch, 100),
    staleTime: staleTimes.searchPrices,
    enabled: debouncedSearch.length >= 2,
  });

  // Build bar chart data from comparison
  const barData = useMemo(() => {
    if (!comparison?.stores) return [];
    return comparison.stores
      .filter((sp) => sp.latest_price != null || sp.promo_price != null)
      .map((sp) => ({
        store_name: sp.store.name,
        price: Number(sp.promo_price ?? sp.latest_price),
      }));
  }, [comparison]);

  const sortedSimilar = useMemo(
    () =>
      [...(similarResults ?? [])].sort(
        (a, b) => a.effective_price - b.effective_price
      ),
    [similarResults]
  );

  return (
    <div>
      <PageHeader
        title="Product History"
        subtitle="Search for a product and explore its price history across stores."
      />

      {/* Search & Select */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        <ProductSearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setSelectedProductId(undefined);
          }}
          placeholder="Search for a product..."
        />
        {products.length > 0 && (
          <ProductSelect
            products={products}
            value={selectedProductId}
            onChange={setSelectedProductId}
          />
        )}
      </div>

      {/* Date range control */}
      {productId && (
        <div className="flex items-center gap-2 mb-6">
          <label className="text-sm text-muted-foreground">History days:</label>
          <Input
            type="number"
            min={1}
            max={365}
            value={days}
            onChange={(e) => setDays(Number(e.target.value) || 90)}
            className="w-24"
          />
        </div>
      )}

      {/* Empty states */}
      {!debouncedSearch && (
        <p className="text-muted-foreground">
          Enter a search term above to find products.
        </p>
      )}
      {debouncedSearch && products.length === 0 && (
        <p className="text-muted-foreground">
          No products found. Try a different search term.
        </p>
      )}

      {/* Price History Chart */}
      {productId && (
        <>
          <h2 className="text-lg font-semibold mb-3">Price History</h2>
          {historyLoading ? (
            <Skeleton className="h-80 mb-6" />
          ) : history && history.length > 0 ? (
            <div className="mb-6">
              <PriceHistoryLineChart history={history} />
            </div>
          ) : (
            <p className="text-muted-foreground mb-6">
              No price history available for this product.
            </p>
          )}

          <Separator className="mb-6" />

          {/* Current Prices Across Stores */}
          <h2 className="text-lg font-semibold mb-3">
            Current Prices Across Stores
          </h2>
          {comparison?.stores && comparison.stores.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <div className="rounded-md border overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Store</TableHead>
                      <TableHead className="text-right">Price</TableHead>
                      <TableHead>Promo</TableHead>
                      <TableHead className="text-right">Promo Price</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {comparison.stores.map((sp) => (
                      <TableRow
                        key={sp.store.id}
                        style={{
                          borderLeft: `4px solid ${getStoreColor(sp.store.name)}`,
                        }}
                      >
                        <TableCell className="font-medium">
                          {sp.store.name}
                        </TableCell>
                        <TableCell className="text-right">
                          {sp.latest_price != null
                            ? formatCurrency(sp.latest_price)
                            : "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {sp.promo_label || "—"}
                        </TableCell>
                        <TableCell className="text-right">
                          {sp.promo_price != null
                            ? formatCurrency(sp.promo_price)
                            : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {barData.length > 0 && (
                <StoreComparisonBarChart data={barData} />
              )}
            </div>
          ) : (
            <p className="text-muted-foreground mb-6">
              No comparison data available for this product.
            </p>
          )}

          <Separator className="mb-6" />
        </>
      )}

      {/* Similar Products */}
      {debouncedSearch && sortedSimilar.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-1">
            Similar Products Across Stores
          </h2>
          <p className="text-sm text-muted-foreground mb-3">
            Other products matching &quot;{debouncedSearch}&quot; across all stores.
          </p>
          <div className="rounded-md border overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Store</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Effective</TableHead>
                  <TableHead>Promo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedSimilar.map((item, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="font-medium">{item.store}</TableCell>
                    <TableCell>{item.product_name}</TableCell>
                    <TableCell className="text-right">
                      {formatCurrency(item.price)}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatCurrency(item.effective_price)}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {item.promo_label || ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}
