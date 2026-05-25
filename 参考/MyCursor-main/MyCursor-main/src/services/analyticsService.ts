import { invoke } from "@tauri-apps/api/core";
import type {
  UserAnalyticsData,
  FilteredUsageEventsData,
  AnalyticsResponse,
} from "../types/analytics";

export class AnalyticsService {
  /**
   * 获取用户分析数据
   */
  static async getUserAnalytics(
    token: string,
    teamId: number = 0,
    userId: number = 0,
    startDate: string,
    endDate: string
  ): Promise<AnalyticsResponse<UserAnalyticsData>> {
    try {
      console.log("📊 获取用户分析数据...", {
        teamId,
        userId,
        startDate,
        endDate,
      });

      const result = await invoke<AnalyticsResponse<UserAnalyticsData>>(
        "get_user_analytics",
        {
          token,
          teamId,
          userId,
          startDate,
          endDate,
        }
      );

      console.log("✅ 用户分析数据获取成功:", result);
      return result;
    } catch (error) {
      console.error("❌ 获取用户分析数据失败:", error);
      return {
        success: false,
        message: `获取用户分析数据失败: ${error}`,
      };
    }
  }

  /**
   * 获取过滤的使用事件数据
   */
  static async getUsageEvents(
    token: string,
    teamId: number = 0,
    startDate: string | number,
    endDate: string | number,
    page: number = 1,
    pageSize: number = 100
  ): Promise<AnalyticsResponse<FilteredUsageEventsData>> {
    try {
      console.log("📊 获取使用事件数据...", {
        teamId,
        startDate,
        endDate,
        page,
        pageSize,
      });

      const result = await invoke<AnalyticsResponse<FilteredUsageEventsData>>(
        "get_usage_events",
        {
          token,
          teamId,
          startDate,
          endDate,
          page,
          pageSize,
        }
      );

      console.log("✅ 使用事件数据获取成功:", result);
      return result;
    } catch (error) {
      console.error("❌ 获取使用事件数据失败:", error);
      return {
        success: false,
        message: `获取使用事件数据失败: ${error}`,
      };
    }
  }

  /**
   * 辅助方法：将日期转换为时间戳字符串（毫秒）
   */
  static dateToTimestamp(date: Date): string {
    return date.getTime().toString();
  }

  /**
   * 辅助方法：将时间戳字符串转换为日期
   */
  static timestampToDate(timestamp: string): Date {
    return new Date(parseInt(timestamp));
  }

  /**
   * 辅助方法：格式化金额（分转元）
   */
  static formatCents(cents: number | null | undefined): string {
    if (cents === null || cents === undefined || isNaN(cents)) {
      return "$0.00";
    }
    return `$${(cents / 100).toFixed(2)}`;
  }

  /**
   * 辅助方法：格式化数字
   */
  static formatNumber(num: number | null | undefined): string {
    if (num === null || num === undefined || isNaN(num)) {
      return "0";
    }
    return num.toLocaleString();
  }

  /**
   * 辅助方法：获取事件类型的显示文本
   */
  static getEventKindDisplay(kind: string): string {
    const kindMap: Record<string, string> = {
      USAGE_EVENT_KIND_INCLUDED_IN_PRO: "包含在订阅中",
      USAGE_EVENT_KIND_ERRORED_NOT_CHARGED: "错误未计费",
      USAGE_EVENT_KIND_PAID: "付费使用",
      USAGE_EVENT_KIND_FREE: "免费使用",
    };
    return kindMap[kind] || kind;
  }

  /**
   * 辅助方法：获取模型的显示名称
   */
  static getModelDisplayName(model: string): string {
    const modelMap: Record<string, string> = {
      "claude-4.1-opus": "Claude 4.1 Opus",
      "claude-4-sonnet": "Claude 4 Sonnet",
      "claude-3-5-sonnet": "Claude 3.5 Sonnet",
      "gpt-4": "GPT-4",
      "gpt-3.5-turbo": "GPT-3.5 Turbo",
    };
    return modelMap[model] || model;
  }
}
