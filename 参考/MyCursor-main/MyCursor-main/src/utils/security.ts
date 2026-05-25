/**
 * 安全工具函数
 * 用于处理敏感信息的脱敏和保护
 */

/**
 * 脱敏 Token 或其他敏感字符串
 * @param value 敏感字符串
 * @param visibleStart 可见的开头字符数（默认5）
 * @param visibleEnd 可见的结尾字符数（默认5）
 * @returns 脱敏后的字符串
 */
export const maskSensitiveData = (
  value: string | undefined | null,
  visibleStart: number = 5,
  visibleEnd: number = 5
): string => {
  if (!value || typeof value !== 'string') {
    return '***';
  }

  // 如果字符串太短，全部脱敏
  if (value.length <= visibleStart + visibleEnd) {
    return '***';
  }

  const start = value.slice(0, visibleStart);
  const end = value.slice(-visibleEnd);
  return `${start}...${end}`;
};

/**
 * 脱敏邮箱地址
 * @param email 邮箱地址
 * @returns 脱敏后的邮箱
 * @example maskEmail('user@example.com') => 'u***r@example.com'
 */
export const maskEmail = (email: string | undefined | null): string => {
  if (!email || typeof email !== 'string') {
    return '***';
  }

  const [localPart, domain] = email.split('@');
  if (!localPart || !domain) {
    return '***';
  }

  if (localPart.length <= 2) {
    return `*@${domain}`;
  }

  const maskedLocal = `${localPart[0]}***${localPart[localPart.length - 1]}`;
  return `${maskedLocal}@${domain}`;
};

/**
 * 脱敏对象中的敏感字段
 * @param obj 包含敏感信息的对象
 * @param sensitiveKeys 需要脱敏的字段名数组
 * @returns 脱敏后的对象副本
 */
export const maskObjectFields = <T extends Record<string, any>>(
  obj: T,
  sensitiveKeys: string[] = ['token', 'password', 'secret', 'accessToken', 'refreshToken', 'workos_cursor_session_token']
): T => {
  if (!obj || typeof obj !== 'object') {
    return obj;
  }

  const masked = { ...obj } as any;
  
  for (const key of sensitiveKeys) {
    if (key in masked && typeof masked[key] === 'string') {
      masked[key] = maskSensitiveData(masked[key]);
    }
  }

  return masked as T;
};

/**
 * 为日志安全地格式化对象
 * 自动脱敏常见的敏感字段
 * @param data 要记录的数据
 * @returns 脱敏后的数据
 */
export const sanitizeForLog = (data: any): any => {
  // 生产环境完全禁止记录敏感数据
  if (!import.meta.env.DEV && typeof data === 'object' && data !== null) {
    const hasSensitiveData = ['token', 'password', 'secret', 'key'].some(
      key => key in data
    );
    if (hasSensitiveData) {
      return '[REDACTED - Sensitive Data]';
    }
  }
  if (!data) {
    return data;
  }

  // 如果是字符串，检查是否像Token
  if (typeof data === 'string') {
    // 如果长度大于20且包含字母数字，可能是Token
    if (data.length > 20 && /^[A-Za-z0-9_-]+$/.test(data)) {
      return maskSensitiveData(data);
    }
    return data;
  }

  // 如果是数组
  if (Array.isArray(data)) {
    return data.map(item => sanitizeForLog(item));
  }

  // 如果是对象
  if (typeof data === 'object') {
    return maskObjectFields(data);
  }

  return data;
};

/**
 * 安全的 console.log 包装器
 * 生产环境自动禁用
 */
export const secureLog = {
  log: (...args: any[]) => {
    if (import.meta.env.DEV) {
      console.log(...args.map(sanitizeForLog));
    }
  },
  warn: (...args: any[]) => {
    if (import.meta.env.DEV) {
      console.warn(...args.map(sanitizeForLog));
    }
  },
  error: (...args: any[]) => {
    // 错误日志在生产环境也保留,但要脱敏
    console.error(...args.map(sanitizeForLog));
  },
  info: (...args: any[]) => {
    if (import.meta.env.DEV) {
      console.info(...args.map(sanitizeForLog));
    }
  },
  debug: (...args: any[]) => {
    if (import.meta.env.DEV) {
      console.debug(...args.map(sanitizeForLog));
    }
  },
};

/**
 * 检查字符串是否包含敏感信息
 */
export const containsSensitiveData = (str: string): boolean => {
  if (!str || typeof str !== 'string') return false;
  
  // 检查是否像 Token （长字符串，只包含字母数字和分隔符）
  if (str.length > 30 && /^[A-Za-z0-9_\-\.]+$/.test(str)) {
    return true;
  }
  
  // 检查常见敏感关键词
  const sensitiveKeywords = [
    'token', 'password', 'secret', 'apikey', 'api_key',
    'auth', 'session', 'cookie', 'credential'
  ];
  
  const lowerStr = str.toLowerCase();
  return sensitiveKeywords.some(keyword => lowerStr.includes(keyword));
};
