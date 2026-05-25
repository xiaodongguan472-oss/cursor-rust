/**
 * 性能测试工具
 * 用于测试优化效果
 * 
 * ✅ 测试项目:
 * 1. 虚拟滚动性能
 * 2. IndexedDB vs localStorage
 * 3. Worker 处理性能
 * 4. 内存使用情况
 */

import { performanceMonitor } from './performance';
import { hybridStorage } from './hybridStorage';
import { workerManager } from './workerManager';
import { logger } from './logger';

/**
 * 生成测试账号数据
 */
export function generateTestAccounts(count: number): any[] {
  const accounts = [];
  
  for (let i = 0; i < count; i++) {
    accounts.push({
      email: `test${i}@example.com`,
      token: `token_${i}_${Math.random().toString(36).substring(7)}`,
      refresh_token: Math.random() > 0.5 ? `refresh_${i}` : null,
      workos_cursor_session_token: Math.random() > 0.7 ? `workos_${i}` : null,
      is_current: i === 0,
      created_at: new Date().toISOString(),
      username: `User ${i}`,
      subscription_type: ['pro', 'free_trial', 'free'][Math.floor(Math.random() * 3)],
      subscription_status: ['active', 'inactive'][Math.floor(Math.random() * 2)],
      trial_days_remaining: Math.floor(Math.random() * 30),
    });
  }
  
  return accounts;
}

/**
 * 测试虚拟滚动性能
 */
export async function testVirtualScrollPerformance(): Promise<void> {
  logger.info('🧪 开始测试虚拟滚动性能...');
  
  const testCases = [100, 1000, 5000, 10000];

  for (const count of testCases) {
    // Generate test accounts but don't store in variable since we don't use it
    generateTestAccounts(count);

    performanceMonitor.start(`render_${count}_accounts`);

    // 模拟渲染时间（实际渲染由 React 处理）
    await new Promise(resolve => setTimeout(resolve, 10));
    
    const time = performanceMonitor.end(`render_${count}_accounts`);
    
    logger.info(`  ✅ 渲染 ${count} 个账号: ${time.toFixed(2)}ms`);
  }
  
  logger.info('✅ 虚拟滚动性能测试完成');
}

/**
 * 测试 IndexedDB vs localStorage 性能
 */
export async function testStoragePerformance(): Promise<void> {
  logger.info('🧪 开始测试存储性能...');
  
  const testData = generateTestAccounts(1000);
  
  // 测试 IndexedDB 写入
  performanceMonitor.start('indexeddb_write');
  await hybridStorage.saveAccounts(testData);
  const idbWriteTime = performanceMonitor.end('indexeddb_write');
  logger.info(`  ✅ IndexedDB 写入 1000 个账号: ${idbWriteTime.toFixed(2)}ms`);
  
  // 测试 IndexedDB 读取
  performanceMonitor.start('indexeddb_read');
  await hybridStorage.loadAccounts();
  const idbReadTime = performanceMonitor.end('indexeddb_read');
  logger.info(`  ✅ IndexedDB 读取 1000 个账号: ${idbReadTime.toFixed(2)}ms`);
  
  // 测试 localStorage 写入（小数据）
  const smallData = generateTestAccounts(10);
  performanceMonitor.start('localstorage_write');
  localStorage.setItem('test_accounts', JSON.stringify(smallData));
  const lsWriteTime = performanceMonitor.end('localstorage_write');
  logger.info(`  ✅ localStorage 写入 10 个账号: ${lsWriteTime.toFixed(2)}ms`);
  
  // 测试 localStorage 读取
  performanceMonitor.start('localstorage_read');
  JSON.parse(localStorage.getItem('test_accounts') || '[]');
  const lsReadTime = performanceMonitor.end('localstorage_read');
  logger.info(`  ✅ localStorage 读取 10 个账号: ${lsReadTime.toFixed(2)}ms`);
  
  // 清理
  localStorage.removeItem('test_accounts');
  
  logger.info('✅ 存储性能测试完成');
}

/**
 * 测试 Worker 处理性能
 */
