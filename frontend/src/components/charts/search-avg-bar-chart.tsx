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
import type { SearchPriceResult } from "@/lib/types";

interface SearchAvgBarChartProps {
  results: SearchPriceResult[];
}

export function SearchAvgBarChart({ results }: SearchAvgBarChartProps) {
  const storeMap = new Map<string, { total: number; count: number }>();
  for (const r of results) {
    const entry = storeMap.get(r.store) || { total: 0, count: 0 };
    entry.total += r.effective_price;
    entry.count += 1;
    storeMap.set(r.store, entry);
  }

  const data = Array.from(storeMap.entries())
    .map(([store, { total, count }]) => ({
      store,
      avg: total / count,
    }))
    .sort((a, b) => a.avg - b.avg);

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <XAxis dataKey="store" tick={{ fontSize: 12 }} />
        <YAxis
          tickFormatter={(v) => `€${Number(v).toFixed(2)}`}
          tick={{ fontSize: 12 }}
        />
        <Tooltip
          formatter={(value) => [formatCurrency(Number(value)), "Avg Price"]}
        />
        <Bar dataKey="avg" radius={[4, 4, 0, 0]}>
          <LabelList
            dataKey="avg"
            position="top"
            formatter={(v) => formatCurrency(Number(v))}
            style={{ fontSize: 11 }}
          />
          {data.map((entry) => (
            <Cell key={entry.store} fill={getStoreColor(entry.store)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
