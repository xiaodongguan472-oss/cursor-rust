import React, { memo } from "react";

interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  color?: "primary" | "white";
  className?: string;
}

export const Spinner: React.FC<SpinnerProps> = memo(({
  size = "md",
  color = "primary",
  className = "",
}) => {
  const sizeStyles = {
    sm: "w-4 h-4",
    md: "w-8 h-8",
    lg: "w-12 h-12",
  };

  const colorStyles = {
    primary: "border-primary-600",
    white: "border-white",
  };

  return (
    <div
      className={`
        ${sizeStyles[size]}
        border-4 border-gray-200
        ${colorStyles[color]}
        border-t-transparent
        rounded-full
        animate-spin
        ${className}
      `}
    />
  );
});

Spinner.displayName = "Spinner";

// Loading组件
interface LoadingSpinnerProps {
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = memo(({ message }) => {
  return (
    <div className="flex flex-col items-center justify-center py-12">
      <Spinner size="lg" />
      {message && <p className="mt-4 text-gray-600">{message}</p>}
    </div>
  );
});

LoadingSpinner.displayName = "LoadingSpinner";

// 保持默认导出以兼容
export default Spinner;
