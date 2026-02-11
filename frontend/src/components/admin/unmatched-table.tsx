"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchUnmatched } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { useDebounce } from "@/hooks/use-debounce";
import { formatCurrency } from "@/lib/utils";
import type { AdminProductOut } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronDown, ChevronRight, Pencil, Merge } from "lucide-react";
import { StoreProductsPanel } from "./store-products-panel";
import { ProductEditDialog } from "./product-edit-dialog";
import { MergeDialog } from "./merge-dialog";

export function UnmatchedTable() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editProduct, setEditProduct] = useState<AdminProductOut | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const debouncedSearch = useDebounce(search);
  const limit = 30;

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.adminUnmatched({
      search: debouncedSearch || undefined,
      page,
    }),
    queryFn: () =>
      fetchUnmatched({
        search: debouncedSearch || undefined,
        page,
        limit,
      }),
    staleTime: staleTimes.adminUnmatched,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / limit);

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (items.every((p) => selected.has(p.id))) {
      setSelected((prev) => {
        const next = new Set(prev);
        items.forEach((p) => next.delete(p.id));
        return next;
      });
    } else {
      setSelected((prev) => {
        const next = new Set(prev);
        items.forEach((p) => next.add(p.id));
        return next;
      });
    }
  }

  const selectedProducts = items.filter((p) => selected.has(p.id));

  return (
    <div className="space-y-4">
      {/* Search */}
      <Input
        placeholder="Search products..."
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
        className="max-w-sm"
      />

      {/* Table */}
      {isLoading ? (
        <Skeleton className="h-96" />
      ) : items.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center">
          {debouncedSearch
            ? "No unmatched products found for this search."
            : "No unmatched singleton products found."}
        </p>
      ) : (
        <>
          <div className="rounded-md border overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={
                        items.length > 0 &&
                        items.every((p) => selected.has(p.id))
                      }
                      onCheckedChange={toggleSelectAll}
                    />
                  </TableHead>
                  <TableHead className="w-10" />
                  <TableHead>Name</TableHead>
                  <TableHead>Brand</TableHead>
                  <TableHead>EAN</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Store</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((product) => {
                  const sp = product.store_products[0];
                  const isExpanded = expandedId === product.id;
                  return (
                    <TableRow key={product.id} className="group" data-expanded={isExpanded || undefined}>
                      <TableCell>
                        <Checkbox
                          checked={selected.has(product.id)}
                          onCheckedChange={() => toggleSelect(product.id)}
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0"
                          onClick={() =>
                            setExpandedId(isExpanded ? null : product.id)
                          }
                        >
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </Button>
                      </TableCell>
                      <TableCell className="font-medium max-w-[200px] truncate">
                        {product.name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {product.brand ?? "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {product.ean ?? "—"}
                      </TableCell>
                      <TableCell>
                        {product.unit && product.unit_size
                          ? `${product.unit_size} ${product.unit}`
                          : "—"}
                      </TableCell>
                      <TableCell>
                        {sp ? (
                          <Badge variant="outline">{sp.store.name}</Badge>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {sp
                          ? formatCurrency(sp.promo_price ?? sp.latest_price)
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0"
                          onClick={() => setEditProduct(product)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {/* Expanded panel */}
          {expandedId && (
            <div className="rounded-md border p-4 bg-muted/30">
              <StoreProductsPanel
                productId={expandedId}
                productName={
                  items.find((p) => p.id === expandedId)?.name ?? ""
                }
              />
            </div>
          )}

          {/* Pagination */}
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {total} unmatched product{total !== 1 && "s"}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="flex items-center px-2 text-muted-foreground">
                {page} / {totalPages || 1}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Floating merge bar */}
      {selected.size >= 2 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
          <Button
            size="lg"
            className="shadow-lg gap-2"
            onClick={() => setMergeOpen(true)}
          >
            <Merge className="h-4 w-4" />
            Merge {selected.size} products
          </Button>
        </div>
      )}

      {/* Edit dialog */}
      {editProduct && (
        <ProductEditDialog
          product={editProduct}
          open={!!editProduct}
          onOpenChange={(open) => {
            if (!open) setEditProduct(null);
          }}
        />
      )}

      {/* Merge dialog */}
      {mergeOpen && selectedProducts.length >= 2 && (
        <MergeDialog
          products={selectedProducts}
          open={mergeOpen}
          onOpenChange={setMergeOpen}
          onMerged={() => setSelected(new Set())}
        />
      )}
    </div>
  );
}
