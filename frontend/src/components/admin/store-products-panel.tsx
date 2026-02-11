"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdminStoreProducts, unlinkStoreProduct } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { formatCurrency } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Unlink } from "lucide-react";

interface StoreProductsPanelProps {
  productId: number;
  productName: string;
}

export function StoreProductsPanel({
  productId,
  productName,
}: StoreProductsPanelProps) {
  const queryClient = useQueryClient();

  const { data: storeProducts, isLoading } = useQuery({
    queryKey: queryKeys.adminStoreProducts(productId),
    queryFn: () => fetchAdminStoreProducts(productId),
    staleTime: staleTimes.adminStoreProducts,
  });

  const unlinkMutation = useMutation({
    mutationFn: (storeProductId: number) =>
      unlinkStoreProduct(productId, storeProductId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-store-products"] });
      queryClient.invalidateQueries({ queryKey: ["admin-unmatched"] });
    },
  });

  if (isLoading) {
    return <Skeleton className="h-20" />;
  }

  if (!storeProducts || storeProducts.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-2">
        No store products found.
      </p>
    );
  }

  const canUnlink = storeProducts.length > 1;

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-muted-foreground">
        Store products for &quot;{productName}&quot;
      </p>
      <div className="grid gap-2">
        {storeProducts.map((sp) => (
          <div
            key={sp.id}
            className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
          >
            <div className="flex items-center gap-3 min-w-0">
              <Badge variant="outline">{sp.store.name}</Badge>
              <span className="truncate">{sp.store_name}</span>
              {sp.store_sku && (
                <span className="text-muted-foreground text-xs">
                  SKU: {sp.store_sku}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <span className="font-medium">
                {formatCurrency(sp.promo_price ?? sp.latest_price)}
              </span>
              {!sp.is_active && (
                <Badge variant="secondary">Inactive</Badge>
              )}
              {canUnlink && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={unlinkMutation.isPending}
                    >
                      <Unlink className="h-3.5 w-3.5 mr-1" />
                      Unlink
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Unlink store product?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will remove &quot;{sp.store_name}&quot; ({sp.store.name})
                        from this product and create a new standalone product for it.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => unlinkMutation.mutate(sp.id)}
                      >
                        Unlink
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
