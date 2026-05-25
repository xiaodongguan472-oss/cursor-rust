import React, { useState, memo } from "react";
import type { AggregatedUsageData } from "../types/usage";
import { UsageDetailsModal } from "./UsageDetailsModal";

interface AggregatedUsageDisplayProps {
  aggregatedUsage: AggregatedUsageData;
  title?: string;
  showTitle?: boolean;
  className?: string;
  variant?: "detailed" | "compact";
  token?: string; // Token for fetching detailed usage data
  showDetailsButton?: boolean; // Whether to show the "查看明细" button
}

export const AggregatedUsageDisplay: React.FC<AggregatedUsageDisplayProps> = memo(({
  aggregatedUsage,
  title = "📊 聚合用量数据",
  showTitle = true,
  className = "",
  variant = "detailed",
  token,
  showDetailsButton = false,
}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const formatNumber = (num: string | number): string => {
    const numVal = typeof num === "string" ? parseInt(num) : num;
    return new Intl.NumberFormat().format(numVal);
  };

  const formatCurrency = (cents: number): string => {
    return `$${(cents / 100).toFixed(2)}`;
  };

  const isCompact = variant === "compact";

  return (
    <div className={`space-y-4 ${className}`}>
      {showTitle && (
        <div className="flex items-center justify-between">
          <h4
            className={`font-medium text-gray-700 ${
              isCompact ? "text-sm" : "text-md"
            }`}
          >
            {title}
          </h4>
          {showDetailsButton && token && (
            <button
              onClick={() => setIsModalOpen(true)}
              className="inline-flex items-center px-3 py-1 text-sm font-medium text-blue-700 bg-blue-100 border border-transparent rounded hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              📋 查看明细
            </button>
          )}
        </div>
      )}

      {/* Summary Cards */}
      <div
        className={`grid gap-4 ${
          isCompact
            ? "grid-cols-2 md:grid-cols-4"
            : "grid-cols-2 md:grid-cols-4"
        }`}
      >
        <div className={`rounded-lg bg-blue-50 ${isCompact ? "p-2" : "p-3"}`}>
          <div
            className={`font-medium tracking-wide text-blue-600 uppercase ${
              isCompact ? "text-xs" : "text-xs"
            }`}
          >
            总输入Token
          </div>
          <div
            className={`mt-1 font-semibold text-blue-900 ${
              isCompact ? "text-md" : "text-lg"
            }`}
          >
            {formatNumber(aggregatedUsage.total_input_tokens)}
          </div>
        </div>

        <div className={`rounded-lg bg-green-50 ${isCompact ? "p-2" : "p-3"}`}>
          <div
            className={`font-medium tracking-wide text-green-600 uppercase ${
              isCompact ? "text-xs" : "text-xs"
            }`}
          >
            总输出Token
          </div>
          <div
            className={`mt-1 font-semibold text-green-900 ${
              isCompact ? "text-md" : "text-lg"
            }`}
          >
            {formatNumber(aggregatedUsage.total_output_tokens)}
          </div>
        </div>

        <div className={`rounded-lg bg-purple-50 ${isCompact ? "p-2" : "p-3"}`}>
          <div
            className={`font-medium tracking-wide text-purple-600 uppercase ${
              isCompact ? "text-xs" : "text-xs"
            }`}
          >
            缓存读取Token
          </div>
          <div
            className={`mt-1 font-semibold text-purple-900 ${
              isCompact ? "text-md" : "text-lg"
            }`}
          >
            {formatNumber(aggregatedUsage.total_cache_read_tokens)}
          </div>
        </div>

        <div className={`rounded-lg bg-yellow-50 ${isCompact ? "p-2" : "p-3"}`}>
          <div
            className={`font-medium tracking-wide text-yellow-600 uppercase ${
              isCompact ? "text-xs" : "text-xs"
            }`}
          >
            总费用
          </div>
          <div
            className={`mt-1 font-semibold text-yellow-900 ${
              isCompact ? "text-md" : "text-lg"
            }`}
          >
            {formatCurrency(aggregatedUsage.total_cost_cents)}
          </div>
        </div>
      </div>


      {/* Usage Details Modal */}
      {token && (
        <UsageDetailsModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          token={token}
        />
      )}
    </div>
  );
}, (prevProps, nextProps) => {
  // 自定义比较函数：只有聚合数据变化时才重新渲染
  return (
    JSON.stringify(prevProps.aggregatedUsage) === JSON.stringify(nextProps.aggregatedUsage) &&
    prevProps.title === nextProps.title &&
    prevProps.showTitle === nextProps.showTitle &&
    prevProps.variant === nextProps.variant &&
    prevProps.showDetailsButton === nextProps.showDetailsButton
  );
});

AggregatedUsageDisplay.displayName = "AggregatedUsageDisplay";
