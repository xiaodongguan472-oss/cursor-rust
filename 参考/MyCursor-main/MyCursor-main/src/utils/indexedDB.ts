/**
 * IndexedDB 存储工具
 * 提供比 localStorage 更大的存储空间（几百 MB）和更好的性能
 * 
 * ✅ 优势:
 * - 存储空间: 几百 MB（vs localStorage 的 5-10MB）
 * - 异步操作: 不阻塞主线程
 * - 支持索引: 快速查询
 * - 支持事务: 数据一致性
 * 
 * 使用场景:
 * - 大量账号数据缓存
 * - 用量数据历史记录
 * - 事件数据缓存
 */

import { logger } from './logger';

// 数据库配置
const DB_NAME = 'MyCursorDB';
const DB_VERSION = 1;

// 对象存储（表）名称
export const STORES = {
  ACCOUNTS: 'accounts',
  USAGE_DATA: 'usage_data',
  EVENTS_DATA: 'events_data',
  CONFIG: 'config',
} as const;

// 数据库实例缓存
let dbInstance: IDBDatabase | null = null;

/**
 * 初始化 IndexedDB
 */
export async function initDB(): Promise<IDBDatabase> {
  if (dbInstance) {
    return dbInstance;
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => {
      logger.error('IndexedDB 打开失败:', request.error);
      reject(request.error);
    };

    request.onsuccess = () => {
      dbInstance = request.result;
      logger.info('✅ IndexedDB 初始化成功');
      resolve(dbInstance);
    };

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      // 创建账号存储
      if (!db.objectStoreNames.contains(STORES.ACCOUNTS)) {
        const accountStore = db.createObjectStore(STORES.ACCOUNTS, { keyPath: 'email' });
        accountStore.createIndex('email', 'email', { unique: true });
        accountStore.createIndex('is_current', 'is_current', { unique: false });
        logger.info('✅ 创建 accounts 对象存储');
      }

      // 创建用量数据存储
      if (!db.objectStoreNames.contains(STORES.USAGE_DATA)) {
        const usageStore = db.createObjectStore(STORES.USAGE_DATA, { keyPath: 'email' });
        usageStore.createIndex('email', 'email', { unique: true });
        usageStore.createIndex('saved_at', 'saved_at', { unique: false });
        logger.info('✅ 创建 usage_data 对象存储');
      }

      // 创建事件数据存储
      if (!db.objectStoreNames.contains(STORES.EVENTS_DATA)) {
        const eventsStore = db.createObjectStore(STORES.EVENTS_DATA, { keyPath: 'id', autoIncrement: true });
        eventsStore.createIndex('timestamp', 'timestamp', { unique: false });
        logger.info('✅ 创建 events_data 对象存储');
      }

      // 创建配置存储
      if (!db.objectStoreNames.contains(STORES.CONFIG)) {
        db.createObjectStore(STORES.CONFIG, { keyPath: 'key' });
        logger.info('✅ 创建 config 对象存储');
      }
    };
  });
}

/**
 * 通用的 IndexedDB 操作类
 */
