import { memo, useState } from "react";
import Modal from "./Modal";
import { useTheme } from "../context/ThemeContext";
import type { ThemeMode } from "../types/theme";
import { Icon, type IconName } from "./Icon";
import { useToast } from "./Toast";

interface ThemeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ThemeModal = memo(({ isOpen, onClose }: ThemeModalProps) => {
  const { config, setThemeMode, setCustomBackground, uploadBackground } = useTheme();
  const { showSuccess, showError } = useToast();
  const [isUploading, setIsUploading] = useState(false);

  // 主题模式选项
  const themeModes: { mode: ThemeMode; icon: IconName; label: string; description: string }[] = [
    { mode: "light", icon: "sun", label: "亮色", description: "明亮清晰的界面" },
    { mode: "dark", icon: "moon", label: "暗色", description: "深色护眼模式" },
  ];

  // 处理主题模式选择
  const handleThemeModeChange = (mode: ThemeMode) => {
    setThemeMode(mode);
  };

  // 处理背景图片上传
  const handleBackgroundUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    
    // 清除 input 的值，允许重复选择同一文件
    e.target.value = '';
    
    if (!file) {
      return;
    }

    // 验证文件类型
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      showError('请选择 JPG、PNG 或 WebP 格式的图片');
      return;
    }

    // 验证文件大小（限制10MB）
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
      showError('图片文件过大，请选择小于 10MB 的图片');
      return;
    }

    try {
      setIsUploading(true);
      console.log('开始上传图片:', file.name, file.type, file.size);
      
      const imageUrl = await uploadBackground(file);
      
      console.log('图片上传成功，URL 长度:', imageUrl?.length);
      
      if (imageUrl) {
        // 获取当前 opacity，如果小于 0.4，设置为 1（完全可见）
        const currentOpacity = config.customBackground?.opacity || 0;
        const newOpacity = currentOpacity < 0.4 ? 1 : currentOpacity;
        
        setCustomBackground({
          enabled: true,
          imageUrl,
          opacity: newOpacity,
          blur: config.customBackground?.blur || 0,
        });
        
        showSuccess('背景图片上传成功！');
      } else {
        throw new Error('图片读取失败，返回空 URL');
      }
    } catch (error) {
      console.error('图片上传失败:', error);
      showError(`图片上传失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setIsUploading(false);
    }
  };

  // 处理自定义背景启用/禁用
  const handleBackgroundToggle = (enabled: boolean) => {
    setCustomBackground({
      enabled,
    });
  };

  // 处理模糊度变化
  const handleBlurChange = (blur: number) => {
    setCustomBackground({
      blur,
    });
  };

  // 处理前景透明度变化
  const handleOpacityChange = (opacity: number) => {
    setCustomBackground({
      opacity,
    });
  };

  return (
    <Modal open={isOpen} onClose={onClose} title="主题设置" size="lg">
      <div className="space-y-6">
        {/* 主题模式选择 */}
        <div>
          <h3 className="text-sm font-medium mb-3" style={{ color: "var(--text-primary)" }}>
            主题模式
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {themeModes.map(({ mode, icon, label, description }) => (
              <button
                key={mode}
                onClick={() => handleThemeModeChange(mode)}
                className="p-4 rounded-lg border-2 transition-all duration-200 text-left"
                style={{
                  backgroundColor: config.mode === mode ? "var(--primary-color)" : "var(--bg-primary)",
                  borderColor: config.mode === mode ? "var(--primary-color)" : "var(--border-primary)",
                  color: config.mode === mode ? "white" : "var(--text-primary)",
                }}
              >
                <div className="flex items-center space-x-3">
                  <Icon name={icon} size={24} />
                  <div className="flex-1">
                    <div className="font-medium">{label}</div>
                    <div
                      className="text-xs mt-1"
                      style={{
                        color: config.mode === mode ? "rgba(255,255,255,0.8)" : "var(--text-secondary)",
                      }}
                    >
                      {description}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 自定义背景 */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
              自定义背景
            </h3>
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={config.customBackground?.enabled || false}
                onChange={(e) => handleBackgroundToggle(e.target.checked)}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              <span className="ml-3 text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
                启用
              </span>
            </label>
          </div>

          {/* 上传背景图片 */}
          <div className="mb-4">
            <label
              className={`flex items-center justify-center w-full p-4 border-2 border-dashed rounded-lg transition-colors duration-200 ${
                isUploading ? 'cursor-wait opacity-60' : 'cursor-pointer hover:border-blue-500'
              }`}
              style={{
                borderColor: isUploading ? "var(--text-secondary)" : "var(--border-primary)",
                backgroundColor: "var(--bg-secondary)",
              }}
            >
              <div className="flex flex-col items-center">
                {isUploading ? (
                  <>
                    <Icon name="loading" size={32} className="animate-spin mb-2" />
                    <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      上传中...
                    </span>
                  </>
                ) : (
                  <>
                    <Icon name="upload" size={32} className="mb-2" />
                    <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      上传背景图片
                    </span>
                    <span className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                      支持 JPG、PNG、WebP 格式（最大 10MB）
                    </span>
                  </>
                )}
              </div>
              <input
                type="file"
                accept="image/jpeg,image/jpg,image/png,image/webp"
                onChange={handleBackgroundUpload}
                disabled={isUploading}
                className="hidden"
              />
            </label>
            
            {/* 显示当前图片信息 */}
            {config.customBackground?.imageUrl && (
              <div className="mt-2 text-xs flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
                <Icon name="check" size={14} color="var(--primary-color)" />
                <span>背景图片已设置</span>
              </div>
            )}
          </div>

          {/* 背景参数调节 */}
          {config.customBackground?.enabled && config.customBackground?.imageUrl && (
            <div className="space-y-4">
              {/* 模糊度 */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    模糊度
                  </label>
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    {config.customBackground?.blur || 0}px
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="20"
                  step="1"
                  value={config.customBackground?.blur || 0}
                  onChange={(e) => handleBlurChange(Number(e.target.value))}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                  style={{
                    accentColor: "var(--primary-color)",
                  }}
                />
              </div>

              {/* 内容不透明度 */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    内容不透明度
                  </label>
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    {Math.round((config.customBackground?.opacity || 1) * 100)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.4"
                  max="1"
                  step="0.01"
                  value={config.customBackground?.opacity || 1}
                  onChange={(e) => handleOpacityChange(Number(e.target.value))}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                  style={{
                    accentColor: "var(--primary-color)",
                  }}
                />
                <p className="text-xs mt-2 flex items-start gap-1" style={{ color: "var(--text-secondary)" }}>
                  <Icon name="info" size={12} style={{ marginTop: '2px' }} />
                  调低此值可以让背景图片更明显，但可能影响文字可读性
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
});

ThemeModal.displayName = "ThemeModal";

