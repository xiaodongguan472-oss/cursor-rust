/**
 * Web Worker 管理器
 * 提供简单的 API 来使用 Web Worker 处理大数据
 * 
 * ✅ 功能:
 * 1. Worker 生命周期管理
 * 2. Promise 化的 Worker 通信
 * 3. 超时处理
 * 4. 错误处理
 * 
 * 使用示例:
 * ```typescript
 * const result = await workerManager.parseAccounts(jsonString);
 * if (result.success) {
 *   console.log('解析成功:', result.accounts);
 * }
 * ```
 */

import type { WorkerMessage, WorkerResponse, WorkerMessageType } from '../workers/dataProcessor.worker';
import { logger } from './logger';

// 请求超时时间（30秒）
const REQUEST_TIMEOUT = 30000;

/**
 * Worker 管理器类
 */
class WorkerManager {
  private worker: Worker | null = null;
  private pendingRequests = new Map<string, {
    resolve: (value: any) => void;
    reject: (reason: any) => void;
    timeout: number;
  }>();
  private requestIdCounter = 0;

  /**
   * 初始化 Worker
   */
  private initWorker(): void {
    if (this.worker) {
      return;
    }

    try {
      // 创建 Worker
      this.worker = new Worker(
        new URL('../workers/dataProcessor.worker.ts', import.meta.url),
        { type: 'module' }
      );

      // 监听消息
      this.worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
        this.handleWorkerMessage(event.data);
      };

      // 监听错误
      this.worker.onerror = (error) => {
        logger.error('Worker 错误:', error);
        this.rejectAllPending('Worker 发生错误');
        this.terminateWorker();
      };

      logger.info('✅ Worker 初始化成功');
    } catch (error) {
      logger.error('Worker 初始化失败:', error);
      throw error;
    }
  }

  /**
   * 处理 Worker 消息
   */
  private handleWorkerMessage(response: WorkerResponse): void {
    const pending = this.pendingRequests.get(response.id);
    
    if (!pending) {
      logger.warn(`收到未知请求的响应: ${response.id}`);
      return;
    }

    // 清除超时
    clearTimeout(pending.timeout);
    this.pendingRequests.delete(response.id);

    // 处理响应
    if (response.success) {
      pending.resolve(response.data);
    } else {
      pending.reject(new Error(response.error || '处理失败'));
    }
  }

  /**
   * 发送消息到 Worker
   */
  private sendMessage<T = any>(
    type: WorkerMessageType,
    data: any,
    timeout: number = REQUEST_TIMEOUT
  ): Promise<T> {
    return new Promise((resolve, reject) => {
      // 初始化 Worker
      if (!this.worker) {
        this.initWorker();
      }

      // 生成请求 ID
      const id = `req_${++this.requestIdCounter}_${Date.now()}`;

      // 设置超时
      const timeoutId = window.setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`请求超时: ${type}`));
      }, timeout);

      // 保存请求
      this.pendingRequests.set(id, {
        resolve,
        reject,
        timeout: timeoutId,
      });

      // 发送消息
      const message: WorkerMessage = { type, id, data };
      this.worker!.postMessage(message);
    });
  }

  /**
   * 拒绝所有待处理的请求
   */
  private rejectAllPending(reason: string): void {
    this.pendingRequests.forEach((pending) => {
      clearTimeout(pending.timeout);
      pending.reject(new Error(reason));
    });
    this.pendingRequests.clear();
  }

  /**
   * 终止 Worker
   */
  terminateWorker(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
      this.rejectAllPending('Worker 已终止');
      logger.info('Worker 已终止');
    }
  }

  /**
   * 解析账号数据
   */
  async parseAccounts(jsonString: string): Promise<{
    success: boolean;
    accounts?: any[];
    error?: string;
  }> {
    try {
      const accounts = await this.sendMessage('PARSE_ACCOUNTS', { jsonString });
      return { success: true, accounts };
    } catch (error: any) {
      logger.error('解析账号失败:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * 验证账号数据
   */
  async validateAccounts(accounts: any[]): Promise<{
    success: boolean;
    validAccounts?: any[];
    invalidCount?: number;
    errors?: string[];
  }> {
    try {
      const result = await this.sendMessage('VALIDATE_ACCOUNTS', { accounts });
      return { success: true, ...result };
    } catch (error: any) {
      logger.error('验证账号失败:', error);
      return { success: false };
    }
  }

  /**
   * 去重账号
   */
  async deduplicateAccounts(accounts: any[]): Promise<{
    success: boolean;
    uniqueAccounts?: any[];
    duplicateCount?: number;
  }> {
    try {
      const result = await this.sendMessage('DEDUPLICATE_ACCOUNTS', { accounts });
      return { success: true, ...result };
    } catch (error: any) {
      logger.error('去重账号失败:', error);
      return { success: false };
    }
  }

  /**
   * 聚合用量数据
   */
  async aggregateUsage(usageData: any[]): Promise<{
    success: boolean;
    aggregated?: any;
  }> {
    try {
      const aggregated = await this.sendMessage('AGGREGATE_USAGE', { usageData });
      return { success: true, aggregated };
    } catch (error: any) {
      logger.error('聚合用量失败:', error);
      return { success: false };
    }
  }

  /**
   * 导出数据
   */
  async exportData(data: any, options: { pretty?: boolean } = {}): Promise<{
    success: boolean;
    jsonString?: string;
    error?: string;
  }> {
    try {
      const jsonString = await this.sendMessage('EXPORT_DATA', { data, options });
      return { success: true, jsonString };
    } catch (error: any) {
      logger.error('导出数据失败:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * 检查 Worker 是否可用
   */
  isAvailable(): boolean {
    return typeof Worker !== 'undefined';
  }

  /**
   * 获取待处理请求数量
   */
  getPendingCount(): number {
    return this.pendingRequests.size;
  }
}

// 创建单例
export const workerManager = new WorkerManager();

// 在页面卸载时清理
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    workerManager.terminateWorker();
  });
}

