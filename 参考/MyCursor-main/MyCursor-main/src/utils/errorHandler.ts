/**
 * 统一错误处理工具
 * 提供一致的错误处理和用户友好的错误信息
 */

import { logger } from './logger';
import type { TauriResponse } from '../types/tauri';

/**
 * API错误类
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public code?: string,
    public details?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * 网络错误类
 */
export class NetworkError extends Error {
  constructor(message: string = '网络连接失败，请检查网络设置') {
    super(message);
    this.name = 'NetworkError';
  }
}

/**
 * 验证错误类
 */
export class ValidationError extends Error {
  constructor(
    message: string,
    public field?: string
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

/**
 * 从错误对象中提取用户友好的错误消息
 */
export const getErrorMessage = (error: unknown): string => {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof NetworkError) {
    return error.message;
  }

  if (error instanceof ValidationError) {
    return error.field ? `${error.field}: ${error.message}` : error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  if (typeof error === 'string') {
    return error;
  }

  return '发生未知错误';
};

/**
 * 处理API错误
 * @param error 错误对象
 * @param context 错误上下文（用于日志）
 * @returns 标准错误响应
 */
export const handleApiError = (
  error: unknown,
  context?: string
): TauriResponse<null> => {
  const errorMessage = getErrorMessage(error);
  
  // 记录错误日志
  logger.error(context || 'API错误', {
    error: error instanceof Error ? error.message : error,
    stack: error instanceof Error ? error.stack : undefined,
  });

  return {
    success: false,
    data: null,
    message: errorMessage,
    error: errorMessage,
  };
};

/**
 * 包装异步函数，自动处理错误
 * @param fn 要执行的异步函数
 * @param errorContext 错误上下文
 * @returns 包装后的函数
 */
export const withErrorHandling = <T, Args extends any[]>(
  fn: (...args: Args) => Promise<T>,
  errorContext?: string
) => {
  return async (...args: Args): Promise<T | TauriResponse<null>> => {
    try {
      return await fn(...args);
    } catch (error) {
      return handleApiError(error, errorContext);
    }
  };
};

/**
 * 验证必填字段
 */
export const validateRequired = (
  value: any,
  fieldName: string
): void => {
  if (!value || (typeof value === 'string' && value.trim() === '')) {
    throw new ValidationError(`${fieldName}不能为空`, fieldName);
  }
};

/**
 * 验证邮箱格式
 */
export const validateEmail = (email: string): void => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    throw new ValidationError('邮箱格式不正确', 'email');
  }
};

/**
 * 验证Token格式
 */
export const validateToken = (token: string): void => {
  if (!token || token.length < 20) {
    throw new ValidationError('Token格式不正确或长度不足', 'token');
  }
};

/**
 * 批量验证
 */
export const validate = (validations: (() => void)[]): boolean => {
  try {
    validations.forEach(validation => validation());
    return true;
  } catch (error) {
    if (error instanceof ValidationError) {
      logger.warn('验证失败', { field: error.field, message: error.message });
    }
    throw error;
  }
};

/**
 * 安全地执行可能失败的操作，提供默认值
 */
export const tryCatch = <T>(
  fn: () => T,
  defaultValue: T,
  logError: boolean = true
): T => {
  try {
    return fn();
  } catch (error) {
    if (logError) {
      logger.error('操作失败，使用默认值', { error });
    }
    return defaultValue;
  }
};

/**
 * 重试机制
 */
export const retry = async <T>(
  fn: () => Promise<T>,
  options: {
    maxAttempts?: number;
    delay?: number;
    onRetry?: (attempt: number, error: any) => void;
  } = {}
): Promise<T> => {
  const { maxAttempts = 3, delay = 1000, onRetry } = options;
  
  let lastError: any;
  
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      
      if (attempt < maxAttempts) {
        if (onRetry) {
          onRetry(attempt, error);
        }
        
        logger.warn(`操作失败，正在重试 (${attempt}/${maxAttempts})`, { error });
        
        // 等待后重试
        await new Promise(resolve => setTimeout(resolve, delay * attempt));
      }
    }
  }
  
  throw lastError;
};
