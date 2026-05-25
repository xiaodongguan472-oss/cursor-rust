import React, { memo } from "react";

export type BadgeColor = "primary" | "info" | "success" | "danger" | "gray";

interface BadgeProps {
  color?: BadgeColor;
  children: React.ReactNode;
  className?: string;
}

const Badge: React.FC<BadgeProps> = memo(({
  color = "primary",
  children,
  className = "",
}) => {
  const colorStyles = {
    primary: "bg-primary-600/15 text-primary-600",
    info: "bg-info-500/15 text-info-600",
    success: "bg-success-500/15 text-success-600",
    danger: "bg-danger-500/15 text-danger-600",
    gray: "bg-gray-200 text-gray-700",
  };

  return (
    <span
      className={`
        inline-flex items-center
        px-3 py-1 rounded-full
        text-xs font-semibold
        ${colorStyles[color]}
        ${className}
      `}
    >
      {children}
    </span>
  );
});

Badge.displayName = "Badge";

export default Badge;
