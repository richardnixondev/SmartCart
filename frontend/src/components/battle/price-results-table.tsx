"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getStoreColor } from "@/lib/store-colors";
import { formatCurrency } from "@/lib/utils";
import type { SearchPriceResult } from "@/lib/types";

interface PriceResultsTableProps {
  results: SearchPriceResult[];
}

export function PriceResultsTable({ results }: PriceResultsTableProps) {
  const sorted = [...results].sort(
    (a, b) => a.effective_price - b.effective_price
  );

  return (
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
          {sorted.map((item, idx) => (
            <TableRow
              key={`${item.store}-${item.product_name}-${idx}`}
              style={{ borderLeft: `4px solid ${getStoreColor(item.store)}` }}
            >
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
  );
}
