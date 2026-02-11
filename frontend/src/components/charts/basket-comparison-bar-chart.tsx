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
import type { BasketStoreTotal } from "@/lib/types";

interface BasketComparisonBarChartProps {
  stores: BasketStoreTotal[];
}

export function BasketComparisonBarChart({
  stores,
}: BasketComparisonBarChartProps) {
  const sorted = [...stores].sort(
    (a, b) => Number(a.total) - Number(b.total)
  );
  const minTotal = sorted.length > 0 ? Number(sorted[0].total) : 0;

  const data = sorted.map((s) => ({
    store: s.store.name,
    total: Number(s.total),
    isCheapest: Number(s.total) === minTotal,
  }));

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <XAxis dataKey="store" tick={{ fontSize: 12 }} />
        <YAxis
          tickFormatter={(v) => `€${Number(v).toFixed(2)}`}
          tick={{ fontSize: 11 }}
        />
        <Tooltip
          formatter={(value) => [formatCurrency(Number(value)), "Total"]}
        />
        <Bar dataKey="total" radius={[4, 4, 0, 0]}>
          <LabelList
            dataKey="total"
            position="top"
            formatter={(v) => formatCurrency(Number(v))}
            style={{ fontSize: 11 }}
          />
          {data.map((entry) => (
            <Cell
              key={entry.store}
              fill={getStoreColor(entry.store)}
              stroke={entry.isCheapest ? "gold" : "transparent"}
              strokeWidth={entry.isCheapest ? 3 : 0}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
