/**
 * 混合存储策略
 * 优先使用 IndexedDB，降级到 localStorage
 * 
 * ✅ 策略:
 * 1. 大数据（>100KB）: 使用 IndexedDB
 * 2. 小数据（<100KB）: 使用 localStorage
 * 3. IndexedDB 不可用时: 降级到 localStorage
 * 4. localStorage 配额满时: 自动清理并重试
 * 
 * 使用场景:
 * - 账号列表缓存（可能很大）
 * - 用量数据缓存
 * - 配置数据（较小）
 */

import { idb, STORES } from './indexedDB';
import { safeStorage } from './safeStorage';
import { logger } from './logger';

// 大小阈值（100KB）
const SIZE_THRESHOLD = 100 * 1024;

/**
 * 检查 IndexedDB 是否可用
 */
async function isIndexedDBAvailable(): Promise<boolean> {
  try {
    if (!window.indexedDB) {
      return false;
    }
    // 尝试初始化
    await idb.init();
    return true;
  } catch (error) {
    logger.warn('IndexedDB 不可用，将使用 localStorage', error);
    return false;
  }
}

/**
 * 计算数据大小（字节）
 */
function getDataSize(data: any): number {
  try {
    const serialized = JSON.stringify(data);
    return new Blob([serialized]).size;
  } catch {
    return 0;
  }
}

/**
 * 混合存储类
 */
export class HybridStorage {
  private static indexedDBAvailable: boolean | null = null;

  /**
   * 初始化
   */
  static async init(): Promise<void> {
    this.indexedDBAvailable = await isIndexedDBAvailable();
    if (this.indexedDBAvailable) {
      logger.info('✅ 混合存储: 使用 IndexedDB + localStorage');
    } else {
      logger.warn('⚠️ 混合存储: 仅使用 localStorage');
    }
  }

  /**
   * 保存数据
   * @param key 键名
   * @param value 值
   * @param options 选项
   */
  static async set<T = any>(
    key: string,
    value: T,
    options: {
      forceIndexedDB?: boolean; // 强制使用 IndexedDB
      forceLocalStorage?: boolean; // 强制使用 localStorage
      storeName?: string; // IndexedDB 存储名称
    } = {}
  ): Promise<boolean> {
    // 确保初始化
    if (this.indexedDBAvailable === null) {
      await this.init();
    }

    const dataSize = getDataSize(value);
    const useIndexedDB = options.forceIndexedDB || 
                         (!options.forceLocalStorage && 
                          this.indexedDBAvailable && 
                          dataSize > SIZE_THRESHOLD);

    try {
      if (useIndexedDB) {
        // 使用 IndexedDB
        const storeName = options.storeName || STORES.CONFIG;
        const success = await idb.set(storeName, key, value);
        
        if (success) {
          logger.debug(`✅ HybridStorage.set (IndexedDB): ${key} (${(dataSize / 1024).toFixed(2)}KB)`);
          return true;
        } else {
          // IndexedDB 失败，降级到 localStorage
          logger.warn(`⚠️ IndexedDB 保存失败，降级到 localStorage: ${key}`);
          return safeStorage.set(key, value);
        }
      } else {
        // 使用 localStorage
        const success = safeStorage.set(key, value);
        if (success) {
          logger.debug(`✅ HybridStorage.set (localStorage): ${key} (${(dataSize / 1024).toFixed(2)}KB)`);
        }
        return success;
      }
    } catch (error) {
      logger.error('HybridStorage.set 错误:', error);
      return false;
    }
  }

  /**
   * 获取数据
   */
  static async get<T = any>(
    key: string,
    options: {
      defaultValue?: T;
      storeName?: string;
    } = {}
  ): Promise<T | null> {
    // 确保初始化
    if (this.indexedDBAvailable === null) {
      await this.init();
    }

    try {
      // 1. 先尝试从 IndexedDB 读取
      if (this.indexedDBAvailable) {
        const storeName = options.storeName || STORES.CONFIG;
        const data = await idb.get<any>(storeName, key);
        
        if (data) {
          logger.debug(`✅ HybridStorage.get (IndexedDB): ${key}`);
          // 如果数据有 value 字段，返回 value，否则返回整个对象
          return (data.value !== undefined ? data.value : data) as T;
        }
      }

      // 2. IndexedDB 没有数据，尝试从 localStorage 读取
      const localData = safeStorage.get<T>(key, null);
      if (localData !== null) {
        logger.debug(`✅ HybridStorage.get (localStorage): ${key}`);
        return localData;
      }

      // 3. 都没有，返回默认值
      return options.defaultValue ?? null;
    } catch (error) {
      logger.error('HybridStorage.get 错误:', error);
      return options.defaultValue ?? null;
    }
  }