export class IndexedDBStorage {
  /**
   * 保存数据
   */
  static async set<T = any>(storeName: string, key: string, value: T): Promise<boolean> {
    try {
      const db = await initDB();
      const transaction = db.transaction([storeName], 'readwrite');
      const store = transaction.objectStore(storeName);

      // 如果 keyPath 是 'email' 或其他字段，需要将 key 作为对象的一部分
      const data = typeof value === 'object' && value !== null
        ? { ...value, [store.keyPath as string]: key }
        : { [store.keyPath as string]: key, value };

      const request = store.put(data);

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          logger.debug(`✅ IndexedDB.set: ${storeName}/${key}`);
          resolve(true);
        };
        request.onerror = () => {
          logger.error(`❌ IndexedDB.set 失败: ${storeName}/${key}`, request.error);
          reject(request.error);
        };
      });
    } catch (error) {
      logger.error('IndexedDB.set 错误:', error);
      return false;
    }
  }

  /**
   * 获取数据
   */
  static async get<T = any>(storeName: string, key: string): Promise<T | null> {
    try {
      const db = await initDB();
      const transaction = db.transaction([storeName], 'readonly');
      const store = transaction.objectStore(storeName);
      const request = store.get(key);

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          const result = request.result;
          if (result) {
            logger.debug(`✅ IndexedDB.get: ${storeName}/${key}`);
            resolve(result as T);
          } else {
            resolve(null);
          }
        };
        request.onerror = () => {
          logger.error(`❌ IndexedDB.get 失败: ${storeName}/${key}`, request.error);
          reject(request.error);
        };
      });
    } catch (error) {
      logger.error('IndexedDB.get 错误:', error);
      return null;
    }
  }

  /**
   * 获取所有数据
   */
  static async getAll<T = any>(storeName: string): Promise<T[]> {
    try {
      const db = await initDB();
      const transaction = db.transaction([storeName], 'readonly');
      const store = transaction.objectStore(storeName);
      const request = store.getAll();

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          logger.debug(`✅ IndexedDB.getAll: ${storeName} (${request.result.length} 项)`);
          resolve(request.result as T[]);
        };
        request.onerror = () => {
          logger.error(`❌ IndexedDB.getAll 失败: ${storeName}`, request.error);
          reject(request.error);
        };
      });
    } catch (error) {
      logger.error('IndexedDB.getAll 错误:', error);
      return [];
    }
  }

  /**
   * 删除数据
   */
  static async delete(storeName: string, key: string): Promise<boolean> {
    try {
      const db = await initDB();
      const transaction = db.transaction([storeName], 'readwrite');
      const store = transaction.objectStore(storeName);
      const request = store.delete(key);

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          logger.debug(`✅ IndexedDB.delete: ${storeName}/${key}`);
          resolve(true);
        };
        request.onerror = () => {
          logger.error(`❌ IndexedDB.delete 失败: ${storeName}/${key}`, request.error);
          reject(request.error);
        };
      });
    } catch (error) {
      logger.error('IndexedDB.delete 错误:', error);
      return false;
    }
  }

  /**
   * 清空存储
   */
  static async clear(storeName: string): Promise<boolean> {
    try {
      const db = await initDB();
      const transaction = db.transaction([storeName], 'readwrite');
      const store = transaction.objectStore(storeName);
      const request = store.clear();

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          logger.info(`✅ IndexedDB.clear: ${storeName}`);
          resolve(true);
        };
        request.onerror = () => {
          logger.error(`❌ IndexedDB.clear 失败: ${storeName}`, request.error);
          reject(request.error);
        };
      });
    } catch (error) {
      logger.error('IndexedDB.clear 错误:', error);
      return false;
    }
  }

  /**
   * 批量保存数据
   */
  static async setMany<T = any>(storeName: string, items: Array<{ key: string; value: T }>): Promise<boolean> {
    try {
      const db = await initDB();
      const transaction = db.transaction([storeName], 'readwrite');
      const store = transaction.objectStore(storeName);

      const promises = items.map(({ key, value }) => {
        const data = typeof value === 'object' && value !== null
          ? { ...value, [store.keyPath as string]: key }
          : { [store.keyPath as string]: key, value };

        return new Promise<void>((resolve, reject) => {
          const request = store.put(data);
          request.onsuccess = () => resolve();
          request.onerror = () => reject(request.error);
        });
      });

      await Promise.all(promises);
      logger.info(`✅ IndexedDB.setMany: ${storeName} (${items.length} 项)`);
      return true;
    } catch (error) {
      logger.error('IndexedDB.setMany 错误:', error);
      return false;
    }
  }

  /**
   * 获取存储统计信息
   */
  static async getStats(): Promise<{
    storeName: string;
    count: number;
  }[]> {
    try {
      const db = await initDB();
      const stats: { storeName: string; count: number }[] = [];

      for (const storeName of Object.values(STORES)) {
        const transaction = db.transaction([storeName], 'readonly');
        const store = transaction.objectStore(storeName);
        const request = store.count();

        const count = await new Promise<number>((resolve) => {
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => resolve(0);
        });

        stats.push({ storeName, count });
      }

      return stats;
    } catch (error) {
      logger.error('IndexedDB.getStats 错误:', error);
      return [];
    }
  }
}

/**
 * 便捷导出
 */
export const idb = {
  init: initDB,
  set: IndexedDBStorage.set,
  get: IndexedDBStorage.get,
  getAll: IndexedDBStorage.getAll,
  delete: IndexedDBStorage.delete,
  clear: IndexedDBStorage.clear,
  setMany: IndexedDBStorage.setMany,
  stats: IndexedDBStorage.getStats,
};

