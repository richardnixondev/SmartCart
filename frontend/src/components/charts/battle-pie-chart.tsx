"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { getStoreColor } from "@/lib/store-colors";
import { formatCurrency } from "@/lib/utils";
import type { BattleResult } from "@/lib/types";

interface BattlePieChartProps {
  results: BattleResult[];
}

export function BattlePieChart({ results }: BattlePieChartProps) {
  const data = results
    .filter((r) => r.wins > 0)
    .map((r) => ({
      name: r.store.name,
      value: r.wins,
      pct: r.cheapest_pct,
      avg: r.avg_price,
    }));

  if (data.length === 0) return null;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const renderLabel = (props: any) => {
    const { name, pct } = props;
    return `${name} ${Number(pct).toFixed(0)}%`;
  };

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          nameKey="name"
          label={renderLabel}
          labelLine={false}
        >
          {data.map((entry) => (
            <Cell key={entry.name} fill={getStoreColor(entry.name)} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value, name, props) => [
            `${value} wins (avg ${formatCurrency((props.payload as { avg: number }).avg)})`,
            name,
          ]}
        />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
