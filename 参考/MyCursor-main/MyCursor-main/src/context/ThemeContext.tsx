/**
 * 主题 Context
 * 提供全局主题状态管理
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import type { ThemeConfig, ThemeMode, CustomBackground } from '../types/theme';
import { themeService } from '../services/themeService';

interface ThemeContextValue {
  /** 当前主题配置 */
  config: ThemeConfig;
  /** 设置主题模式 */
  setThemeMode: (mode: ThemeMode) => void;
  /** 设置自定义背景 */
  setCustomBackground: (background: Partial<CustomBackground>) => void;
  /** 上传背景图片 */
  uploadBackground: (file: File) => Promise<string>;
  /** 切换主题模式 */
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

interface ThemeProviderProps {
  children: ReactNode;
}

/**
 * 主题 Provider
 */
export function ThemeProvider({ children }: ThemeProviderProps) {
  const [config, setConfig] = useState<ThemeConfig>(themeService.getConfig());

  // 初始化主题
  useEffect(() => {
    themeService.init();
    setConfig(themeService.getConfig());

    return () => {
      themeService.destroy();
    };
  }, []);

  /**
   * 设置主题模式
   */
  const setThemeMode = (mode: ThemeMode) => {
    themeService.setThemeMode(mode);
    setConfig(themeService.getConfig());
  };

  /**
   * 设置自定义背景
   */
  const setCustomBackground = (background: Partial<CustomBackground>) => {
    themeService.setCustomBackground(background);
    setConfig(themeService.getConfig());
  };

  /**
   * 上传背景图片
   */
  const uploadBackground = async (file: File): Promise<string> => {
    const url = await themeService.uploadBackground(file);
    return url;
  };

  /**
   * 切换主题模式（Light <-> Dark）
   */
  const toggleTheme = () => {
    const currentMode = config.mode;
    const newMode = currentMode === 'light' ? 'dark' : 'light';
    setThemeMode(newMode);
  };

  const value: ThemeContextValue = {
    config,
    setThemeMode,
    setCustomBackground,
    uploadBackground,
    toggleTheme,
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

/**
 * 使用主题 Hook
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}

