/** 状态指示标签（单个状态指标卡片） */
interface StatusBadgeProps {
  label: string;
  active: boolean;
  activeText: string;
  inactiveText: string;
}

export function StatusBadge({ label, active, activeText, inactiveText }: StatusBadgeProps) {
  return (
    <div className="p-3 rounded-lg" style={{ backgroundColor: "var(--bg-secondary)" }}>
      <p className="text-xs font-medium mb-1" style={{ color: "var(--text-tertiary)" }}>
        {label}
      </p>
      <div className="flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: active ? "#4ec9b0" : "#666" }}
        />
        <p className="text-sm font-semibold" style={{ color: active ? "#4ec9b0" : "var(--text-secondary)" }}>
          {active ? activeText : inactiveText}
        </p>
      </div>
    </div>
  );
}
