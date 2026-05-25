/**
 * 安全的 localStorage 包装器
 * 处理配额超出、序列化错误等问题
 */

import { logger } from './logger';

// localStorage 配额限制（大多数浏览器为 5-10MB）
const MAX_STORAGE_SIZE = 5 * 1024 * 1024; // 5MB
const WARNING_THRESHOLD = 0.8; // 80% 时警告

export class SafeStorage {
  /**
   * 获取当前 localStorage 使用量（字节）
   */
  static getStorageSize(): number {
    let total = 0;
    for (let key in localStorage) {
      if (localStorage.hasOwnProperty(key)) {
        total += key.length + (localStorage.getItem(key)?.length || 0);
      }
    }
    return total;
  }

  /**
   * 获取存储使用率（0-1）
   */
  static getStorageUsage(): number {
    return this.getStorageSize() / MAX_STORAGE_SIZE;
  }

  /**
   * 检查是否接近配额限制
   */
  static isNearQuota(): boolean {
    return this.getStorageUsage() > WARNING_THRESHOLD;
  }

  /**
   * 安全地设置 localStorage 项
   * @param key 键名
   * @param value 值（会自动序列化）
   * @param options 选项
   * @returns 是否成功
   */
  static setItem(
    key: string,
    value: any,
    options: {
      compress?: boolean; // 是否压缩（未来可实现）
      maxSize?: number; // 最大允许大小（字节）
      onQuotaExceeded?: () => void; // 配额超出回调
    } = {}
  ): boolean {
    try {
      // 序列化数据
      const serialized = typeof value === 'string' ? value : JSON.stringify(value);
      
      // ✅ 检查单个项大小
      const itemSize = key.length + serialized.length;
      const maxItemSize = options.maxSize || MAX_STORAGE_SIZE * 0.5; // 默认不超过总配额的50%
      
      if (itemSize > maxItemSize) {
        logger.warn(`localStorage 项 "${key}" 过大 (${(itemSize / 1024).toFixed(2)}KB)，已跳过`);
        return false;
      }

      // ✅ 检查总存储使用量
      if (this.isNearQuota()) {
        logger.warn(
          `localStorage 使用率已达 ${(this.getStorageUsage() * 100).toFixed(1)}%，建议清理`
        );
      }

      // ✅ 尝试存储
      localStorage.setItem(key, serialized);
      return true;

    } catch (error: any) {
      // ✅ 处理配额超出错误
      if (error.name === 'QuotaExceededError' || error.code === 22) {
        logger.error('localStorage 配额已满，无法保存数据');
        
        // 调用回调
        if (options.onQuotaExceeded) {
          options.onQuotaExceeded();
        } else {
          // 默认行为：清理旧数据
          this.clearOldestItems(3);
          
          // 重试一次
          try {
            localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
            logger.info('清理后重试成功');
            return true;
          } catch (retryError) {
            logger.error('清理后重试仍然失败');
            return false;
          }
        }
      } else {
        logger.error('localStorage.setItem 失败:', error);
      }
      return false;
    }
  }

  /**
   * 安全地获取 localStorage 项
   * @param key 键名
   * @param defaultValue 默认值
   * @param parse 是否自动解析 JSON
   * @returns 值或默认值
   */
  static getItem<T = any>(
    key: string,
    defaultValue: T | null = null,
    parse: boolean = true
  ): T | null {
    try {
      const value = localStorage.getItem(key);
      
      if (value === null) {
        return defaultValue;
      }

      // ✅ 自动解析 JSON
      if (parse) {
        try {
          return JSON.parse(value) as T;
        } catch {
          // 如果解析失败，返回原始字符串
          return value as unknown as T;
        }
      }

      return value as unknown as T;

    } catch (error) {
      logger.error(`localStorage.getItem("${key}") 失败:`, error);
      return defaultValue;
    }
  }

  /**
   * 安全地删除 localStorage 项
   */
  static removeItem(key: string): boolean {
    try {
      localStorage.removeItem(key);
      return true;
    } catch (error) {
      logger.error(`localStorage.removeItem("${key}") 失败:`, error);
      return false;
    }
  }

  /**
   * 清理最旧的 N 个项（基于时间戳后缀）
   */
  static clearOldestItems(count: number = 5): number {
    try {
      const items: Array<{ key: string; timestamp: number }> = [];

      // 收集所有带时间戳的项
      for (let key in localStorage) {
        if (localStorage.hasOwnProperty(key)) {
          const value = localStorage.getItem(key);
          if (value) {
            try {
              const parsed = JSON.parse(value);
              // 查找 saved_at、timestamp、updatedAt 等字段
              const timestamp = parsed.saved_at || parsed.timestamp || parsed.updatedAt || 0;
              items.push({ key, timestamp });
            } catch {
              // 无法解析的项，设置为最旧
              items.push({ key, timestamp: 0 });
            }
          }
        }
      }

      // 按时间戳排序（最旧的在前）
      items.sort((a, b) => a.timestamp - b.timestamp);

      // 删除最旧的 N 个
      let removed = 0;
      for (let i = 0; i < Math.min(count, items.length); i++) {
        localStorage.removeItem(items[i].key);
        removed++;
      }

      logger.info(`已清理 ${removed} 个最旧的 localStorage 项`);
      return removed;

    } catch (error) {
      logger.error('清理 localStorage 失败:', error);
      return 0;
    }
  }

  /**
   * 清理所有缓存数据（保留配置）
   */
  static clearCache(preserveKeys: string[] = ['app_config_cache', 'mycursor_theme_config']): number {
    try {
      let removed = 0;
      const keysToRemove: string[] = [];

      // 收集要删除的键
      for (let key in localStorage) {
        if (localStorage.hasOwnProperty(key) && !preserveKeys.includes(key)) {
          keysToRemove.push(key);
        }
      }

      // 删除
      keysToRemove.forEach(key => {
        localStorage.removeItem(key);
        removed++;
      });

      logger.info(`已清理 ${removed} 个缓存项，保留了 ${preserveKeys.length} 个配置项`);
      return removed;

    } catch (error) {
      logger.error('清理缓存失败:', error);
      return 0;
    }
  }

  /**
   * 获取存储统计信息
   */
  static getStats(): {
    totalSize: number;
    totalSizeMB: number;
    itemCount: number;
    usage: number;
    usagePercent: string;
    isNearQuota: boolean;
  } {
    const totalSize = this.getStorageSize();
    const usage = this.getStorageUsage();
    const itemCount = Object.keys(localStorage).length;

    return {
      totalSize,
      totalSizeMB: totalSize / (1024 * 1024),
      itemCount,
      usage,
      usagePercent: `${(usage * 100).toFixed(1)}%`,
      isNearQuota: this.isNearQuota(),
    };
  }

  /**
   * 打印存储统计信息
   */
  static logStats(): void {
    const stats = this.getStats();
    logger.info('📊 localStorage 统计:', {
      大小: `${(stats.totalSizeMB).toFixed(2)} MB`,
      项数: stats.itemCount,
      使用率: stats.usagePercent,
      接近配额: stats.isNearQuota ? '⚠️ 是' : '✅ 否',
    });
  }
}

// 导出便捷方法
export const safeStorage = {
  set: SafeStorage.setItem.bind(SafeStorage),
  get: SafeStorage.getItem.bind(SafeStorage),
  remove: SafeStorage.removeItem.bind(SafeStorage),
  clear: SafeStorage.clearCache.bind(SafeStorage),
  stats: SafeStorage.getStats.bind(SafeStorage),
  logStats: SafeStorage.logStats.bind(SafeStorage),
};

