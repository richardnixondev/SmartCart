"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { mergeProducts } from "@/lib/api";
import type { AdminProductOut } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

interface MergeDialogProps {
  products: AdminProductOut[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onMerged: () => void;
}

export function MergeDialog({
  products,
  open,
  onOpenChange,
  onMerged,
}: MergeDialogProps) {
  const queryClient = useQueryClient();
  const [targetId, setTargetId] = useState<string>(String(products[0]?.id ?? ""));

  const mutation = useMutation({
    mutationFn: () =>
      mergeProducts({
        product_ids: products.map((p) => p.id),
        target_id: Number(targetId),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-unmatched"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
      onOpenChange(false);
      onMerged();
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Merge {products.length} Products</DialogTitle>
          <DialogDescription>
            All store products will be moved to the target product. The other
            products will be deleted.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Target product (will be kept)</Label>
            <Select value={targetId} onValueChange={setTargetId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {products.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    #{p.id} — {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Products to merge</Label>
            <div className="rounded-md border divide-y max-h-60 overflow-y-auto">
              {products.map((p) => {
                const sp = p.store_products[0];
                const isTarget = String(p.id) === targetId;
                return (
                  <div
                    key={p.id}
                    className="flex items-center justify-between px-3 py-2 text-sm"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {isTarget && <Badge>Target</Badge>}
                      <span className={isTarget ? "font-medium" : ""}>{p.name}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {sp && (
                        <>
                          <Badge variant="outline">{sp.store.name}</Badge>
                          <span className="text-muted-foreground">
                            {formatCurrency(sp.promo_price ?? sp.latest_price)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {mutation.isError && (
          <p className="text-sm text-destructive">
            Merge failed. Please try again.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "Merging..." : "Merge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
