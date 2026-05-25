/**
 * 主题服务
 * 负责主题切换、自定义背景管理
 */

import type { ThemeConfig, ThemeMode, CustomBackground } from '../types/theme';
import { DEFAULT_THEME_CONFIG } from '../types/theme';
import { safeStorage } from '../utils/safeStorage';

const STORAGE_KEY = 'mycursor_theme_config';

/**
 * 主题服务类
 */
export class ThemeService {
  private currentConfig: ThemeConfig = DEFAULT_THEME_CONFIG;
  private systemThemeListener?: MediaQueryList;

  constructor() {
    this.loadConfig();
    this.setupSystemThemeListener();
  }

  /**
   * 从 localStorage 加载配置
   * ✅ 使用安全包装器
   */
  private loadConfig(): void {
    const stored = safeStorage.get<ThemeConfig>(STORAGE_KEY);
    if (stored) {
      this.currentConfig = stored;
    }
  }

  /**
   * 保存配置到 localStorage
   * ✅ 使用安全包装器
   */
  private saveConfig(): void {
    safeStorage.set(STORAGE_KEY, this.currentConfig);
  }

  /**
   * 设置系统主题监听器
   */
  private setupSystemThemeListener(): void {
    if (typeof window === 'undefined') return;

    this.systemThemeListener = window.matchMedia('(prefers-color-scheme: dark)');
    this.systemThemeListener.addEventListener('change', () => {
      if (this.currentConfig.mode === 'system') {
        this.applyTheme(this.currentConfig);
      }
    });
  }

  /**
   * 获取当前配置
   */
  getConfig(): ThemeConfig {
    return { ...this.currentConfig };
  }

  /**
   * 设置主题模式
   */
  setThemeMode(mode: ThemeMode): void {
    this.currentConfig.mode = mode;
    this.saveConfig();
    this.applyTheme(this.currentConfig);
  }

  /**
   * 设置自定义背景
   */
  setCustomBackground(background: Partial<CustomBackground>): void {
    console.log('[ThemeService] 设置自定义背景，传入配置:', background);
    
    // 确保有初始配置
    if (!this.currentConfig.customBackground) {
      console.log('[ThemeService] 初始化默认背景配置');
      this.currentConfig.customBackground = {
        enabled: false,
        imageUrl: '',
        blur: 0,
        opacity: 1,
      };
    }
    
    // 合并配置
    const oldConfig = { ...this.currentConfig.customBackground };
    this.currentConfig.customBackground = {
      ...this.currentConfig.customBackground,
      ...background,
    };
    
    console.log('[ThemeService] 配置合并完成:', {
      old: oldConfig,
      new: this.currentConfig.customBackground,
    });
    
    this.saveConfig();
    this.applyCustomBackground(this.currentConfig.customBackground);
  }

  /**
   * 应用主题
   */
  applyTheme(config: ThemeConfig): void {
    const root = document.documentElement;
    let effectiveMode = config.mode;

    // 如果是系统主题，检测系统偏好
    if (config.mode === 'system') {
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      effectiveMode = isDark ? 'dark' : 'light';
    }
    // 如果是透明主题，保持 transparent
    else if (config.mode === 'transparent') {
      effectiveMode = 'transparent';
    }

    // 设置主题属性
    root.setAttribute('data-theme', effectiveMode);

    // 应用自定义背景
    if (config.customBackground?.enabled) {
      this.applyCustomBackground(config.customBackground);
    } else {
      this.clearCustomBackground();
    }
  }

  /**
   * 应用自定义背景
   */
  private applyCustomBackground(background: CustomBackground): void {
    console.log('[ThemeService] 应用自定义背景:', {
      enabled: background.enabled,
      hasImageUrl: !!background.imageUrl,
      imageUrlLength: background.imageUrl?.length || 0,
      blur: background.blur,
      opacity: background.opacity,
    });

    const body = document.body;

    if (!background.enabled || !background.imageUrl) {
      console.log('[ThemeService] 背景未启用或无图片，清除背景');
      this.clearCustomBackground();
      return;
    }

    // 设置背景图片（固定为 cover 和 center）
    try {
      body.style.backgroundImage = `url(${background.imageUrl})`;
      body.style.backgroundSize = 'cover';
      body.style.backgroundPosition = 'center';
      body.style.backgroundRepeat = 'no-repeat';
      body.style.backgroundAttachment = 'fixed';
      
      console.log('[ThemeService] 背景图片已设置');
    } catch (error) {
      console.error('[ThemeService] 设置背景图片失败:', error);
      return;
    }

    // 应用背景模糊效果
    if (background.blur > 0) {
      body.style.filter = `blur(${background.blur}px)`;
      console.log('[ThemeService] 应用模糊效果:', background.blur);
    } else {
      body.style.filter = '';
    }

    // 应用前景透明度，确保不低于 0.4
    const opacity = Math.max(0.4, background.opacity || 1);
    console.log('[ThemeService] 应用前景透明度:', opacity);
    this.applyForegroundOpacity(opacity);
  }

