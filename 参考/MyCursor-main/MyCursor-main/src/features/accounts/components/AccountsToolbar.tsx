import { Dropdown, Icon } from "@/components";
import type { DropdownOption } from "@/components";

interface RefreshProgress {
  current: number;
  total: number;
  isRefreshing: boolean;
}

interface AccountsToolbarProps {
  showAddForm: boolean;
  selectedCount: number;
  refreshProgress: RefreshProgress;
  subscriptionFilterOptions: DropdownOption[];
  subscriptionFilter: string;
  onSubscriptionFilterChange: (value: string) => void;
  tagFilterOptions: DropdownOption[];
  tagFilter: string;
  onTagFilterChange: (value: string) => void;
  concurrentLimit: number;
  onConcurrentLimitChange: (value: number) => void;
  onToggleAddForm: () => void;
  onRefreshAll: () => void;
  onDeleteSelected: () => void;
  onExportSelected: () => void;
  onImportAccounts: () => void;
  onRefreshCurrentAccount: () => void;
}

export function AccountsToolbar({
  showAddForm,
  selectedCount,
  refreshProgress,
  subscriptionFilterOptions,
  subscriptionFilter,
  onSubscriptionFilterChange,
  tagFilterOptions,
  tagFilter,
  onTagFilterChange,
  concurrentLimit,
  onConcurrentLimitChange,
  onToggleAddForm,
  onRefreshAll,
  onDeleteSelected,
  onExportSelected,
  onImportAccounts,
  onRefreshCurrentAccount,
}: AccountsToolbarProps) {
  const getButtonStyle = (
    variant: "primary" | "secondary" | "success" | "danger" = "primary",
    disabled = false
  ) => {
    const baseStyle = {
      display: "inline-flex",
      alignItems: "center",
      padding: "8px 12px",
      fontSize: "13px",
      fontWeight: "500",
      borderRadius: "var(--border-radius)",
      border: "none",
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "all var(--transition-duration) ease",
      boxShadow: "var(--shadow-light)",
      opacity: disabled ? 0.5 : 1,
    };

    const variants = {
      primary: {
        backgroundColor: "var(--primary-color)",
        color: "white",
      },
      secondary: {
        backgroundColor: "var(--bg-secondary)",
        color: "var(--text-primary)",
        border: "1px solid var(--border-primary)",
      },
      success: {
        backgroundColor: "#10b981",
        color: "white",
      },
      danger: {
        backgroundColor: "#ef4444",
        color: "white",
      },
    };

    return { ...baseStyle, ...variants[variant] };
  };

  const withHover = (disabled = false) => ({
    onMouseEnter: (e: React.MouseEvent<HTMLButtonElement>) => {
      if (!disabled) {
        e.currentTarget.style.transform = "translateY(-1px)";
        e.currentTarget.style.boxShadow = "var(--shadow-medium)";
      }
    },
    onMouseLeave: (e: React.MouseEvent<HTMLButtonElement>) => {
      e.currentTarget.style.transform = "translateY(0)";
      e.currentTarget.style.boxShadow = "var(--shadow-light)";
    },
  });

  return (
    <div
      className="sticky top-0 z-10"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-primary)",
        backdropFilter: "blur(var(--backdrop-blur))",
        WebkitBackdropFilter: "blur(var(--backdrop-blur))",
        boxShadow: "var(--shadow-light)",
        borderTopLeftRadius: "var(--border-radius-large)",
        borderTopRightRadius: "var(--border-radius-large)",
      }}
    >
      <div className="px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <button
            type="button"
            onClick={onToggleAddForm}
            style={getButtonStyle("primary")}
            title={showAddForm ? "关闭添加表单" : "打开添加表单"}
            {...withHover()}
          >
            <Icon name="plus" size={14} style={{ marginRight: "4px" }} />
            添加
          </button>

          <button
            type="button"
            onClick={onRefreshAll}
            disabled={refreshProgress.isRefreshing}
            style={getButtonStyle("success", refreshProgress.isRefreshing)}
            {...withHover(refreshProgress.isRefreshing)}
          >
            {refreshProgress.isRefreshing ? (
              <>
                <Icon name="loading" size={14} style={{ marginRight: "4px" }} className="animate-spin" />
                刷新中
              </>
            ) : (
              <>
                <Icon name="refresh" size={14} style={{ marginRight: "4px" }} />
                刷新{selectedCount > 0 && ` (${selectedCount})`}
              </>
            )}
          </button>

          <button
            type="button"
            onClick={onDeleteSelected}
            disabled={selectedCount === 0}
            style={getButtonStyle("danger", selectedCount === 0)}
            {...withHover(selectedCount === 0)}
          >
            <Icon name="trash" size={14} style={{ marginRight: "4px" }} />
            删除{selectedCount > 0 && ` (${selectedCount})`}
          </button>

          <button
            type="button"
            onClick={onExportSelected}
            disabled={selectedCount === 0}
            style={getButtonStyle("primary", selectedCount === 0)}
            {...withHover(selectedCount === 0)}
          >
            <Icon name="export" size={14} style={{ marginRight: "4px" }} />
            导出 {selectedCount > 0 && `(${selectedCount})`}
          </button>

          <button
            type="button"
            onClick={onImportAccounts}
            style={getButtonStyle("secondary")}
            {...withHover()}
          >
            <Icon name="import" size={14} style={{ marginRight: "4px" }} />
            导入
          </button>

          <button
            type="button"
            onClick={onRefreshCurrentAccount}
            style={getButtonStyle("secondary")}
            {...withHover()}
          >
            <Icon name="refresh" size={14} style={{ marginRight: "4px" }} />
            刷新当前账号
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Dropdown
            options={subscriptionFilterOptions}
            value={subscriptionFilter}
            onChange={onSubscriptionFilterChange}
          />

          {tagFilterOptions.length > 1 && (
            <Dropdown
              options={tagFilterOptions}
              value={tagFilter}
              onChange={onTagFilterChange}
            />
          )}

          <div className="flex items-center gap-2">
            <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
              并发:
            </label>
            <input
              type="number"
              min="1"
              max="10"
              value={concurrentLimit}
              onChange={(e) => {
                const value = parseInt(e.target.value, 10);
                if (value >= 1 && value <= 10) {
                  onConcurrentLimitChange(value);
                }
              }}
              style={{
                width: "50px",
                padding: "6px 8px",
                fontSize: "13px",
                backgroundColor: "var(--bg-primary)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-primary)",
                borderRadius: "var(--border-radius)",
                textAlign: "center",
                transition: "all var(--transition-duration) ease",
              }}
              onFocus={(e) => {
                e.currentTarget.style.outline = "none";
                e.currentTarget.style.borderColor = "var(--primary-color)";
                e.currentTarget.style.boxShadow = "0 0 0 3px rgba(74, 137, 220, 0.1)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = "var(--border-primary)";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
          </div>
        </div>

        {refreshProgress.isRefreshing && (
          <div className="mt-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
                刷新进度: {refreshProgress.current} / {refreshProgress.total}
              </span>
              <span className="text-sm font-medium" style={{ color: "var(--primary-color)" }}>
                {Math.round((refreshProgress.current / refreshProgress.total) * 100)}%
              </span>
            </div>
            <div
              className="w-full h-2 overflow-hidden"
              style={{
                backgroundColor: "var(--bg-secondary)",
                borderRadius: "12px",
              }}
            >
              <div
                className="h-2 transition-all duration-300"
                style={{
                  width: `${(refreshProgress.current / refreshProgress.total) * 100}%`,
                  backgroundColor: "var(--primary-color)",
                  borderRadius: "12px",
                }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
