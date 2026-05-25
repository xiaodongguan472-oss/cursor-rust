export interface ModelUsage {
  model_intent: string;
  input_tokens: string;
  output_tokens: string;
  cache_write_tokens: string;
  cache_read_tokens: string;
  total_cents: number;
}

export interface AggregatedUsageData {
  aggregations: ModelUsage[];
  total_input_tokens: string;
  total_output_tokens: string;
  total_cache_write_tokens: string;
  total_cache_read_tokens: string;
  total_cost_cents: number;
}

export interface UsageRequest {
  start_date: number;
  end_date: number;
  team_id: number;
}

export interface UsageResponse {
  success: boolean;
  message: string;
  data?: AggregatedUsageData;
}

export interface DateRange {
  startDate: Date;
  endDate: Date;
}

export interface UsageEvent {
  timestamp: number;
  model_intent: string;
  cost_cents: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_write_tokens?: number;
  cache_read_tokens?: number;
}

export interface EventsDataCache {
  email: string;
  start_date: string;
  end_date: string;
  events: UsageEvent[];
  total_events?: number;
  saved_at: number;
  message?: string; // 用于显示错误或提示信息
}
