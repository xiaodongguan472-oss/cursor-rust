/**
 * 性能监控工具
 * 用于追踪应用性能，发现优化机会
 */

interface PerformanceMetric {
  name: string;
  duration: number;
  timestamp: number;
  type: 'operation' | 'render' | 'network';
}

class PerformanceMonitor {
  private metrics: PerformanceMetric[] = [];
  private timers: Map<string, number> = new Map();
  private maxMetrics = import.meta.env.DEV ? 100 : 0; // ✅ 生产环境不保留任何指标
  private isEnabled = import.meta.env.DEV; // ✅ 生产环境默认禁用

  /**
   * 开始计时
   * ✅ 生产环境完全跳过，零开销
   */
  start(name: string): void {
    if (!this.isEnabled) return;
    this.timers.set(name, performance.now());
  }

  /**
   * 结束计时并记录
   * ✅ 生产环境完全跳过，零开销
   */
  end(name: string, type: 'operation' | 'render' | 'network' = 'operation'): number {
    if (!this.isEnabled) return 0;

    const startTime = this.timers.get(name);

    if (!startTime) {
      console.warn(`Performance timer "${name}" was not started`);
      return 0;
    }

    const duration = performance.now() - startTime;
    this.timers.delete(name);

    // 记录指标
    this.addMetric({
      name,
      duration,
      timestamp: Date.now(),
      type,
    });

    return duration;
  }

  /**
   * 测量函数执行时间
   * ✅ 生产环境直接执行函数，零开销
   */
  async measure<T>(
    name: string,
    fn: () => T | Promise<T>,
    type: 'operation' | 'render' | 'network' = 'operation'
  ): Promise<T> {
    // ✅ 生产环境直接返回，不创建任何对象
    if (!this.isEnabled) {
      return await fn();
    }

    this.start(name);
    try {
      const result = await fn();
      return result;
    } finally {
      this.end(name, type);
    }
  }

  /**
   * 添加指标
   */
  private addMetric(metric: PerformanceMetric): void {
    this.metrics.push(metric);

    // 限制记录数量
    if (this.metrics.length > this.maxMetrics) {
      this.metrics.shift();
    }

    // 开发环境输出
    if (import.meta.env.DEV) {
      const color = metric.duration > 1000 ? 'red' : metric.duration > 500 ? 'orange' : 'green';
      console.log(
        `%c[Performance] ${metric.name}: ${metric.duration.toFixed(2)}ms`,
        `color: ${color}; font-weight: bold;`
      );
    }
  }

  /**
   * 获取所有指标
   */
  getMetrics(): PerformanceMetric[] {
    return [...this.metrics];
  }

  /**
   * 获取统计信息
   */
  getStats(name?: string): {
    count: number;
    avg: number;
    min: number;
    max: number;
    total: number;
  } {
    const filtered = name
      ? this.metrics.filter((m) => m.name === name)
      : this.metrics;

    if (filtered.length === 0) {
      return { count: 0, avg: 0, min: 0, max: 0, total: 0 };
    }

    const durations = filtered.map((m) => m.duration);
    const total = durations.reduce((sum, d) => sum + d, 0);

    return {
      count: filtered.length,
      avg: total / filtered.length,
      min: Math.min(...durations),
      max: Math.max(...durations),
      total,
    };
  }

  /**
   * 清空所有指标
   */
  clear(): void {
    this.metrics = [];
    this.timers.clear();
  }

  /**
   * 启用/禁用性能监控
   */
  setEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
    if (!enabled) {
      this.clear();
    }
  }

  /**
   * 检查是否启用
   */
  isMonitoringEnabled(): boolean {
    return this.isEnabled;
  }

  /**
   * 导出性能报告
   */
  exportReport(): string {
    const report = {
      timestamp: new Date().toISOString(),
      metrics: this.metrics,
      summary: {
        operation: this.getStats(),
        byName: this.getUniqueNames().map((name) => ({
          name,
          ...this.getStats(name),
        })),
      },
    };

    return JSON.stringify(report, null, 2);
  }

  /**
   * 获取所有唯一的指标名称
   */
  private getUniqueNames(): string[] {
    return [...new Set(this.metrics.map((m) => m.name))];
  }

  /**
   * 获取内存使用情况（如果可用）
   */
  getMemoryUsage(): {
    used: number;
    total: number;
    limit: number;
  } | null {
    if ('memory' in performance) {
      const memory = (performance as any).memory;
      return {
        used: memory.usedJSHeapSize / 1024 / 1024, // MB
        total: memory.totalJSHeapSize / 1024 / 1024, // MB
        limit: memory.jsHeapSizeLimit / 1024 / 1024, // MB
      };
    }
    return null;
  }

  /**
   * 打印性能摘要
   */
  printSummary(): void {
    console.group('📊 Performance Summary');
    
    const uniqueNames = this.getUniqueNames();
    
    uniqueNames.forEach((name) => {
      const stats = this.getStats(name);
      console.log(
        `${name}: avg ${stats.avg.toFixed(2)}ms (${stats.count} calls, min ${stats.min.toFixed(2)}ms, max ${stats.max.toFixed(2)}ms)`
      );
    });

    const memory = this.getMemoryUsage();
    if (memory) {
      console.log(`\n💾 Memory: ${memory.used.toFixed(2)}MB / ${memory.total.toFixed(2)}MB (limit: ${memory.limit.toFixed(2)}MB)`);
    }

    console.groupEnd();
  }
}

// 创建单例
export const performanceMonitor = new PerformanceMonitor();

// 开发环境下暴露到 window
if (import.meta.env.DEV) {
  (window as any).__perf__ = performanceMonitor;
  console.log('💡 Performance monitor available as window.__perf__');
}

/**
 * 便捷的测量函数
 */
export function measurePerformance<T>(
  name: string,
  fn: () => T | Promise<T>
): Promise<T> {
  return performanceMonitor.measure(name, fn);
}

/**
 * React Hook: 测量组件渲染时间
 */
export function usePerformanceMonitor(componentName: string) {
  const startTime = performance.now();

  return {
    onMount: () => {
      const duration = performance.now() - startTime;
      performanceMonitor['addMetric']({
        name: `${componentName} mount`,
        duration,
        timestamp: Date.now(),
        type: 'render',
      });
    },
  };
}

/**
 * 监控网络请求
 */
export async function monitoredFetch<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  return performanceMonitor.measure(
    `Fetch: ${url}`,
    async () => {
      const response = await fetch(url, options);
      return response.json();
    },
    'network'
  );
}