  /**
   * 应用前景透明度
   * 改进：通过 CSS 变量控制内容区域背景透明度，让背景图片可见
   */
  private applyForegroundOpacity(opacity: number): void {
    // 将 opacity 转换为 CSS 变量
    // opacity 范围：0.4-1
    // 0.4 = 内容背景 40% 不透明（背景图很明显，60% 可见）
    // 1.0 = 内容背景完全不透明（背景图不可见）
    console.log('[ThemeService] 设置内容不透明度:', opacity);
    document.documentElement.style.setProperty('--content-bg-opacity', opacity.toString());
  }

  /**
   * 清除自定义背景
   */
  private clearCustomBackground(): void {
    const body = document.body;
    body.style.backgroundImage = '';
    body.style.backgroundSize = '';
    body.style.backgroundPosition = '';
    body.style.backgroundRepeat = '';
    body.style.backgroundAttachment = '';
    body.style.filter = '';

    // 清除 CSS 变量
    document.documentElement.style.removeProperty('--content-bg-opacity');

    // 移除旧的遮罩层（兼容性清理）
    const overlayEl = document.getElementById('bg-overlay-layer');
    if (overlayEl) {
      overlayEl.remove();
    }

    // 移除旧的前景透明度样式（兼容性清理）
    const styleEl = document.getElementById('custom-fg-opacity');
    if (styleEl) {
      styleEl.remove();
    }
  }

  /**
   * 上传背景图片
   * @param file 图片文件
   * @returns 图片 URL（Data URL 格式）
   */
  async uploadBackground(file: File): Promise<string> {
    console.log('[ThemeService] 开始读取图片文件:', {
      name: file.name,
      type: file.type,
      size: file.size,
    });

    return new Promise((resolve, reject) => {
      // 验证文件对象
      if (!file || !(file instanceof File)) {
        console.error('[ThemeService] 无效的文件对象:', file);
        reject(new Error('无效的文件对象'));
        return;
      }

      const reader = new FileReader();
      
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        
        if (!dataUrl || typeof dataUrl !== 'string') {
          console.error('[ThemeService] 读取结果无效:', dataUrl);
          reject(new Error('文件读取结果无效'));
          return;
        }

        // 验证是否是有效的图片 Data URL
        if (!dataUrl.startsWith('data:image/')) {
          console.error('[ThemeService] 不是有效的图片 Data URL:', dataUrl.substring(0, 50));
          reject(new Error('文件不是有效的图片格式'));
          return;
        }

        console.log('[ThemeService] 图片读取成功:', {
          urlLength: dataUrl.length,
          urlPrefix: dataUrl.substring(0, 50),
        });
        
        resolve(dataUrl);
      };
      
      reader.onerror = (error) => {
        console.error('[ThemeService] 文件读取错误:', error);
        reject(new Error(`文件读取失败: ${reader.error?.message || '未知错误'}`));
      };
      
      reader.onabort = () => {
        console.error('[ThemeService] 文件读取被中止');
        reject(new Error('文件读取被中止'));
      };
      
      // 开始读取文件
      try {
        reader.readAsDataURL(file);
      } catch (error) {
        console.error('[ThemeService] 启动文件读取失败:', error);
        reject(error);
      }
    });
  }

  /**
   * 初始化主题（应用保存的配置）
   */
  init(): void {
    this.applyTheme(this.currentConfig);
  }

  /**
   * 销毁服务
   */
  destroy(): void {
    if (this.systemThemeListener) {
      this.systemThemeListener.removeEventListener('change', () => {});
    }
  }
}

// 导出单例
export const themeService = new ThemeService();

