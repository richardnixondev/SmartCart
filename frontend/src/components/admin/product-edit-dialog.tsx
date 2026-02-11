"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProduct } from "@/lib/api";
import type { AdminProductOut, ProductUpdateIn } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ProductEditDialogProps {
  product: AdminProductOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProductEditDialog({
  product,
  open,
  onOpenChange,
}: ProductEditDialogProps) {
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    name: product.name,
    brand: product.brand ?? "",
    ean: product.ean ?? "",
    unit: product.unit ?? "",
    unit_size: product.unit_size?.toString() ?? "",
    image_url: product.image_url ?? "",
  });

  const mutation = useMutation({
    mutationFn: (data: ProductUpdateIn) => updateProduct(product.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-unmatched"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
      onOpenChange(false);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const data: ProductUpdateIn = {};
    if (form.name !== product.name) data.name = form.name;
    if (form.brand !== (product.brand ?? ""))
      data.brand = form.brand || null;
    if (form.ean !== (product.ean ?? "")) data.ean = form.ean || null;
    if (form.unit !== (product.unit ?? "")) data.unit = form.unit || null;
    if (form.unit_size !== (product.unit_size?.toString() ?? ""))
      data.unit_size = form.unit_size ? Number(form.unit_size) : null;
    if (form.image_url !== (product.image_url ?? ""))
      data.image_url = form.image_url || null;

    if (Object.keys(data).length === 0) {
      onOpenChange(false);
      return;
    }
    mutation.mutate(data);
  }

  function handleChange(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Product</DialogTitle>
          <DialogDescription>
            Update product metadata. Only changed fields will be saved.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={form.name}
              onChange={(e) => handleChange("name", e.target.value)}
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="brand">Brand</Label>
              <Input
                id="brand"
                value={form.brand}
                onChange={(e) => handleChange("brand", e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ean">EAN</Label>
              <Input
                id="ean"
                value={form.ean}
                onChange={(e) => handleChange("ean", e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="unit">Unit</Label>
              <Input
                id="unit"
                value={form.unit}
                onChange={(e) => handleChange("unit", e.target.value)}
                placeholder="e.g. L, kg, ml"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="unit_size">Unit Size</Label>
              <Input
                id="unit_size"
                type="number"
                step="any"
                value={form.unit_size}
                onChange={(e) => handleChange("unit_size", e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="image_url">Image URL</Label>
            <Input
              id="image_url"
              value={form.image_url}
              onChange={(e) => handleChange("image_url", e.target.value)}
            />
          </div>
          {mutation.isError && (
            <p className="text-sm text-destructive">
              Failed to update product. Please try again.
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
