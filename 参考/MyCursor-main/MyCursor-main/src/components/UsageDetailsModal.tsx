import React, { useState, useEffect } from "react";
import type {
  UserAnalyticsData,
  FilteredUsageEventsData,
} from "../types/analytics";
import { AnalyticsService } from "../services/analyticsService";

interface UsageDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
}

export const UsageDetailsModal: React.FC<UsageDetailsModalProps> = ({
  isOpen,
  onClose,
  token,
}) => {
  const [activeTab, setActiveTab] = useState<"analytics" | "events">("events");
  const [analyticsData, setAnalyticsData] = useState<UserAnalyticsData | null>(
    null
  );
  const [eventsData, setEventsData] = useState<FilteredUsageEventsData | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  // 获取最近30天的时间范围
  const getDateRange = () => {
    const endDate = new Date();
    const startDate = new Date().getTime() - 30 * 24 * 60 * 60 * 1000;
    // startDate.setDate(startDate.getDate() - 7);
    console.log("startDate", startDate);
    console.log("endDate", endDate);

    return {
      startDate: AnalyticsService.dateToTimestamp(new Date(startDate)),
      endDate: AnalyticsService.dateToTimestamp(endDate),
    };
  };

  // 加载数据
  const loadData = async () => {
    if (!isOpen) return;

    console.log(
      `🔄 Loading data - Tab: ${activeTab}, Page: ${currentPage}, PageSize: ${pageSize}`
    );

    setLoading(true);
    setError(null);

    try {
      const { startDate, endDate } = getDateRange();

      if (activeTab === "analytics") {
        const result = await AnalyticsService.getUserAnalytics(
          token,
          0, // teamId
          0, // userId
          startDate,
          endDate
        );

        if (result.success && result.data) {
          setAnalyticsData(result.data);
        } else {
          setError(result.message);
        }
      } else {
        const result = await AnalyticsService.getUsageEvents(
          token,
          0, // teamId
          startDate,
          endDate,
          currentPage,
          pageSize
        );

        console.log(`📊 Usage events result:`, result);

        if (result.success && result.data) {
          console.log(`✅ Events data loaded successfully:`, result.data);
          setEventsData(result.data);
        } else {
          console.error(`❌ Events data loading failed:`, result.message);
          setError(result.message);
        }
      }
    } catch (err) {
      setError(`加载数据失败: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  // 当模态框打开或标签页切换时加载数据
  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, activeTab, currentPage]);

  // 格式化时间戳
  const formatTimestamp = (timestamp: string | null | undefined) => {
    if (!timestamp) {
      return "-";
    }
    try {
      const date = AnalyticsService.timestampToDate(timestamp);
      if (isNaN(date.getTime())) {
        return "-";
      }
      return date.toLocaleString("zh-CN");
    } catch (_error) {
      console.warn("Invalid timestamp:", timestamp);
      return "-";
    }
  };

  // 格式化日期（仅日期部分）
  const formatDate = (timestamp: string | null | undefined) => {
    if (!timestamp) {
      return "-";
    }
    try {
      const date = AnalyticsService.timestampToDate(timestamp);
      if (isNaN(date.getTime())) {
        return "-";
      }
      return date.toLocaleDateString("zh-CN");
    } catch (_error) {
      console.warn("Invalid date timestamp:", timestamp);
      return "-";
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
        {/* Backdrop */}
        <div
          className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75"
          onClick={onClose}
        />

        {/* Modal */}
        <div className="inline-block w-[95%] max-w-[750px] p-6 my-8 overflow-hidden text-left align-middle transition-all transform bg-white rounded-lg shadow-xl">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900">
              📊 使用详情 (最近30天)
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 focus:outline-none"
            >
              ✕
            </button>
          </div>

          {/* Tab Navigation */}
          <div className="mb-4 border-b border-gray-200">
            <nav className="flex -mb-px space-x-8">
              <button
                onClick={() => setActiveTab("events")}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === "events"
                    ? "border-blue-500 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                🔍 使用事件明细
              </button>
              <button
                onClick={() => setActiveTab("analytics")}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === "analytics"
                    ? "border-blue-500 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                📈 用户分析数据
              </button>
            </nav>
          </div>

          {/* Content */}
          <div className="overflow-y-auto max-h-96">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="inline-flex items-center">
                  <svg
                    className="w-4 h-4 mr-2 animate-spin"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  <span className="text-sm text-gray-500">加载数据中...</span>
                </div>
              </div>
            ) : error ? (
              <div className="p-4 border border-red-200 rounded-md bg-red-50">
                <p className="text-sm text-red-600">❌ {error}</p>
                <div className="mt-2 text-xs text-gray-600">
                  当前页码: {currentPage}, 页大小: {pageSize}
                  {eventsData && (
                    <span>, 总记录数: {eventsData.totalUsageEventsCount}</span>
                  )}
                </div>
                <button
                  onClick={loadData}
                  className="mt-2 text-sm text-red-700 underline hover:text-red-800"
                >
                  重试
                </button>
              </div>
            ) : activeTab === "events" && eventsData ? (
              <div>
                {/* Events Table */}
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-xs font-medium tracking-wider text-left text-gray-500 uppercase">
                          时间
                        </th>
                        <th className="px-3 py-2 text-xs font-medium tracking-wider text-left text-gray-500 uppercase">
                          模型
                        </th>
                        <th className="px-3 py-2 text-xs font-medium tracking-wider text-left text-gray-500 uppercase">
                          类型
                        </th>
                        <th className="px-3 py-2 text-xs font-medium tracking-wider text-left text-gray-500 uppercase">
                          Token用量
                        </th>
                        <th className="px-3 py-2 text-xs font-medium tracking-wider text-left text-gray-500 uppercase">
                          费用
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {(eventsData?.usageEventsDisplay || []).map(
                        (event, index) => (
                          <tr key={index} className="hover:bg-gray-50">
                            <td className="px-3 py-2 text-sm text-gray-900">
                              {formatTimestamp(event.timestamp)}
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              <span className="inline-flex px-2 py-1 text-xs font-medium text-blue-800 bg-blue-100 rounded-full">
                                {AnalyticsService.getModelDisplayName(
                                  event.model
                                )}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              <span
                                className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                  event.kind.includes("INCLUDED_IN_PRO")
                                    ? "bg-green-100 text-green-800"
                                    : event.kind.includes("ERRORED")
                                      ? "bg-red-100 text-red-800"
                                      : "bg-yellow-100 text-yellow-800"
                                }`}
                              >
                                {AnalyticsService.getEventKindDisplay(
                                  event.kind
                                )}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              {event.tokenUsage ? (
                                <div className="space-y-1">
                                  <div>
                                    输入:{" "}
                                    {AnalyticsService.formatNumber(
                                      event.tokenUsage.inputTokens
                                    )}
                                  </div>
                                  <div>
                                    输出:{" "}
                                    {AnalyticsService.formatNumber(
                                      event.tokenUsage.outputTokens
                                    )}
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    缓存:{" "}
                                    {AnalyticsService.formatNumber(
                                      event.tokenUsage.cacheReadTokens
                                    )}
                                  </div>
                                </div>
                              ) : (
                                <span className="text-gray-400">-</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              {event.tokenUsage?.totalCents !== undefined ? (
                                <span className="font-medium">
                                  {AnalyticsService.formatCents(
                                    event.tokenUsage.totalCents
                                  )}
                                </span>
                              ) : (
                                <span className="text-gray-400">
                                  {event.usageBasedCosts || "-"}
                                </span>
                              )}
                            </td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {eventsData && (
                  <div className="flex items-center justify-between px-2 mt-4">
                    <div className="text-sm text-gray-700">
                      显示 {(currentPage - 1) * pageSize + 1} -{" "}
                      {Math.min(
                        currentPage * pageSize,
                        eventsData.totalUsageEventsCount
                      )}
                      ，共 {eventsData.totalUsageEventsCount} 条记录
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={() =>
                          setCurrentPage(Math.max(1, currentPage - 1))
                        }
                        disabled={currentPage === 1}
                        className="px-3 py-1 text-sm border rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                      >
                        上一页
                      </button>
                      <span className="px-3 py-1 text-sm">
                        第 {currentPage} 页
                      </span>
                      <button
                        onClick={() => {
                          const nextPage = currentPage + 1;
                          const maxPage = Math.ceil(
                            eventsData.totalUsageEventsCount / pageSize
                          );
                          console.log(
                            `📄 Next page click: ${nextPage}, Max page: ${maxPage}`
                          );
                          if (nextPage <= maxPage) {
                            setCurrentPage(nextPage);
                          }
                        }}
                        disabled={
                          currentPage >=
                          Math.ceil(eventsData.totalUsageEventsCount / pageSize)
                        }
                        className="px-3 py-1 text-sm border rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                      >
                        下一页
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : activeTab === "analytics" && analyticsData ? (
              <div>
                {/* Analytics Summary */}
                <div className="p-4 mb-4 rounded-lg bg-gray-50">
                  <h4 className="mb-2 font-medium text-gray-900">
                    📊 总览信息
                  </h4>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-600">时间范围:</span>
                      <span className="ml-2 font-medium">
                        {analyticsData?.period
                          ? `${formatDate(
                              analyticsData.period.startDate
                            )} - ${formatDate(analyticsData.period.endDate)}`
                          : "-"}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-600">团队成员数:</span>
                      <span className="ml-2 font-medium">
                        {analyticsData?.totalMembersInTeam || 1}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Daily Metrics */}
                <div className="space-y-4">
                  <h4 className="font-medium text-gray-900">📈 每日指标</h4>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-xs font-medium text-left text-gray-500 uppercase">
                            日期
                          </th>
                          <th className="px-3 py-2 text-xs font-medium text-left text-gray-500 uppercase">
                            活跃用户
                          </th>
                          <th className="px-3 py-2 text-xs font-medium text-left text-gray-500 uppercase">
                            代码接受
                          </th>
                          <th className="px-3 py-2 text-xs font-medium text-left text-gray-500 uppercase">
                            请求数
                          </th>
                          <th className="px-3 py-2 text-xs font-medium text-left text-gray-500 uppercase">
                            模型使用
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {analyticsData?.dailyMetrics?.map((metric, index) => (
                          <tr key={index} className="hover:bg-gray-50">
                            <td className="px-3 py-2 text-sm text-gray-900">
                              {formatDate(metric.date)}
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              {metric.activeUsers ?? 0}
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              <div className="space-y-1">
                                {metric.acceptedLinesAdded && (
                                  <div className="text-green-600">
                                    +
                                    {AnalyticsService.formatNumber(
                                      metric.acceptedLinesAdded
                                    )}{" "}
                                    行
                                  </div>
                                )}
                                {metric.acceptedLinesDeleted && (
                                  <div className="text-red-600">
                                    -
                                    {AnalyticsService.formatNumber(
                                      metric.acceptedLinesDeleted
                                    )}{" "}
                                    行
                                  </div>
                                )}
                                {metric.totalAccepts && (
                                  <div className="text-xs text-gray-500">
                                    接受率: {metric.totalAccepts}/
                                    {metric.totalApplies || 0}
                                  </div>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              <div className="space-y-1">
                                {metric.composerRequests && (
                                  <div>
                                    编写:{" "}
                                    {AnalyticsService.formatNumber(
                                      metric.composerRequests
                                    )}
                                  </div>
                                )}
                                {metric.agentRequests && (
                                  <div>
                                    助手:{" "}
                                    {AnalyticsService.formatNumber(
                                      metric.agentRequests
                                    )}
                                  </div>
                                )}
                                {metric.subscriptionIncludedReqs && (
                                  <div className="text-xs text-gray-500">
                                    订阅:{" "}
                                    {AnalyticsService.formatNumber(
                                      metric.subscriptionIncludedReqs
                                    )}
                                  </div>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900">
                              {metric.modelUsage &&
                              metric.modelUsage.length > 0 ? (
                                <div className="space-y-1">
                                  {metric.modelUsage.map((model, idx) => (
                                    <div
                                      key={idx}
                                      className="flex items-center space-x-2"
                                    >
                                      <span className="inline-flex px-2 py-1 text-xs text-blue-800 bg-blue-100 rounded">
                                        {AnalyticsService.getModelDisplayName(
                                          model.name
                                        )}
                                      </span>
                                      <span className="text-xs text-gray-500">
                                        {model.count}次
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                        )) || []}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-gray-500">暂无数据</div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end mt-6">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-transparent rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