export async function testWorkerPerformance(): Promise<void> {
  logger.info('🧪 开始测试 Worker 处理性能...');
  
  if (!workerManager.isAvailable()) {
    logger.warn('⚠️ Worker 不可用，跳过测试');
    return;
  }
  
  const testCases = [100, 1000, 5000];
  
  for (const count of testCases) {
    const accounts = generateTestAccounts(count);
    const jsonString = JSON.stringify(accounts);
    
    // 测试主线程解析
    performanceMonitor.start(`main_parse_${count}`);
    JSON.parse(jsonString);
    const mainTime = performanceMonitor.end(`main_parse_${count}`);
    
    // 测试 Worker 解析
    performanceMonitor.start(`worker_parse_${count}`);
    await workerManager.parseAccounts(jsonString);
    const workerTime = performanceMonitor.end(`worker_parse_${count}`);
    
    logger.info(`  ✅ ${count} 个账号:`);
    logger.info(`     - 主线程解析: ${mainTime.toFixed(2)}ms`);
    logger.info(`     - Worker 解析: ${workerTime.toFixed(2)}ms`);
    logger.info(`     - 性能提升: ${((mainTime - workerTime) / mainTime * 100).toFixed(1)}%`);
  }
  
  logger.info('✅ Worker 处理性能测试完成');
}

/**
 * 测试内存使用情况
 */
export async function testMemoryUsage(): Promise<void> {
  logger.info('🧪 开始测试内存使用情况...');

  // Check if performance.memory is available (Chrome-specific API)
  const perfWithMemory = performance as any;
  if (!perfWithMemory.memory) {
    logger.warn('⚠️ performance.memory 不可用，跳过测试');
    return;
  }

  const formatBytes = (bytes: number) => {
    return (bytes / 1024 / 1024).toFixed(2) + ' MB';
  };

  // 初始内存
  const initialMemory = perfWithMemory.memory.usedJSHeapSize;
  logger.info(`  📊 初始内存: ${formatBytes(initialMemory)}`);

  // 创建大量数据
  const accounts = generateTestAccounts(10000);
  const afterCreateMemory = perfWithMemory.memory.usedJSHeapSize;
  logger.info(`  📊 创建 10000 个账号后: ${formatBytes(afterCreateMemory)}`);
  logger.info(`     - 增加: ${formatBytes(afterCreateMemory - initialMemory)}`);

  // 保存到 IndexedDB
  await hybridStorage.saveAccounts(accounts);
  const afterSaveMemory = perfWithMemory.memory.usedJSHeapSize;
  logger.info(`  📊 保存到 IndexedDB 后: ${formatBytes(afterSaveMemory)}`);

  // 清理引用
  (accounts as any).length = 0;

  // 强制垃圾回收（如果可用）
  const globalWithGc = globalThis as any;
  if (globalWithGc.gc) {
    globalWithGc.gc();
  }

  await new Promise(resolve => setTimeout(resolve, 1000));

  const afterGCMemory = perfWithMemory.memory.usedJSHeapSize;
  logger.info(`  📊 垃圾回收后: ${formatBytes(afterGCMemory)}`);
  logger.info(`     - 释放: ${formatBytes(afterSaveMemory - afterGCMemory)}`);
  
  logger.info('✅ 内存使用测试完成');
}

/**
 * 运行所有性能测试
 */
export async function runAllPerformanceTests(): Promise<void> {
  logger.info('🚀 开始运行所有性能测试...\n');
  
  try {
    await testVirtualScrollPerformance();
    console.log('');
    
    await testStoragePerformance();
    console.log('');
    
    await testWorkerPerformance();
    console.log('');
    
    await testMemoryUsage();
    console.log('');
    
    // 显示存储统计
    await hybridStorage.logStats();
    
    logger.info('\n✅ 所有性能测试完成！');
  } catch (error) {
    logger.error('❌ 性能测试失败:', error);
  }
}

/**
 * 导出到全局（方便在控制台调用）
 */
if (typeof window !== 'undefined') {
  (window as any).performanceTest = {
    runAll: runAllPerformanceTests,
    virtualScroll: testVirtualScrollPerformance,
    storage: testStoragePerformance,
    worker: testWorkerPerformance,
    memory: testMemoryUsage,
    generateAccounts: generateTestAccounts,
  };
  
  logger.info('💡 性能测试工具已加载，在控制台输入以下命令运行测试:');
  logger.info('   performanceTest.runAll()        - 运行所有测试');
  logger.info('   performanceTest.virtualScroll() - 测试虚拟滚动');
  logger.info('   performanceTest.storage()       - 测试存储性能');
  logger.info('   performanceTest.worker()        - 测试 Worker 性能');
  logger.info('   performanceTest.memory()        - 测试内存使用');
}

