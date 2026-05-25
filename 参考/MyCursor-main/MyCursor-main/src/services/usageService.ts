import { invoke } from "@tauri-apps/api/core";
import type { AggregatedUsageData } from "../types/usage";

export interface UsageServiceResponse {
  success: boolean;
  message: string;
  data?: AggregatedUsageData;
}

export class UsageService {
  /**
   * 获取指定时间段的用量数据
   */
  static async getUsageForPeriod(
    token: string,
    startDate: number,
    endDate: number,
    teamId: number = -1
  ): Promise<UsageServiceResponse> {
    try {
      console.log("📊 获取用量数据...", {
        startDate: new Date(startDate).toISOString(),
        endDate: new Date(endDate).toISOString(),
        teamId,
      });

      const result = await invoke<any>("get_usage_for_period", {
        token,
        startDate,
        endDate,
        teamId,
      });

      if (result && result.success) {
        return {
          success: true,
          message: "获取用量数据成功",
          data: result.data,
        };
      } else {
        return {
          success: false,
          message: result?.message || "获取用量数据失败",
        };
      }
    } catch (error) {
      console.error("❌ 获取用量数据失败:", error);
      return {
        success: false,
        message: `获取用量数据失败: ${error}`,
      };
    }
  }
}
