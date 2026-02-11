"use client";

import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchProducts, compareBasket } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { useDebounce } from "@/hooks/use-debounce";
import { PageHeader } from "@/components/layout/page-header";
import { ProductSearchInput } from "@/components/products/product-search-input";
import { ProductSelect } from "@/components/products/product-select";
import { BasketTable, type BasketItem } from "@/components/basket/basket-table";
import { StoreTotalCard } from "@/components/basket/store-total-card";
import { BasketComparisonBarChart } from "@/components/charts/basket-comparison-bar-chart";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ShoppingCart, Trash2 } from "lucide-react";
import type { BasketCompareOut } from "@/lib/types";

const STORAGE_KEY = "smartcart-basket";

function loadBasket(): BasketItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveBasket(items: BasketItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export default function BasketComparePage() {
  const [basket, setBasket] = useState<BasketItem[]>([]);
  const [search, setSearch] = useState("");
  const [selectedProductId, setSelectedProductId] = useState<string>();
  const [quantity, setQuantity] = useState(1);
  const debouncedSearch = useDebounce(search);

  // Load basket from localStorage on mount
  useEffect(() => {
    setBasket(loadBasket());
  }, []);

  // Persist basket changes
  const updateBasket = useCallback((items: BasketItem[]) => {
    setBasket(items);
    saveBasket(items);
  }, []);

  // Search products
  const { data: productsData } = useQuery({
    queryKey: queryKeys.products({ search: debouncedSearch, limit: 30 }),
    queryFn: () => fetchProducts({ search: debouncedSearch, limit: 30 }),
    staleTime: staleTimes.products,
    enabled: debouncedSearch.length >= 2,
  });

  const products = productsData?.items ?? [];

  // Compare mutation
  const compareMutation = useMutation({
    mutationFn: () =>
      compareBasket({
        name: "My Basket",
        items: basket.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
        })),
      }),
  });

  const handleAdd = () => {
    if (!selectedProductId) return;
    const product = products.find((p) => String(p.id) === selectedProductId);
    if (!product) return;

    const newBasket = [
      ...basket,
      {
        product_id: product.id,
        product_name: product.name,
        quantity,
      },
    ];
    updateBasket(newBasket);
    setSelectedProductId(undefined);
    setQuantity(1);
  };

  const handleRemove = (index: number) => {
    const newBasket = basket.filter((_, i) => i !== index);
    updateBasket(newBasket);
  };

  const handleClear = () => {
    updateBasket([]);
    compareMutation.reset();
  };

  const result: BasketCompareOut | undefined = compareMutation.data;
  const activeStores = (result?.stores ?? []).filter(
    (s) => s.items_found > 0
  );
  const sortedStores = [...activeStores].sort(
    (a, b) => Number(a.total) - Number(b.total)
  );
  const cheapestTotal =
    sortedStores.length > 0 ? Number(sortedStores[0].total) : 0;

  return (
    <div>
      <PageHeader
        title="Basket Compare"
        subtitle="Build a shopping list, then compare the total cost at each store."
      />

      {/* Add Items */}
      <h2 className="text-lg font-semibold mb-3">Add Items to Basket</h2>
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_200px_80px_auto] gap-3 items-end mb-6">
        <ProductSearchInput
          value={search}
          onChange={setSearch}
          placeholder="e.g. milk, bread, chicken ..."
        />
        {products.length > 0 && (
          <ProductSelect
            products={products}
            value={selectedProductId}
            onChange={setSelectedProductId}
          />
        )}
        <div>
          <label className="text-xs text-muted-foreground">Qty</label>
          <Input
            type="number"
            min={1}
            max={99}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value) || 1)}
          />
        </div>
        <Button onClick={handleAdd} disabled={!selectedProductId}>
          Add to basket
        </Button>
      </div>

      <Separator className="mb-6" />

      {/* Basket */}
      <h2 className="text-lg font-semibold mb-3">Your Basket</h2>
      <BasketTable items={basket} onRemove={handleRemove} />

      {basket.length > 0 && (
        <div className="flex gap-3 mt-4">
          <Button
            onClick={() => compareMutation.mutate()}
            disabled={compareMutation.isPending}
            className="flex-1"
          >
            <ShoppingCart className="h-4 w-4 mr-2" />
            {compareMutation.isPending ? "Comparing..." : "Compare Basket"}
          </Button>
          <Button variant="outline" onClick={handleClear}>
            <Trash2 className="h-4 w-4 mr-2" />
            Clear Basket
          </Button>
        </div>
      )}

      {/* Error */}
      {compareMutation.isError && (
        <p className="text-destructive mt-4">
          Could not compare your basket. Make sure the API is running.
        </p>
      )}

      {/* Results */}
      {result && sortedStores.length > 0 && (
        <>
          <Separator className="my-6" />
          <h2 className="text-lg font-semibold mb-3">Comparison Results</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
            {sortedStores.map((st) => (
              <StoreTotalCard
                key={st.store.id}
                storeTotal={st}
                cheapestTotal={cheapestTotal}
                isCheapest={Number(st.total) === cheapestTotal}
              />
            ))}
          </div>

          <BasketComparisonBarChart stores={sortedStores} />
        </>
      )}

      {result && sortedStores.length === 0 && (
        <p className="text-muted-foreground mt-6">
          None of the stores carry these products.
        </p>
      )}

      {compareMutation.isPending && (
        <div className="mt-6">
          <Skeleton className="h-48" />
        </div>
      )}
    </div>
  );
}
