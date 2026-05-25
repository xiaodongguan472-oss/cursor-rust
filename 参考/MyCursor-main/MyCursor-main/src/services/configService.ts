import { invoke } from "@tauri-apps/api/core";

export interface HistorySnapshot {
  timestamp: number; // 刷新时间戳
  total_cost: number; // 总费用（cents）
  models: Record<string, number>; // 各模型费用 {"model_name": cost_in_cents}
}

export interface UsageDataCache {
  email: string;
  token: string;
  start_date: string; // 使用下划线命名与Rust保持一致
  end_date: string;
  data: any;
  history_snapshots?: HistorySnapshot[]; // 历史快照数组（可选，向后兼容）
  saved_at: number;
}

export class ConfigService {
  /**
   * 保存用量数据到本地
   */
  static async saveUsageData(
    email: string,
    token: string,
    startDate: string,
    endDate: string,
    data: any
  ): Promise<{ success: boolean; message: string }> {
    try {
      const cacheData: UsageDataCache = {
        email,
        token,
        start_date: startDate, // 使用下划线命名
        end_date: endDate,
        data,
        saved_at: Date.now(),
      };

      const result = await invoke<any>("save_usage_data_cache", {
        cacheData: JSON.stringify(cacheData),
      });
      return result;
    } catch (error) {
      console.error("保存用量数据失败:", error);
      return {
        success: false,
        message: `保存失败: ${error}`,
      };
    }
  }

  /**
   * 从本地读取用量数据
   */
  static async loadUsageData(email: string): Promise<{
    success: boolean;
    data?: UsageDataCache;
    message?: string;
  }> {
    try {
      const result = await invoke<any>("load_usage_data_cache", { email });
      return result;
    } catch (error) {
      console.error("读取用量数据失败:", error);
      return {
        success: false,
        message: `读取失败: ${error}`,
      };
    }
  }

  /**
   * 清除所有用量数据
   */
  static async clearUsageData(): Promise<{
    success: boolean;
    message: string;
  }> {
    try {
      const result = await invoke<any>("clear_usage_data");
      return result;
    } catch (error) {
      console.error("清除数据失败:", error);
      return {
        success: false,
        message: `清除失败: ${error}`,
      };
    }
  }

  /**
   * 保存账户缓存数据
   */
  static async saveAccountCache(
    accounts: any[]
  ): Promise<{ success: boolean; message: string }> {
    try {
      const result = await invoke<any>("save_account_cache", {
        accountsJson: JSON.stringify(accounts),
      });
      return result;
    } catch (error) {
      console.error("保存账户缓存失败:", error);
      return {
        success: false,
        message: `保存失败: ${error}`,
      };
    }
  }

  /**
   * 加载账户缓存数据
   */
  static async loadAccountCache(): Promise<{
    success: boolean;
    data?: any[];
    message?: string;
  }> {
    try {
      const result = await invoke<any>("load_account_cache");
      if (result.success && result.data) {
        return {
          success: true,
          data: JSON.parse(result.data),
        };
      }
      return result;
    } catch (error) {
      console.error("加载账户缓存失败:", error);
      return {
        success: false,
        message: `加载失败: ${error}`,
      };
    }
  }

  /**
   * 清除账户缓存
   */
  static async clearAccountCache(): Promise<{
    success: boolean;
    message: string;
  }> {
    try {
      const result = await invoke<any>("clear_account_cache");
      return result;
    } catch (error) {
      console.error("清除账户缓存失败:", error);
      return {
        success: false,
        message: `清除失败: ${error}`,
      };
    }
  }

  /**
   * 刷新单个账户信息（从API获取）
   */
  static async refreshSingleAccountInfo(token: string): Promise<any> {
    try {
      const result = await invoke<any>("refresh_single_account_info", {
        token,
      });
      return result;
    } catch (error) {
      console.error("刷新账户信息失败:", error);
      return {
        success: false,
        message: `刷新失败: ${error}`,
      };
    }
  }

  /**
   * 刷新所有账户信息
   */
  static async refreshAllAccountsInfo(tokens: string[]): Promise<any> {
    try {
      const result = await invoke<any>("refresh_all_accounts_info", { tokens });
      return result;
    } catch (error) {
      console.error("刷新所有账户信息失败:", error);
      return {
        success: false,
        message: `刷新失败: ${error}`,
      };
    }
  }

  /**
   * 保存事件数据到本地
   */
  static async saveEventsData(
    eventsData: any
  ): Promise<{ success: boolean; message: string }> {
    try {
      const result = await invoke<any>("save_events_data_cache", {
        eventsData: JSON.stringify(eventsData), // Rust后端会自动转换为events_data
      });
      console.log("💾 保存事件数据结果:", result);
      return result;
    } catch (error) {
      console.error("保存事件数据失败:", error);
      return {
        success: false,
        message: `保存失败: ${error}`,
      };
    }
  }

  /**
   * 从本地读取事件数据
   */
  static async loadEventsData(): Promise<{
    success: boolean;
    data?: any;
    message?: string;
  }> {
    try {
      const result = await invoke<any>("load_events_data_cache");
      if (result.success && result.data) {
        return {
          success: true,
          data: JSON.parse(result.data),
        };
      }
      return result;
    } catch (error) {
      console.error("读取事件数据失败:", error);
      return {
        success: false,
        message: `读取失败: ${error}`,
      };
    }
  }

  /**
   * 清除事件数据
   */
  static async clearEventsData(): Promise<{
    success: boolean;
    message: string;
  }> {
    try {
      const result = await invoke<any>("clear_events_data");
      return result;
    } catch (error) {
      console.error("清除事件数据失败:", error);
      return {
        success: false,
        message: `清除失败: ${error}`,
      };
    }
  }
}
