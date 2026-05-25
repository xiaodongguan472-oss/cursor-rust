/**
 * 主题系统类型定义
 */

/**
 * 主题模式
 */
export type ThemeMode = 'light' | 'dark' | 'system' | 'transparent';

/**
 * 自定义背景配置
 */
export interface CustomBackground {
  /** 是否启用自定义背景 */
  enabled: boolean;
  /** 背景图片 URL 或本地路径 */
  imageUrl: string;
  /** 背景模糊度 (0-20px) */
  blur: number;
  /** 前景透明度 (0-1) - 控制前景内容的不透明度 */
  opacity: number;
}

/**
 * 主题配置
 */
export interface ThemeConfig {
  /** 主题模式 */
  mode: ThemeMode;
  /** 自定义背景配置 */
  customBackground?: CustomBackground;
}

/**
 * 默认主题配置
 */
export const DEFAULT_THEME_CONFIG: ThemeConfig = {
  mode: 'light',
  customBackground: {
    enabled: false,
    imageUrl: '',
    blur: 0,
    opacity: 1, // 默认完全不透明，确保内容可见
  },
};

/**
 * 默认自定义背景配置
 */
export const DEFAULT_CUSTOM_BACKGROUND: CustomBackground = {
  enabled: false,
  imageUrl: '',
  blur: 0,
  opacity: 1, // 默认完全不透明，确保内容可见
};

