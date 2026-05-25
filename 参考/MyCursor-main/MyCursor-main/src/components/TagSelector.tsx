import { useState, useEffect, useCallback, useRef, memo } from "react";
import { invoke } from "@tauri-apps/api/core";

interface TagSelectorProps {
  /** 当前已选中的标签列表 */
  selectedTags: string[];
  /** 标签变更回调 */
  onChange: (tags: string[]) => void;
}

/**
 * 标签选择器组件
 * 支持从预设标签中多选，也支持输入新标签回车创建
 */
export const TagSelector = memo(({ selectedTags, onChange }: TagSelectorProps) => {
  const [presetTags, setPresetTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 组件挂载时加载预设标签
  useEffect(() => {
    loadPresetTags();
  }, []);

  // 点击外部关闭下拉面板
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  /** 从后端加载预设标签 */
  const loadPresetTags = async () => {
    try {
      const result = await invoke<{ success: boolean; tags: string[] }>("get_preset_tags");
      if (result.success) {
        setPresetTags(result.tags);
      }
    } catch (error) {
      console.error("加载预设标签失败:", error);
    }
  };

  /** 保存预设标签到后端 */
  const savePresetTags = useCallback(async (tags: string[]) => {
    try {
      await invoke("save_preset_tags", { tags });
    } catch (error) {
      console.error("保存预设标签失败:", error);
    }
  }, []);

  /** 切换标签的选中状态 */
  const toggleTag = useCallback((tag: string) => {
    if (selectedTags.includes(tag)) {
      onChange(selectedTags.filter(t => t !== tag));
    } else {
      onChange([...selectedTags, tag]);
    }
  }, [selectedTags, onChange]);

  /** 输入框回车事件：创建新标签或选中已有标签 */
  const handleInputKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const val = tagInput.trim();
      if (!val) return;

      // 如果预设中不存在，则新建预设标签
      if (!presetTags.includes(val)) {
        const newPresets = [...presetTags, val];
        setPresetTags(newPresets);
        savePresetTags(newPresets);
      }
      // 选中该标签
      if (!selectedTags.includes(val)) {
        onChange([...selectedTags, val]);
      }
      setTagInput("");
    }
  }, [tagInput, presetTags, selectedTags, onChange, savePresetTags]);

  /** 移除已选标签 */
  const removeSelectedTag = useCallback((tag: string) => {
    onChange(selectedTags.filter(t => t !== tag));
  }, [selectedTags, onChange]);

  /** 删除预设标签（同时从已选中移除） */
  const removePresetTag = useCallback((tag: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newPresets = presetTags.filter(t => t !== tag);
    setPresetTags(newPresets);
    savePresetTags(newPresets);
    if (selectedTags.includes(tag)) {
      onChange(selectedTags.filter(t => t !== tag));
    }
  }, [presetTags, selectedTags, onChange, savePresetTags]);

  /** 点击创建新标签 */
  const handleCreateTag = useCallback(() => {
    const val = tagInput.trim();
    if (!val) return;
    if (!presetTags.includes(val)) {
      const newPresets = [...presetTags, val];
      setPresetTags(newPresets);
      savePresetTags(newPresets);
    }
    if (!selectedTags.includes(val)) {
      onChange([...selectedTags, val]);
    }
    setTagInput("");
  }, [tagInput, presetTags, selectedTags, onChange, savePresetTags]);

  // 根据输入过滤预设标签
  const filteredPresets = tagInput.trim()
    ? presetTags.filter(t => t.toLowerCase().includes(tagInput.trim().toLowerCase()))
    : presetTags;

  // 是否显示"创建新标签"提示
  const showNewTagHint = tagInput.trim() && !presetTags.includes(tagInput.trim());

  return (
    <div ref={containerRef}>
      {/* 已选标签展示 */}
      {selectedTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selectedTags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
              style={{
                backgroundColor: 'rgba(74, 137, 220, 0.15)',
                color: 'var(--primary-color)',
              }}
            >
              {tag}
              <button
                type="button"
                onClick={() => removeSelectedTag(tag)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--primary-color)', padding: '0 2px', fontSize: '14px', lineHeight: '1',
                }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 搜索/输入框 */}
      <div style={{ position: 'relative' }}>
        <input
          type="text"
          value={tagInput}
          onChange={(e) => {
            setTagInput(e.target.value);
            if (!isDropdownOpen) setIsDropdownOpen(true);
          }}
          onFocus={() => setIsDropdownOpen(true)}
          onKeyDown={handleInputKeyDown}
          placeholder={presetTags.length > 0 ? "搜索或输入新标签，回车添加" : "输入标签名，回车创建"}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          style={{
            fontSize: '13px',
            backgroundColor: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            borderColor: 'var(--border-primary)',
          }}
        />

        {/* 预设标签下拉面板 */}
        {isDropdownOpen && (filteredPresets.length > 0 || showNewTagHint) && (
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              marginTop: '4px',
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--border-radius)',
              boxShadow: 'var(--shadow-medium)',
              zIndex: 50,
              maxHeight: '200px',
              overflowY: 'auto',
            }}
          >
            {/* 预设标签列表 */}
            {filteredPresets.map((tag) => {
              const isSelected = selectedTags.includes(tag);
              return (
                <div
                  key={tag}
                  onClick={() => toggleTag(tag)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    cursor: 'pointer',
                    fontSize: '13px',
                    color: isSelected ? 'var(--primary-color)' : 'var(--text-primary)',
                    backgroundColor: isSelected ? 'rgba(74, 137, 220, 0.08)' : 'transparent',
                    transition: 'background-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = isSelected
                      ? 'rgba(74, 137, 220, 0.12)'
                      : 'var(--bg-secondary)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = isSelected
                      ? 'rgba(74, 137, 220, 0.08)'
                      : 'transparent';
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {/* 复选框指示器 */}
                    <span
                      style={{
                        width: '16px',
                        height: '16px',
                        borderRadius: '3px',
                        border: isSelected
                          ? '2px solid var(--primary-color)'
                          : '2px solid var(--border-primary)',
                        backgroundColor: isSelected ? 'var(--primary-color)' : 'transparent',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        fontSize: '10px',
                        color: 'white',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {isSelected && '✓'}
                    </span>
                    <span>{tag}</span>
                  </div>
                  {/* 删除预设标签按钮 */}
                  <button
                    type="button"
                    onClick={(e) => removePresetTag(tag, e)}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: 'var(--text-tertiary)', padding: '0 4px',
                      fontSize: '14px', lineHeight: '1',
                      opacity: 0.6,
                      transition: 'opacity 0.15s',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.opacity = '1'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.opacity = '0.6'; }}
                    title="删除预设标签"
                  >
                    ×
                  </button>
                </div>
              );
            })}

            {/* 新建标签提示 */}
            {showNewTagHint && (
              <div
                onClick={handleCreateTag}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 10px',
                  cursor: 'pointer',
                  fontSize: '13px',
                  color: 'var(--primary-color)',
                  borderTop: filteredPresets.length > 0 ? '1px solid var(--border-primary)' : 'none',
                  transition: 'background-color 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-secondary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <span style={{ fontWeight: 600 }}>+</span>
                <span>创建标签 "<strong>{tagInput.trim()}</strong>"</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

TagSelector.displayName = "TagSelector";
