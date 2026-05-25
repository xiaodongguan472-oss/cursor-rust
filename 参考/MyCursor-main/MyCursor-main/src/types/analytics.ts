// Analytics types for usage tracking and reporting

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  totalCents: number;
}

export interface UsageEvent {
  timestamp: string;
  model: string;
  kind: string;
  tokenUsage?: TokenUsage;
  usageBasedCosts?: string;
}

export interface FilteredUsageEventsData {
  usageEventsDisplay: UsageEvent[];
  totalUsageEventsCount: number;
}

export interface ModelUsageCount {
  name: string;
  count: number;
}

export interface DailyMetric {
  date: string;
  activeUsers?: number;
  acceptedLinesAdded?: number;
  acceptedLinesDeleted?: number;
  totalAccepts?: number;
  totalApplies?: number;
  composerRequests?: number;
  agentRequests?: number;
  subscriptionIncludedReqs?: number;
  modelUsage?: ModelUsageCount[];
}

export interface AnalyticsPeriod {
  startDate: string;
  endDate: string;
}

export interface UserAnalyticsData {
  period: AnalyticsPeriod;
  totalMembersInTeam: number;
  dailyMetrics: DailyMetric[];
}

export interface AnalyticsResponse<T> {
  success: boolean;
  data?: T;
  message: string;
}
