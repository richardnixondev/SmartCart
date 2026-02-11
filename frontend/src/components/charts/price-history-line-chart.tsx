"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceDot,
} from "recharts";
import { getStoreColor } from "@/lib/store-colors";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { PriceHistoryOut } from "@/lib/types";

interface PriceHistoryLineChartProps {
  history: PriceHistoryOut[];
}

interface ChartPoint {
  date: string;
  timestamp: number;
  [store: string]: string | number | boolean;
}

interface PromoMarker {
  timestamp: number;
  store: string;
  price: number;
}

export function PriceHistoryLineChart({ history }: PriceHistoryLineChartProps) {
  const dateMap = new Map<string, Record<string, number>>();
  const promoMarkers: PromoMarker[] = [];

  for (const entry of history) {
    const storeName = entry.store.name;
    for (const pr of entry.prices) {
      const dateKey = pr.scraped_at.split("T")[0];
      const effective = pr.promo_price != null ? Number(pr.promo_price) : Number(pr.price);

      if (!dateMap.has(dateKey)) {
        dateMap.set(dateKey, {});
      }
      dateMap.get(dateKey)![storeName] = effective;

      if (pr.promo_label != null) {
        promoMarkers.push({
          timestamp: new Date(dateKey).getTime(),
          store: storeName,
          price: effective,
        });
      }
    }
  }

  const storeNames = [...new Set(history.map((h) => h.store.name))].sort();

  const data: ChartPoint[] = Array.from(dateMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, stores]) => ({
      date,
      timestamp: new Date(date).getTime(),
      ...stores,
    }));

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={350}>
      <LineChart data={data}>
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11 }}
          tickFormatter={(d) => formatDate(String(d))}
        />
        <YAxis
          tickFormatter={(v) => `€${Number(v).toFixed(2)}`}
          tick={{ fontSize: 11 }}
        />
        <Tooltip
          labelFormatter={(d) => formatDate(String(d))}
          formatter={(value, name) => [
            formatCurrency(Number(value)),
            String(name),
          ]}
        />
        <Legend />
        {storeNames.map((store) => (
          <Line
            key={store}
            type="monotone"
            dataKey={store}
            stroke={getStoreColor(store)}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
          />
        ))}
        {promoMarkers.map((m, idx) => (
          <ReferenceDot
            key={idx}
            x={data.find((d) => d.timestamp === m.timestamp)?.date ?? ""}
            y={m.price}
            r={6}
            fill="gold"
            stroke={getStoreColor(m.store)}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