  /**
   * 删除数据
   */
  static async delete(
    key: string,
    options: {
      storeName?: string;
    } = {}
  ): Promise<boolean> {
    let success = true;

    // 从 IndexedDB 删除
    if (this.indexedDBAvailable) {
      const storeName = options.storeName || STORES.CONFIG;
      const idbSuccess = await idb.delete(storeName, key);
      success = success && idbSuccess;
    }

    // 从 localStorage 删除
    const lsSuccess = safeStorage.remove(key);
    success = success && lsSuccess;

    if (success) {
      logger.debug(`✅ HybridStorage.delete: ${key}`);
    }

    return success;
  }

  /**
   * 保存账号列表（专用方法）
   */
  static async saveAccounts(accounts: any[]): Promise<boolean> {
    return this.set('account_cache', accounts, {
      forceIndexedDB: true,
      storeName: STORES.ACCOUNTS,
    });
  }

  /**
   * 加载账号列表（专用方法）
   */
  static async loadAccounts(): Promise<any[] | null> {
    return this.get<any[]>('account_cache', {
      storeName: STORES.ACCOUNTS,
    });
  }

  /**
   * 保存用量数据（专用方法）
   */
  static async saveUsageData(email: string, data: any): Promise<boolean> {
    return this.set(email, data, {
      forceIndexedDB: true,
      storeName: STORES.USAGE_DATA,
    });
  }

  /**
   * 加载用量数据（专用方法）
   */
  static async loadUsageData(email: string): Promise<any | null> {
    return this.get(email, {
      storeName: STORES.USAGE_DATA,
    });
  }

  /**
   * 获取存储统计信息
   */
  static async getStats(): Promise<{
    indexedDB: { storeName: string; count: number }[];
    localStorage: {
      totalSize: number;
      totalSizeMB: number;
      itemCount: number;
      usage: number;
      usagePercent: string;
    };
  }> {
    const indexedDBStats = this.indexedDBAvailable ? await idb.stats() : [];
    const localStorageStats = safeStorage.stats();

    return {
      indexedDB: indexedDBStats,
      localStorage: localStorageStats,
    };
  }

  /**
   * 打印存储统计信息
   */
  static async logStats(): Promise<void> {
    const stats = await this.getStats();

    logger.info('📊 混合存储统计:');
    
    if (stats.indexedDB.length > 0) {
      logger.info('  IndexedDB:');
      stats.indexedDB.forEach(({ storeName, count }) => {
        logger.info(`    - ${storeName}: ${count} 项`);
      });
    }

    logger.info('  localStorage:');
    logger.info(`    - 大小: ${stats.localStorage.totalSizeMB.toFixed(2)} MB`);
    logger.info(`    - 项数: ${stats.localStorage.itemCount}`);
    logger.info(`    - 使用率: ${stats.localStorage.usagePercent}`);
  }

  /**
   * 清理所有缓存
   */
  static async clearAll(): Promise<void> {
    // 清理 IndexedDB
    if (this.indexedDBAvailable) {
      for (const storeName of Object.values(STORES)) {
        await idb.clear(storeName);
      }
    }

    // 清理 localStorage
    safeStorage.clear();

    logger.info('✅ 所有缓存已清理');
  }
}

/**
 * 便捷导出
 */
export const hybridStorage = {
  init: HybridStorage.init.bind(HybridStorage),
  set: HybridStorage.set.bind(HybridStorage),
  get: HybridStorage.get.bind(HybridStorage),
  delete: HybridStorage.delete.bind(HybridStorage),
  saveAccounts: HybridStorage.saveAccounts.bind(HybridStorage),
  loadAccounts: HybridStorage.loadAccounts.bind(HybridStorage),
  saveUsageData: HybridStorage.saveUsageData.bind(HybridStorage),
  loadUsageData: HybridStorage.loadUsageData.bind(HybridStorage),
  stats: HybridStorage.getStats.bind(HybridStorage),
  logStats: HybridStorage.logStats.bind(HybridStorage),
  clearAll: HybridStorage.clearAll.bind(HybridStorage),
};

