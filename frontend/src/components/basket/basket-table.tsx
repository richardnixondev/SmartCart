"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";

export interface BasketItem {
  product_id: number;
  product_name: string;
  quantity: number;
}

interface BasketTableProps {
  items: BasketItem[];
  onRemove: (index: number) => void;
}

export function BasketTable({ items, onRemove }: BasketTableProps) {
  if (items.length === 0) {
    return (
      <p className="text-muted-foreground">
        Your basket is empty. Search and add products above.
      </p>
    );
  }

  return (
    <div className="rounded-md border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Product</TableHead>
            <TableHead className="w-20 text-center">Qty</TableHead>
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item, idx) => (
            <TableRow key={`${item.product_id}-${idx}`}>
              <TableCell className="font-medium">{item.product_name}</TableCell>
              <TableCell className="text-center">{item.quantity}</TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onRemove(idx)}
                  className="h-8 w-8 text-destructive hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
