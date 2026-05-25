/**
 * Centralized Logger Utility
 * Provides consistent logging with environment-aware behavior
 * Automatically sanitizes sensitive information
 */

import { sanitizeForLog } from './security';

type LogLevel = "debug" | "info" | "warn" | "error";

interface LoggerConfig {
  enabled: boolean;
  level: LogLevel;
  prefix?: string;
}

class Logger {
  private config: LoggerConfig;
  private static instance: Logger;

  private constructor(config?: Partial<LoggerConfig>) {
    this.config = {
      enabled:
        import.meta.env.DEV || import.meta.env.VITE_ENABLE_LOGGING === "true",
      level: (import.meta.env.VITE_LOG_LEVEL as LogLevel) || "info",
      prefix: config?.prefix || "[MyCursor]",
    };
  }

  static getInstance(config?: Partial<LoggerConfig>): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger(config);
    }
    return Logger.instance;
  }

  private shouldLog(level: LogLevel): boolean {
    if (!this.config.enabled) return false;

    const levels: LogLevel[] = ["debug", "info", "warn", "error"];
    const currentLevelIndex = levels.indexOf(this.config.level);
    const requestedLevelIndex = levels.indexOf(level);

    return requestedLevelIndex >= currentLevelIndex;
  }

  private formatMessage(message: string, ...args: any[]): [string, ...any[]] {
    const timestamp = new Date().toISOString();
    // 自动脱敏日志参数
    const sanitizedArgs = args.map(arg => sanitizeForLog(arg));
    return [`${this.config.prefix} [${timestamp}] ${message}`, ...sanitizedArgs];
  }

  debug(message: string, ...args: any[]): void {
    if (this.shouldLog("debug")) {
      console.debug(...this.formatMessage(message, ...args));
    }
  }

  info(message: string, ...args: any[]): void {
    if (this.shouldLog("info")) {
      console.info(...this.formatMessage(message, ...args));
    }
  }

  warn(message: string, ...args: any[]): void {
    if (this.shouldLog("warn")) {
      console.warn(...this.formatMessage(message, ...args));
    }
  }

  error(message: string, ...args: any[]): void {
    if (this.shouldLog("error")) {
      console.error(...this.formatMessage(message, ...args));
    }
  }
}

// Export singleton instance
export const logger = Logger.getInstance();

// Export factory for custom loggers
export const createLogger = (prefix: string): Logger => {
  return Logger.getInstance({ prefix: `[${prefix}]` });
};
