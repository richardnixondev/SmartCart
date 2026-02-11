"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from "recharts";
import { getStoreColor } from "@/lib/store-colors";
import { formatCurrency } from "@/lib/utils";

interface StoreComparisonBarChartProps {
  data: { store_name: string; price: number }[];
}

export function StoreComparisonBarChart({
  data,
}: StoreComparisonBarChartProps) {
  const sorted = [...data].sort((a, b) => a.price - b.price);

  if (sorted.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={sorted} layout="vertical">
        <XAxis
          type="number"
          tickFormatter={(v) => `€${Number(v).toFixed(2)}`}
          tick={{ fontSize: 11 }}
        />
        <YAxis
          type="category"
          dataKey="store_name"
          width={100}
          tick={{ fontSize: 12 }}
        />
        <Tooltip
          formatter={(value) => [formatCurrency(Number(value)), "Price"]}
        />
        <Bar dataKey="price" radius={[0, 4, 4, 0]}>
          <LabelList
            dataKey="price"
            position="right"
            formatter={(v) => formatCurrency(Number(v))}
            style={{ fontSize: 11 }}
          />
          {sorted.map((entry) => (
            <Cell key={entry.store_name} fill={getStoreColor(entry.store_name)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
