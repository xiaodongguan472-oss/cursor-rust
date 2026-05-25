import React, { useMemo, memo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { HistorySnapshot } from "../services/configService";
import { useTheme } from "../context/ThemeContext";

interface UsageChartProps {
  historySnapshots?: HistorySnapshot[];
  className?: string;
}

// 颜色方案：为不同模型分配不同颜色
const MODEL_COLORS = [
  "#3b82f6", // blue
  "#10b981", // green
  "#f59e0b", // amber
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#f97316", // orange
  "#6366f1", // indigo
];

export const UsageChart: React.FC<UsageChartProps> = memo(({
  historySnapshots = [],
  className = "",
}) => {
  const { config } = useTheme(); // 获取主题配置

  // 格式化时间戳为可读格式
  const formatTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${month}-${day} ${hours}:${minutes}`;
  };

  // Note: formatCost function removed as it's handled by Tooltip formatter inline

  // 处理图表数据
  const chartData = useMemo(() => {
    if (!historySnapshots || historySnapshots.length === 0) {
      return { data: [], modelNames: [] };
    }

    // 提取所有模型名称
    const modelNamesSet = new Set<string>();
    historySnapshots.forEach((snapshot) => {
      Object.keys(snapshot.models || {}).forEach((modelName) => {
        modelNamesSet.add(modelName);
      });
    });
    const modelNames = Array.from(modelNamesSet);

    // 构建图表数据
    const data = historySnapshots.map((snapshot) => {
      const dataPoint: any = {
        timestamp: snapshot.timestamp,
        time: formatTimestamp(snapshot.timestamp),
        totalCost: snapshot.total_cost / 100, // 转为美元
      };

      // 添加各模型费用
      modelNames.forEach((modelName) => {
        dataPoint[modelName] = (snapshot.models[modelName] || 0) / 100; // 转为美元
      });

      return dataPoint;
    });

    return { data, modelNames };
  }, [historySnapshots]);

  // 如果没有数据，不显示任何内容
  if (!historySnapshots || historySnapshots.length === 0) {
    return null;
  }

  // 检测是否开启了自定义背景或透明主题
  const hasCustomBackground = !!(config.customBackground?.enabled && config.customBackground?.imageUrl);
  const isTranslucentTheme = config.mode === 'transparent' || hasCustomBackground;

  return (
    <div
      className={`rounded-lg border p-4 ${className}`}
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderColor: 'var(--border-primary)',
        backdropFilter: isTranslucentTheme ? 'blur(10px)' : 'none',
        WebkitBackdropFilter: isTranslucentTheme ? 'blur(10px)' : 'none',
        transition: 'all 0.3s ease',
      }}
    >
      <h4
        className="mb-4 text-md font-medium"
        style={{
          color: 'var(--text-primary)',
        }}
      >
        📈 费用趋势图
      </h4>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart
          data={chartData.data}
          margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          style={{
            backgroundColor: 'transparent',
          }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={isTranslucentTheme ? 'rgba(0, 0, 0, 0.2)' : undefined}
          />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 12 }}
            angle={-15}
            textAnchor="end"
            height={60}
          />
          <YAxis
            tick={{ fontSize: 12 }}
            label={{ value: "费用 ($)", angle: -90, position: "insideLeft" }}
          />
          <Tooltip
            formatter={(value: any) => `$${Number(value).toFixed(2)}`}
            labelStyle={{ fontWeight: 'bold', color: 'var(--text-primary)' }}
            contentStyle={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border-primary)', color: 'var(--text-primary)' }}
            itemStyle={{ color: 'var(--text-secondary)' }}
            wrapperStyle={{ zIndex: 1000 }}
          />
          <Legend wrapperStyle={{ paddingTop: "10px" }} />

          {/* 总费用折线 */}
          <Line
            type="monotone"
            dataKey="totalCost"
            name="总费用"
            stroke="#f59e0b"
            strokeWidth={3}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />

          {/* 各模型费用折线 */}
          {chartData.modelNames.map((modelName, index) => (
            <Line
              key={modelName}
              type="monotone"
              dataKey={modelName}
              name={modelName}
              stroke={MODEL_COLORS[index % MODEL_COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p
        className="mt-2 text-xs text-center"
        style={{
          color: 'var(--text-secondary)',
        }}
      >
        * 显示最近 {chartData.data.length} 次刷新的费用变化趋势
      </p>
    </div>
  );
});

UsageChart.displayName = "UsageChart";
