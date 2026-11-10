import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface TestingLineChartProps {
  data: { label: string; value: number }[];
  metricLabel: string;
  color: string;
}

export default function TestingLineChart({ data, metricLabel, color }: TestingLineChartProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 20, bottom: 8, left: 8 }}>
        <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
        <XAxis
          dataKey="label"
          tick={{ fill: '#6b7280', fontSize: 12 }}
          tickLine={false}
          axisLine={{ stroke: '#d1d5db' }}
        />
        <YAxis
          width={72}
          tick={{ fill: '#6b7280', fontSize: 12 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value: number) => value.toLocaleString('vi-VN', { maximumFractionDigits: 2 })}
        />
        <Tooltip
          formatter={(value) => [
            typeof value === 'number' ? value.toLocaleString('vi-VN', { maximumFractionDigits: 2 }) : value,
            metricLabel,
          ]}
          contentStyle={{ borderRadius: 0, borderColor: '#d1d5db' }}
        />
        <Line
          type="monotone"
          dataKey="value"
          name={metricLabel}
          stroke={color}
          strokeWidth={2}
          dot={{ r: 3, fill: color }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
