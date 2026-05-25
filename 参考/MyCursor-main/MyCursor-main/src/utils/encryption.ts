/**
 * 数据加密工具
 * 用于敏感数据的加密存储（如 Token、密码等）
 * 
 * 注意：这是前端加密，主要用于防止明文暴露，不能替代后端安全措施
 */

/**
 * 简单的字符串加密（XOR + Base64）
 * 适用于本地存储的轻量级加密
 */
export class SimpleEncryption {
  private key: string;

  constructor(key?: string) {
    // 使用默认密钥或自定义密钥
    this.key = key || this.generateKey();
  }

  /**
   * 生成密钥（基于设备特征）
   */
  private generateKey(): string {
    // 使用浏览器特征生成密钥
    const fingerprint = [
      navigator.userAgent,
      navigator.language,
      new Date().getTimezoneOffset(),
      screen.width,
      screen.height,
    ].join('|');
    
    return btoa(fingerprint).slice(0, 32);
  }

  /**
   * 加密字符串
   */
  encrypt(plainText: string): string {
    if (!plainText) return '';
    
    try {
      const encrypted = this.xorEncrypt(plainText, this.key);
      return btoa(encrypted);
    } catch (error) {
      console.error('Encryption failed:', error);
      return plainText;
    }
  }

  /**
   * 解密字符串
   */
  decrypt(encryptedText: string): string {
    if (!encryptedText) return '';
    
    try {
      const decrypted = atob(encryptedText);
      return this.xorEncrypt(decrypted, this.key);
    } catch (error) {
      console.error('Decryption failed:', error);
      return encryptedText;
    }
  }

  /**
   * XOR 加密/解密（对称加密）
   */
  private xorEncrypt(text: string, key: string): string {
    let result = '';
    for (let i = 0; i < text.length; i++) {
      result += String.fromCharCode(
        text.charCodeAt(i) ^ key.charCodeAt(i % key.length)
      );
    }
    return result;
  }
}

/**
 * 内存中的敏感数据管理器
 * 避免敏感数据在内存中长时间明文存在
 */
export class SecureMemoryStorage {
  private storage = new Map<string, { value: string; timestamp: number }>();
  private encryption = new SimpleEncryption();
  private ttl: number = 30 * 60 * 1000; // 默认 30 分钟过期

  /**
   * 设置敏感数据（加密存储）
   */
  set(key: string, value: string, ttl?: number): void {
    const encrypted = this.encryption.encrypt(value);
    this.storage.set(key, {
      value: encrypted,
      timestamp: Date.now(),
    });

    // 设置过期清理
    if (ttl !== undefined) {
      setTimeout(() => this.delete(key), ttl);
    }
  }

  /**
   * 获取敏感数据（自动解密）
   */
  get(key: string): string | null {
    const item = this.storage.get(key);
    if (!item) return null;

    // 检查是否过期
    if (Date.now() - item.timestamp > this.ttl) {
      this.delete(key);
      return null;
    }

    return this.encryption.decrypt(item.value);
  }

  /**
   * 删除敏感数据
   */
  delete(key: string): void {
    this.storage.delete(key);
  }

  /**
   * 清空所有数据
   */
  clear(): void {
    this.storage.clear();
  }

  /**
   * 获取所有键
   */
  keys(): string[] {
    return Array.from(this.storage.keys());
  }
}

/**
 * localStorage 加密包装器
 */
export class SecureLocalStorage {
  private encryption = new SimpleEncryption();
  private prefix = 'secure_';

  /**
   * 加密存储到 localStorage
   */
  setItem(key: string, value: string): void {
    try {
      const encrypted = this.encryption.encrypt(value);
      localStorage.setItem(this.prefix + key, encrypted);
    } catch (error) {
      console.error('SecureLocalStorage.setItem failed:', error);
    }
  }

  /**
   * 从 localStorage 解密读取
   */
  getItem(key: string): string | null {
    try {
      const encrypted = localStorage.getItem(this.prefix + key);
      if (!encrypted) return null;
      return this.encryption.decrypt(encrypted);
    } catch (error) {
      console.error('SecureLocalStorage.getItem failed:', error);
      return null;
    }
  }

  /**
   * 删除项
   */
  removeItem(key: string): void {
    localStorage.removeItem(this.prefix + key);
  }

  /**
   * 清空所有加密存储
   */
  clear(): void {
    const keys = Object.keys(localStorage);
    keys.forEach(key => {
      if (key.startsWith(this.prefix)) {
        localStorage.removeItem(key);
      }
    });
  }
}

// 导出单例实例
export const secureMemory = new SecureMemoryStorage();
export const secureStorage = new SecureLocalStorage();

/**
 * 工具函数：加密 Token
 */
export function encryptToken(token: string): string {
  const encryption = new SimpleEncryption();
  return encryption.encrypt(token);
}

/**
 * 工具函数：解密 Token
 */
export function decryptToken(encryptedToken: string): string {
  const encryption = new SimpleEncryption();
  return encryption.decrypt(encryptedToken);
}

/**
 * 工具函数：生成随机盐值
 */
export function generateSalt(length: number = 16): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let salt = '';
  for (let i = 0; i < length; i++) {
    salt += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return salt;
}

/**
 * 工具函数：简单哈希（用于数据完整性校验）
 */
export function simpleHash(data: string): string {
  let hash = 0;
  for (let i = 0; i < data.length; i++) {
    const char = data.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash).toString(36);
}

// 在开发环境暴露到 window（用于调试）
if (import.meta.env.DEV) {
  (window as any).__encryption__ = {
    secureMemory,
    secureStorage,
    SimpleEncryption,
  };
  console.log('💡 Encryption utilities available as window.__encryption__');
}
