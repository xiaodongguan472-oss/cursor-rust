/**
 * Common API Response Types
 */

export interface BaseApiResponse {
  success: boolean;
  message: string;
}

export interface ApiResponse<T = unknown> extends BaseApiResponse {
  data?: T;
}

// Tauri invoke result types
export type DeleteAccountResult = BaseApiResponse;

export interface ExportAccountsResult extends BaseApiResponse {
  exported_path?: string;
}

export type ImportAccountsResult = BaseApiResponse;

// Chart tooltip types
export interface TooltipPayload {
  color: string;
  name: string;
  value: number;
  payload: ChartDataPoint;
}

export interface ChartDataPoint {
  timestamp: number;
  time: number | string; // 允许数值型时间轴
  timeLabel?: string;
  totalCost: number;
  currentModel?: string;
  currentCost?: number;
  [modelName: string]: number | string | undefined;
}

export interface TooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}
