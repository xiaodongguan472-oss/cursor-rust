/**
 * 主题选择器组件
 * 用于设置页面的主题切换
 */

import React, { useState, useRef } from 'react';
import { useTheme } from '../context/ThemeContext';
import type { ThemeMode } from '../types/theme';
import { Icon } from './Icon';

export default function ThemeSelector() {
  const { config, setThemeMode, setCustomBackground, uploadBackground } = useTheme();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  /**
   * 处理主题模式切换
   */
  const handleThemeModeChange = (mode: ThemeMode) => {
    setThemeMode(mode);
  };

  /**
   * 处理背景图片上传
   */
  const handleBackgroundUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 验证文件类型
    if (!file.type.startsWith('image/')) {
      alert('请选择图片文件');
      return;
    }

    // 验证文件大小（最大 5MB）
    if (file.size > 5 * 1024 * 1024) {
      alert('图片大小不能超过 5MB');
      return;
    }

    try {
      setUploading(true);
      const url = await uploadBackground(file);
      setCustomBackground({
        enabled: true,
        imageUrl: url,
      });
    } catch (error) {
      console.error('Failed to upload background:', error);
      alert('上传失败，请重试');
    } finally {
      setUploading(false);
    }
  };

  /**
   * 触发文件选择
   */
  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  /**
   * 切换背景启用状态
   */
  const toggleBackgroundEnabled = () => {
    setCustomBackground({
      enabled: !config.customBackground?.enabled,
    });
  };

  /**
   * 更新背景模糊度
   */
  const handleBlurChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCustomBackground({
      blur: Number(e.target.value),
    });
  };

  /**
   * 更新前景透明度（即内容区域的不透明度）
   */
  const handleOpacityChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCustomBackground({
      opacity: Number(e.target.value),
    });
  };

  const bg = config.customBackground;

  return (
    <div className="theme-selector space-y-6">
      {/* 主题模式选择 */}
      <div className="theme-mode-section">
        <h3 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          主题模式
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => handleThemeModeChange('light')}
            className={`theme-mode-btn ${config.mode === 'light' ? 'active' : ''}`}
          >
            <Icon name="sun" size={24} className="mb-2" />
            <span>亮色</span>
          </button>
          <button
            onClick={() => handleThemeModeChange('dark')}
            className={`theme-mode-btn ${config.mode === 'dark' ? 'active' : ''}`}
          >
            <Icon name="moon" size={24} className="mb-2" />
            <span>暗色</span>
          </button>
          <button
            onClick={() => handleThemeModeChange('system')}
            className={`theme-mode-btn ${config.mode === 'system' ? 'active' : ''}`}
          >
            <Icon name="settings" size={24} className="mb-2" />
            <span>系统</span>
          </button>
          <button
            onClick={() => handleThemeModeChange('transparent')}
            className={`theme-mode-btn ${config.mode === 'transparent' ? 'active' : ''}`}
          >
            <Icon name="palette" size={24} className="mb-2" />
            <span>透明</span>
          </button>
        </div>
      </div>

      {/* 自定义背景 */}
      <div className="custom-background-section">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            自定义背景
          </h3>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={bg?.enabled || false}
              onChange={toggleBackgroundEnabled}
              className="w-4 h-4"
            />
            <span style={{ color: 'var(--text-secondary)' }}>启用</span>
          </label>
        </div>

        {/* 上传按钮 */}
        <button
          onClick={triggerFileSelect}
          disabled={uploading}
          className="upload-btn w-full mb-4"
        >
          {uploading ? '上传中...' : '📁 上传背景图片'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleBackgroundUpload}
          className="hidden"
        />

        {/* 背景预览 */}
        {bg?.imageUrl && (
          <div className="background-preview mb-4">
            <img
              src={bg.imageUrl}
              alt="背景预览"
              className="w-full h-32 object-cover rounded-lg"
            />
          </div>
        )}

        {/* 背景调节 */}
        {bg?.enabled && bg?.imageUrl && (
          <div className="background-controls space-y-4">
            {/* 模糊度 */}
            <div className="control-item">
              <label className="flex items-center justify-between mb-2">
                <span style={{ color: 'var(--text-secondary)' }}>模糊度</span>
                <span style={{ color: 'var(--text-primary)' }}>{bg.blur}px</span>
              </label>
              <input
                type="range"
                min="0"
                max="20"
                step="1"
                value={bg.blur}
                onChange={handleBlurChange}
                className="w-full"
              />
            </div>

            {/* 前景透明度 */}
            <div className="control-item">
              <label className="flex items-center justify-between mb-2">
                <span style={{ color: 'var(--text-secondary)' }}>前景透明度</span>
                <span style={{ color: 'var(--text-primary)' }}>
                  {Math.round(bg.opacity * 100)}%
                </span>
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={bg.opacity}
                onChange={handleOpacityChange}
                className="w-full"
              />
            </div>
          </div>
        )}
      </div>

      <style>{`
        .theme-mode-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 16px;
          background-color: var(--bg-secondary);
          border: 2px solid var(--border-primary);
          border-radius: var(--border-radius-large);
          cursor: pointer;
          transition: all var(--transition-duration);
          color: var(--text-primary);
        }

        .theme-mode-btn:hover {
          background-color: var(--bg-hover);
          border-color: var(--border-hover);
          transform: translateY(-2px);
          box-shadow: var(--shadow-medium);
        }

        .theme-mode-btn.active {
          background-color: var(--primary-light);
          border-color: var(--primary-color);
          box-shadow: var(--shadow-active);
        }

        .upload-btn {
          padding: 12px 20px;
          background-color: var(--primary-color);
          color: white;
          border: none;
          border-radius: var(--border-radius);
          cursor: pointer;
          transition: all var(--transition-duration);
          font-size: var(--font-size-base);
        }

        .upload-btn:hover:not(:disabled) {
          background-color: var(--primary-hover);
          transform: translateY(-1px);
          box-shadow: var(--shadow-hover);
        }

        .upload-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        input[type="range"] {
          -webkit-appearance: none;
          appearance: none;
          height: 6px;
          background: var(--bg-tertiary);
          border-radius: 3px;
          outline: none;
        }

        input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 16px;
          height: 16px;
          background: var(--primary-color);
          border-radius: 50%;
          cursor: pointer;
          transition: all var(--transition-duration);
        }

        input[type="range"]::-webkit-slider-thumb:hover {
          transform: scale(1.2);
          box-shadow: 0 0 0 4px var(--primary-light);
        }

        input[type="range"]::-moz-range-thumb {
          width: 16px;
          height: 16px;
          background: var(--primary-color);
          border-radius: 50%;
          cursor: pointer;
          border: none;
        }
      `}</style>
    </div>
  );
}

