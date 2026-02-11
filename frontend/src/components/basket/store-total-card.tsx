"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatCurrency } from "@/lib/utils";
import { getStoreColor } from "@/lib/store-colors";
import type { BasketStoreTotal } from "@/lib/types";

interface StoreTotalCardProps {
  storeTotal: BasketStoreTotal;
  cheapestTotal: number;
  isCheapest: boolean;
}

export function StoreTotalCard({
  storeTotal,
  cheapestTotal,
  isCheapest,
}: StoreTotalCardProps) {
  const delta = Number(storeTotal.total) - cheapestTotal;
  const storeColor = getStoreColor(storeTotal.store.name);

  return (
    <Card
      className={isCheapest ? "ring-2 ring-yellow-400" : ""}
      style={{ borderTop: `4px solid ${storeColor}` }}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{storeTotal.store.name}</CardTitle>
          {isCheapest && (
            <Badge className="bg-yellow-400 text-yellow-900 hover:bg-yellow-400">
              Cheapest
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {formatCurrency(storeTotal.total)}
        </div>
        {delta > 0 ? (
          <p className="text-sm text-destructive mt-1">
            +{formatCurrency(delta)} more
          </p>
        ) : (
          <p className="text-sm text-green-600 mt-1">Best price</p>
        )}
        <p className="text-xs text-muted-foreground mt-2">
          {storeTotal.items_found} found, {storeTotal.items_missing} missing
        </p>
      </CardContent>
    </Card>
  );
}
