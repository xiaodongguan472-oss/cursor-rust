import React, { memo, CSSProperties } from "react";

export type AlertType = "success" | "info" | "warning" | "error";

interface AlertProps {
  type: AlertType;
  children: React.ReactNode;
  className?: string;
  style?: CSSProperties;
}

const Alert: React.FC<AlertProps> = memo(({ type, children, className = "", style }) => {
  // 获取类型样式（使用 CSS 变量）
  const getTypeStyle = (): CSSProperties => {
    const baseStyle: CSSProperties = {
      borderRadius: 'var(--border-radius)',
      borderLeft: '4px solid',
    };

    switch (type) {
      case "success":
        return {
          ...baseStyle,
          backgroundColor: 'rgba(34, 197, 94, 0.1)',
          color: 'var(--success-color)',
          borderLeftColor: 'var(--success-color)',
        };
      case "info":
        return {
          ...baseStyle,
          backgroundColor: 'rgba(74, 137, 220, 0.1)',
          color: 'var(--info-color)',
          borderLeftColor: 'var(--info-color)',
        };
      case "warning":
        return {
          ...baseStyle,
          backgroundColor: 'rgba(251, 146, 60, 0.1)',
          color: 'var(--warning-color)',
          borderLeftColor: 'var(--warning-color)',
        };
      case "error":
        return {
          ...baseStyle,
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          color: 'var(--danger-color)',
          borderLeftColor: 'var(--danger-color)',
        };
    }
  };

  const icons = {
    success: "✓",
    info: "ⓘ",
    warning: "⚠",
    error: "✕",
  };

  return (
    <div
      className={`flex items-start gap-3 px-3 py-2 ${className}`}
      style={{
        ...getTypeStyle(),
        ...style,
      }}
    >
      <span className="text-lg mt-0.5">{icons[type]}</span>
      <div className="flex-1">{children}</div>
    </div>
  );
});

Alert.displayName = "Alert";

export default Alert;
