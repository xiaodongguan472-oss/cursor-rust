/**
 * Tauri Invoke 通用类型定义
 * 提供类型安全的 invoke 调用
 */

/**
 * Tauri命令的标准响应格式
 */
export interface TauriResponse<T = any> {
  success: boolean;
  data?: T;
  message?: string;
  error?: string;
}

/**
 * 用量事件相关类型
 */
export interface GetUsageEventsParams {
  token: string;
  teamId: number;
  startDate: string;
  endDate: string;
  page: number;
  pageSize: number;
}

export interface GetUsageEventsResponse {
  success: boolean;
  data?: {
    usageEventsDisplay?: Array<any>;
    usage_events_display?: Array<any>;
    totalUsageEventsCount?: number;
    total_usage_events_count?: number;
  };
  message?: string;
}

/**
 * 用量统计相关类型
 */
export interface GetUsageForPeriodParams {
  token: string;
  startDate: number;
  endDate: number;
  teamId: number;
}

/**
 * 账户管理相关类型
 */
export interface AutoLoginParams {
  email: string;
  password: string;
  showWindow?: boolean;
}

export interface TriggerAuthorizationLoginParams {
  uuid: string;
  challenge: string;
  workosCursorSessionToken: string;
}

export interface TriggerAuthorizationLoginPollParams {
  uuid: string;
  verifier: string;
}

export interface AuthorizationLoginPollResponse {
  success: boolean;
  response_body?: string;
}

/**
 * Cursor主页相关类型
 */
export interface OpenCursorDashboardParams {
  workosCursorSessionToken: string;
}

/**
 * 类型安全的 invoke 包装器
 */
export type InvokeCommand<P = void, R = TauriResponse> = P extends void
  ? () => Promise<R>
  : (params: P) => Promise<R>;

/**
 * 所有可用的 Tauri 命令类型映射
 */
export interface TauriCommands {
  get_usage_events: InvokeCommand<GetUsageEventsParams, GetUsageEventsResponse>;
  get_usage_for_period: InvokeCommand<GetUsageForPeriodParams, TauriResponse<any>>;
  auto_login_and_get_cookie: InvokeCommand<AutoLoginParams, TauriResponse>;
  auto_login_failed: InvokeCommand<{ error: string }, TauriResponse>;
  show_auto_login_window: InvokeCommand<void, TauriResponse>;
  trigger_authorization_login: InvokeCommand<TriggerAuthorizationLoginParams, TauriResponse>;
  trigger_authorization_login_poll: InvokeCommand<
    TriggerAuthorizationLoginPollParams,
    AuthorizationLoginPollResponse
  >;
  open_cursor_dashboard: InvokeCommand<OpenCursorDashboardParams, TauriResponse>;
}

/**
 * 类型安全的 invoke 助手
 * 使用方式:
 * const result = await safeInvoke('get_usage_events', params);
 */
export async function safeInvoke<K extends keyof TauriCommands>(
  command: K,
  ...args: Parameters<TauriCommands[K]>
): Promise<ReturnType<TauriCommands[K]>> {
  const { invoke } = await import('@tauri-apps/api/core');
  // @ts-expect-error - Tauri invoke 类型推断限制
  return invoke(command, ...args);
}
