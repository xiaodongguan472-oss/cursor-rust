import React, { memo, CSSProperties } from "react";

export type ButtonVariant = "primary" | "info" | "success" | "danger" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

const Button: React.FC<ButtonProps> = memo(({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  disabled,
  className = "",
  style,
  children,
  ...props
}) => {
  // 获取变体样式（使用 CSS 变量）
  const getVariantStyle = (): CSSProperties => {
    const baseStyle: CSSProperties = {
      transition: 'all 0.2s ease',
    };

    switch (variant) {
      case "primary":
        return {
          ...baseStyle,
          backgroundColor: 'var(--primary-color)',
          color: 'white',
          boxShadow: 'var(--shadow-medium)',
        };
      case "info":
        return {
          ...baseStyle,
          backgroundColor: 'var(--info-color)',
          color: 'white',
        };
      case "success":
        return {
          ...baseStyle,
          backgroundColor: 'var(--success-color)',
          color: 'white',
        };
      case "danger":
        return {
          ...baseStyle,
          backgroundColor: 'var(--danger-color)',
          color: 'white',
        };
      case "ghost":
        return {
          ...baseStyle,
          backgroundColor: 'transparent',
          color: 'var(--primary-color)',
          border: '1px solid var(--border-primary)',
        };
      default:
        return baseStyle;
    }
  };

  // 尺寸样式（使用设计系统的间距）
  const sizeStyles = {
    sm: "px-3 py-1.5 text-sm",  // 12px/6px
    md: "px-4 py-2 text-base",   // 16px/8px
    lg: "px-6 py-3 text-lg",     // 24px/12px
  };

  // 禁用状态
  const disabledStyles =
    disabled || loading ? "opacity-50 cursor-not-allowed" : "";

  // 悬停效果类名
  const hoverClass = !disabled && !loading ? "hover-lift" : "";

  return (
    <button
      className={`
        inline-flex items-center justify-center gap-2
        rounded-lg font-medium
        ${sizeStyles[size]}
        ${disabledStyles}
        ${hoverClass}
        ${className}
      `}
      style={{
        ...getVariantStyle(),
        ...style,
      }}
      disabled={disabled || loading}
      onMouseEnter={(e) => {
        if (!disabled && !loading && variant !== 'ghost') {
          e.currentTarget.style.transform = 'translateY(-1px)';
          e.currentTarget.style.boxShadow = 'var(--shadow-heavy)';
        }
        if (!disabled && !loading && variant === 'ghost') {
          e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
          e.currentTarget.style.borderColor = 'var(--primary-color)';
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled && !loading) {
          e.currentTarget.style.transform = 'translateY(0)';
          if (variant !== 'ghost') {
            e.currentTarget.style.boxShadow = 'var(--shadow-medium)';
          } else {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.borderColor = 'var(--border-primary)';
          }
        }
      }}
      {...props}
    >
      {loading && (
        <svg
          className="animate-spin h-4 w-4"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          ></circle>
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          ></path>
        </svg>
      )}
      {!loading && icon && <span>{icon}</span>}
      {children}
    </button>
  );
});

Button.displayName = "Button";

export default Button;
