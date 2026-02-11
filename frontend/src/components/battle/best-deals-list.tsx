"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getStoreColor } from "@/lib/store-colors";
import { formatCurrency } from "@/lib/utils";
import type { SearchPriceResult } from "@/lib/types";

interface BestDealsListProps {
  results: SearchPriceResult[];
  limit?: number;
}

export function BestDealsList({ results, limit = 5 }: BestDealsListProps) {
  const sorted = [...results]
    .sort((a, b) => a.effective_price - b.effective_price)
    .slice(0, limit);

  if (sorted.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Best Deals</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {sorted.map((item, idx) => (
          <div key={idx} className="flex items-center gap-3">
            <div
              className="h-2 w-2 rounded-full shrink-0"
              style={{ backgroundColor: getStoreColor(item.store) }}
            />
            <div className="text-sm">
              <span className="font-bold">
                {formatCurrency(item.effective_price)}
              </span>
              {" - "}
              {item.product_name} @ {item.store}
              {item.promo_label && (
                <span className="text-muted-foreground">
                  {" "}
                  ({item.promo_label})
                </span>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
